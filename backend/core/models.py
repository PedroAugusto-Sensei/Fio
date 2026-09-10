"""Modelo de dados do Fio.

Leia as invariantes do CLAUDE.md antes de mexer aqui. Em especial:
`Mensagem` é imutável, `Chamado` não tem `descricao` nem `situacao`.
"""
import hashlib
import secrets
from datetime import timedelta

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Count, OuterRef, Q, Subquery, Value
from django.utils import timezone

SITUACOES = [
    ("em_andamento", "Em andamento"),
    ("concluido", "Concluído"),
    ("bloqueado", "Bloqueado"),
    ("duvida_cliente", "Dúvida com o cliente"),
]

SITUACOES_VALIDAS = {chave for chave, _ in SITUACOES}

#: Não existe senha compartilhada de empresa: cada funcionário tem conta própria,
#: porque `Registro.autor` e `Registro.setor` são a resposta do produto para "quem
#: agiu". Com login compartilhado o feed do chamado viraria ficção. A empresa é um
#: container, não uma credencial.
#:
#: O papel decide só três coisas: convidar pessoas, editar a lista de setores e mexer
#: na configuração da caixa de e-mail. Ler chamado e publicar registro é de todos —
#: permissão por setor continua fora de escopo, e isso é parte da tese.
PAPEIS = [
    ("admin", "Administrador"),
    ("membro", "Membro"),
]

PAPEIS_VALIDOS = {chave for chave, _ in PAPEIS}

#: Quanto tempo um convite continua aceitando alguém.
DIAS_DE_CONVITE = 7


class Empresa(models.Model):
    criador = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="empresas_criadas")
    imap_host = models.CharField(max_length=253, blank=True, default="")
    imap_usuario = models.CharField(max_length=254, blank=True, default="")
    imap_senha = models.TextField(blank=True, default="", editable=False)
    imap_pasta = models.CharField(max_length=255, default="INBOX")
    nome = models.CharField(max_length=200)
    # A caixa de e-mail da empresa que o ingest lê. Não é endereço de encaminhamento:
    # ninguém encaminha nada para o Fio, o Fio é que lê a caixa.
    #
    # Vazia na empresa que acabou de se cadastrar pela interface: configurar a caixa é
    # coisa de admin e não entra no cadastro. Enquanto estiver vazia, nenhum e-mail
    # entra para esta empresa — o ingest resolve a empresa pela caixa de onde leu.
    caixa_email = models.EmailField(blank=True, default="")
    setores = models.JSONField(default=list)  # ["Suporte", "Produto", ...]
    retencao_dias = models.PositiveIntegerField(default=1825)
    proximo_numero = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        constraints = [
            # Duas empresas não podem ler a mesma caixa — senão o ingest não saberia
            # de quem é o e-mail. Vazio não conta: empresa sem caixa não lê nada.
            models.UniqueConstraint(
                fields=["caixa_email"],
                name="uniq_caixa_email",
                condition=~models.Q(caixa_email=""),
            )
        ]

    def __str__(self):
        return self.nome

    def novo_codigo(self) -> str:
        """Consome o próximo número da empresa. Chamar dentro de transaction.atomic()."""
        empresa = Empresa.objects.select_for_update().get(pk=self.pk)
        numero = empresa.proximo_numero
        Empresa.objects.filter(pk=self.pk).update(proximo_numero=numero + 1)
        self.proximo_numero = numero + 1
        return "D-%04d" % numero


class Pessoa(models.Model):
    user = models.OneToOneField("auth.User", on_delete=models.CASCADE)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pessoas")
    nome = models.CharField(max_length=200)
    setor = models.CharField(max_length=80)
    papel = models.CharField(max_length=10, choices=PAPEIS, default="membro")

    class Meta:
        verbose_name = "pessoa"
        verbose_name_plural = "pessoas"

    def __str__(self):
        return f"{self.nome} · {self.setor}"

    @property
    def e_admin(self) -> bool:
        """Convidar, editar setores e mexer na caixa. Nada além disso."""
        return self.papel == "admin"

    @property
    def iniciais(self) -> str:
        partes = [p for p in self.nome.split() if p]
        if not partes:
            return "?"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()


def token_de_convite() -> str:
    return secrets.token_urlsafe(32)


def prazo_de_convite():
    return timezone.now() + timedelta(days=DIAS_DE_CONVITE)


class Convite(models.Model):
    """Link que deixa uma pessoa criar a **própria** conta dentro de uma empresa.

    Existe porque não existe senha compartilhada: a empresa é um container, não uma
    credencial. Quem entra por aqui vira uma `Pessoa` com nome e setor próprios, e é
    esse nome que aparece em `Registro.autor` depois.

    O Fio não manda e-mail (está fora de escopo). Quem convida copia o link e entrega
    pelo canal que a empresa já usa; `email` aqui é só sugestão de preenchimento na
    tela de aceitar, e não restringe quem aceita.
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="convites")
    criado_por = models.ForeignKey(
        Pessoa, on_delete=models.PROTECT, related_name="convites_feitos"
    )
    token = models.CharField(max_length=64, unique=True, db_index=True, default=token_de_convite)
    email = models.EmailField(blank=True)
    setor = models.CharField(max_length=80, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField(default=prazo_de_convite)
    usado_em = models.DateTimeField(null=True, blank=True)
    usado_por = models.ForeignKey(
        Pessoa, null=True, blank=True, on_delete=models.SET_NULL, related_name="convites_aceitos"
    )

    class Meta:
        verbose_name = "convite"
        verbose_name_plural = "convites"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["empresa", "-criado_em"])]

    def __str__(self):
        return f"convite de {self.empresa.nome} ({self.email or 'sem e-mail'})"

    @property
    def usado(self) -> bool:
        return self.usado_em is not None

    @property
    def expirado(self) -> bool:
        return self.expira_em <= timezone.now()

    @property
    def valido(self) -> bool:
        """Convite usado ou expirado não aceita mais ninguém."""
        return not self.usado and not self.expirado


class Chamado(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="chamados")
    codigo = models.CharField(max_length=20)  # D-0042
    assunto = models.CharField(max_length=500)
    cliente_nome = models.CharField(max_length=200, blank=True)
    cliente_email = models.EmailField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    arquivado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "chamado"
        verbose_name_plural = "chamados"
        constraints = [
            models.UniqueConstraint(fields=["empresa", "codigo"], name="uniq_codigo_empresa")
        ]
        indexes = [models.Index(fields=["empresa", "-criado_em"])]

    # NÃO adicionar campo `situacao` nem `descricao`. Ver invariantes 2 e 3.

    def __str__(self):
        return f"{self.codigo} — {self.assunto}"

    @property
    def descricao(self):
        """A descrição é a Mensagem de ordem = 0. Não existe campo, e não vai existir."""
        return self.mensagens.filter(ordem=0).first()


def registros_ativos_de(chamado_ref=None):
    """Registros ainda não substituídos por versão mais nova, do mais novo ao mais velho."""
    if chamado_ref is None:
        chamado_ref = OuterRef("pk")
    return Registro.objects.filter(
        chamado=chamado_ref, versao_seguinte__isnull=True
    ).order_by("-criado_em")


def chamados_com_situacao(qs=None):
    """Projeção da situação (invariante 3). Uma consulta só — nada de N+1."""
    qs = Chamado.objects.all() if qs is None else qs
    ultimo = registros_ativos_de()
    return qs.annotate(
        situacao=Subquery(ultimo.values("situacao")[:1]),
        ultimo_autor=Subquery(ultimo.values("autor__nome")[:1]),
        ultimo_setor=Subquery(ultimo.values("setor")[:1]),
        ultima_atualizacao=Subquery(ultimo.values("criado_em")[:1]),
        total_registros=Count(
            "registros",
            filter=Q(registros__versao_seguinte__isnull=True),
            distinct=True,
        ),
    )


def situacao_de(chamado) -> "str | None":
    """Situação projetada de um chamado só. `None` quando não há nenhum registro."""
    ultimo = (
        Registro.objects.filter(chamado=chamado, versao_seguinte__isnull=True)
        .order_by("-criado_em")
        .values_list("situacao", flat=True)
        .first()
    )
    return ultimo


class Mensagem(models.Model):
    """Palavras do cliente, como chegaram por e-mail. IMUTÁVEL.

    Não existe campo de canal: e-mail é a única origem possível (invariante 7).
    """

    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="mensagens")
    ordem = models.PositiveIntegerField()
    remetente = models.CharField(max_length=320, blank=True)
    destinatario = models.CharField(max_length=320, blank=True)
    assunto = models.CharField(max_length=500, blank=True)
    recebido_em = models.DateTimeField()

    bruto = models.BinaryField()  # MIME cru, exatamente como chegou
    texto = models.TextField()  # normalizado (seção 6)
    norm_v = models.PositiveIntegerField()  # versão da função de normalização
    sha256 = models.CharField(max_length=64)
    citacao_offset = models.IntegerField(null=True, blank=True)  # início do trecho citado, ou None

    message_id = models.CharField(max_length=998, blank=True)
    search = SearchVectorField(null=True)  # django.contrib.postgres.search

    class Meta:
        verbose_name = "mensagem"
        verbose_name_plural = "mensagens"
        ordering = ["ordem"]
        constraints = [
            models.UniqueConstraint(fields=["chamado", "ordem"], name="uniq_ordem_chamado"),
            models.UniqueConstraint(
                fields=["chamado", "message_id"],
                name="uniq_msgid_chamado",
                condition=~models.Q(message_id=""),
            ),
        ]
        indexes = [GinIndex(fields=["search"])]

    def __str__(self):
        return f"{self.chamado_id}#{self.ordem} de {self.remetente}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Mensagem é imutável: não pode ser alterada depois de criada.")
        if not getattr(self, "_via_ingest", False):
            # Invariante 7: a única origem é o ingest de e-mail. Nenhuma tela, endpoint,
            # serializer ou ação de admin cria mensagem a partir de texto digitado.
            raise ValidationError(
                "Mensagem só pode ser criada pelo ingest de e-mail "
                "(ingest.entrada.gravar_mensagem). Ninguém digita a descrição de um chamado."
            )
        self.sha256 = hashlib.sha256(self.texto.encode("utf-8")).hexdigest()
        self.search = SearchVector(Value(self.texto), config="portuguese")
        super().save(*args, **kwargs)
        # O objeto de expressão não serve de valor em memória; o banco já tem o tsvector.
        self.search = None

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Mensagem não pode ser apagada. Exclusão só em cascata, apagando o chamado inteiro."
        )

    @property
    def texto_proprio(self) -> str:
        """Só o que o cliente escreveu agora. O trecho citado continua inteiro em `texto`."""
        if self.citacao_offset is None:
            return self.texto
        return self.texto[: self.citacao_offset]

    @property
    def texto_citado(self) -> str:
        if self.citacao_offset is None:
            return ""
        return self.texto[self.citacao_offset :]

    def trecho(self, limite: int = 140) -> str:
        """Primeiros ~limite caracteres, cortados em palavra. Para a lista de chamados."""
        return trecho_em_palavra(self.texto_proprio.strip() or self.texto.strip(), limite)


def trecho_em_palavra(texto: str, limite: int = 140) -> str:
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    if espaco > limite // 2:
        corte = corte[:espaco]
    return corte.rstrip(" .,;:") + "…"


class Anexo(models.Model):
    mensagem = models.ForeignKey(Mensagem, on_delete=models.CASCADE, related_name="anexos")
    nome = models.CharField(max_length=300)
    mime = models.CharField(max_length=180)
    arquivo = models.FileField(upload_to="anexos/%Y/%m/")
    sha256 = models.CharField(max_length=64)

    class Meta:
        verbose_name = "anexo"
        verbose_name_plural = "anexos"

    def __str__(self):
        return self.nome


class Registro(models.Model):
    """O que um setor fez. Acrescenta, nunca substitui."""

    chamado = models.ForeignKey(Chamado, on_delete=models.CASCADE, related_name="registros")
    autor = models.ForeignKey(Pessoa, on_delete=models.PROTECT)
    setor = models.CharField(max_length=80)  # copiado da pessoa no momento da escrita
    texto = models.TextField()
    situacao = models.CharField(max_length=30, choices=SITUACOES)
    criado_em = models.DateTimeField(auto_now_add=True)
    editado_em = models.DateTimeField(null=True, blank=True)
    versao_anterior = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="versao_seguinte",
    )
    search = SearchVectorField(null=True)

    class Meta:
        verbose_name = "registro"
        verbose_name_plural = "registros"
        ordering = ["criado_em"]
        indexes = [models.Index(fields=["chamado", "criado_em"]), GinIndex(fields=["search"])]

    def __str__(self):
        return f"{self.setor} · {self.get_situacao_display()}"

    def save(self, *args, **kwargs):
        self.search = SearchVector(Value(self.texto), config="portuguese")
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "search" not in update_fields:
            kwargs["update_fields"] = list(update_fields) + ["search"]
        super().save(*args, **kwargs)
        self.search = None


@transaction.atomic
def abrir_chamado(
    *, empresa: Empresa, assunto: str, cliente_nome: str = "", cliente_email: str = ""
) -> Chamado:
    """Cria o chamado já com o `codigo` sequencial da empresa. Sempre em transação."""
    return Chamado.objects.create(
        empresa=empresa,
        codigo=empresa.novo_codigo(),
        assunto=(assunto or "(sem assunto)")[:500],
        cliente_nome=(cliente_nome or "")[:200],
        cliente_email=cliente_email[:254] if "@" in (cliente_email or "") else "",
    )


# ------------------------------------------------------------------ caixa de entrada

SITUACOES_EMAIL = [
    ("pendente", "Pendente"),
    ("promovido", "Promovido a chamado"),
    ("descartado", "Descartado"),
]

SITUACOES_EMAIL_VALIDAS = {chave for chave, _ in SITUACOES_EMAIL}

#: O que veio do cliente. Depois de gravado, nunca sofre UPDATE — só os campos de
#: situação mudam. Ver `EmailRecebido.save`.
CONTEUDO_DO_EMAIL = (
    "message_id",
    "recebido_em",
    "remetente_nome",
    "remetente_email",
    "destinatario",
    "assunto",
    "bruto",
    "texto",
    "norm_v",
    "sha256",
    "citacao_offset",
)


class EmailRecebido(models.Model):
    """Um e-mail lido da caixa da empresa, antes de qualquer decisão humana.

    Entre a caixa e o chamado existe esta etapa: **todo** e-mail lido é gravado aqui,
    e um humano decide quais viram chamado. O humano escolhe **qual** e-mail vira
    chamado — nunca **o que** está escrito nele.

    Nunca é apagado: promover e descartar só carimbam campos de situação.
    """

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="emails")
    message_id = models.CharField(max_length=998)
    recebido_em = models.DateTimeField()  # do cabeçalho Date
    lido_em = models.DateTimeField(auto_now_add=True)  # quando o ingest gravou

    remetente_nome = models.CharField(max_length=200, blank=True)
    remetente_email = models.CharField(max_length=320)
    destinatario = models.CharField(max_length=320, blank=True)
    assunto = models.CharField(max_length=500, blank=True)
    refs = ArrayField(models.TextField(), default=list, blank=True)  # In-Reply-To + References

    bruto = models.BinaryField()  # MIME cru, como veio (invariante 5)
    texto = models.TextField()  # normalizado, NORM_V
    norm_v = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    citacao_offset = models.IntegerField(null=True, blank=True)

    situacao = models.CharField(max_length=20, choices=SITUACOES_EMAIL, default="pendente")
    promovido_em = models.DateTimeField(null=True, blank=True)
    #: NULL com `situacao='promovido'` significa promovido pelo sistema: resposta dentro
    #: de uma conversa que alguém já tinha aceitado como chamado.
    promovido_por = models.ForeignKey(
        Pessoa, null=True, blank=True, on_delete=models.PROTECT, related_name="emails_promovidos"
    )
    chamado = models.ForeignKey(
        Chamado,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,  # apagar o chamado não apaga o e-mail que o originou
        related_name="emails_recebidos",
    )
    descartado_em = models.DateTimeField(null=True, blank=True)
    descartado_por = models.ForeignKey(
        Pessoa, null=True, blank=True, on_delete=models.PROTECT, related_name="emails_descartados"
    )

    class Meta:
        verbose_name = "e-mail recebido"
        verbose_name_plural = "e-mails recebidos"
        ordering = ["-recebido_em", "-id"]
        constraints = [
            # A dedupe do ingest. Substitui a checagem contra `mensagem.message_id`.
            models.UniqueConstraint(fields=["empresa", "message_id"], name="uniq_msgid_empresa")
        ]
        indexes = [models.Index(fields=["empresa", "situacao", "-recebido_em"])]

    def __str__(self):
        return f"{self.remetente_email} — {self.assunto or '(sem assunto)'}"

    # -- imutabilidade do conteúdo ------------------------------------------------

    @classmethod
    def from_db(cls, db, field_names, values):
        objeto = super().from_db(db, field_names, values)
        presentes = set(field_names)
        objeto._conteudo_original = {
            campo: getattr(objeto, campo) for campo in CONTEUDO_DO_EMAIL if campo in presentes
        }
        return objeto

    def _conteudo_alterado(self) -> list[str]:
        original = getattr(self, "_conteudo_original", None)
        if not original:
            return []
        mudados = []
        for campo, antes in original.items():
            agora = getattr(self, campo)
            if isinstance(antes, memoryview):
                antes = bytes(antes)
            if isinstance(agora, memoryview):
                agora = bytes(agora)
            if antes != agora:
                mudados.append(campo)
        return mudados

    def save(self, *args, **kwargs):
        if self.pk is None:
            # O mesmo cálculo da `Mensagem`: por construção, o sha256 do e-mail e o da
            # mensagem promovida são o mesmo número.
            self.sha256 = hashlib.sha256(self.texto.encode("utf-8")).hexdigest()
        else:
            mudados = self._conteudo_alterado()
            if mudados:
                raise ValidationError(
                    "E-mail recebido é imutável no conteúdo; alterados: "
                    + ", ".join(sorted(mudados))
                    + ". Só os campos de situação mudam."
                )
        super().save(*args, **kwargs)
        self._conteudo_original = {campo: getattr(self, campo) for campo in CONTEUDO_DO_EMAIL}

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "E-mail recebido não é apagado. Descartar carimba `descartado_em` e o "
            "registro continua no banco e continua consultável."
        )

    # -- leitura -------------------------------------------------------------------

    @property
    def remetente(self) -> str:
        if self.remetente_nome and self.remetente_email:
            return f"{self.remetente_nome} <{self.remetente_email}>"
        return self.remetente_email or self.remetente_nome

    @property
    def texto_proprio(self) -> str:
        if self.citacao_offset is None:
            return self.texto
        return self.texto[: self.citacao_offset]

    def trecho(self, limite: int = 140) -> str:
        return trecho_em_palavra(self.texto_proprio.strip() or self.texto.strip(), limite)

    def confere_sha256(self) -> bool:
        """O texto gravado ainda bate com o número gravado? Checado antes de promover."""
        return hashlib.sha256(self.texto.encode("utf-8")).hexdigest() == self.sha256


class AnexoRecebido(models.Model):
    """Anexo de um e-mail da caixa. Copiado para `Anexo` quando o e-mail é promovido."""

    email = models.ForeignKey(EmailRecebido, on_delete=models.CASCADE, related_name="anexos")
    nome = models.CharField(max_length=300)
    mime = models.CharField(max_length=180)
    arquivo = models.FileField(upload_to="recebidos/%Y/%m/")
    sha256 = models.CharField(max_length=64)

    class Meta:
        verbose_name = "anexo recebido"
        verbose_name_plural = "anexos recebidos"

    def __str__(self):
        return self.nome
