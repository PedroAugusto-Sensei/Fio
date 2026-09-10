"""Dados de demonstração (seção 11).

Reproduz a lista do protótipo: 7 chamados, dois deles sem nenhum registro e um bloqueado.
Todo o conteúdo é Lorem Ipsum de propósito — nada que pareça caso de empresa real.

Os e-mails são gerados como MIME de verdade e entram por `ingest.entrada.receber_email`
seguido de `promover`, o mesmo caminho do ingest IMAP — a única origem de uma `Mensagem`
(invariante 7). Não existe entrada manual: é o seed que cobre a demonstração quando não
há caixa IMAP.

Três e-mails ficam de propósito na caixa de entrada, sem virar chamado: um pedido de
verdade, uma resposta automática de férias e uma newsletter. É o que a tela da caixa
existe para separar — e é a razão de a decisão ser humana.
"""
from datetime import timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    AnexoRecebido,
    Chamado,
    EmailRecebido,
    Empresa,
    Mensagem,
    Pessoa,
    Registro,
)
from ingest.entrada import promover, receber_email, salvar_anexos_recebidos

SENHA_DEMO = "fio12345"

EMPRESA_NOME = "Sua Empresa"
# A caixa que o Fio lê. Ninguém encaminha nada para o Fio.
CAIXA_EMPRESA = "atendimento@suaempresa.com.br"
SETORES = ["Suporte", "Produto", "Desenvolvimento", "QA", "Implantação"]

# (username, nome, setor, papel). Cada pessoa tem conta própria: é `Registro.autor`
# que responde "quem agiu", e com login compartilhado o feed viraria ficção.
# Autor 1 é o admin da demonstração — quem convida e edita a lista de setores.
PESSOAS = [
    ("autor.1", "Autor 1", "Suporte", "admin"),
    ("autor.2", "Autor 2", "Produto", "membro"),
    ("autor.3", "Autor 3", "Desenvolvimento", "membro"),
    ("autor.4", "Autor 4", "QA", "membro"),
    ("autor.5", "Autor 5", "Implantação", "membro"),
]

CLIENTES = {
    "Cliente A": ("Contato A", "contato@clientea.com"),
    "Cliente B": ("Contato B", "contato@clienteb.com"),
    "Cliente C": ("Contato C", "contato@clientec.com"),
    "Cliente D": ("Contato D", "contato@cliented.com"),
}

CORPO_0042 = """Lorem ipsum dolor sit amet, consectetur adipiscing elit.

Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.

Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.

Sed ut perspiciatis unde omnis iste natus error sit voluptatem.

--
Contato A
Cliente A
"""

RESPOSTA_1_0042 = """Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.

Em 21/08/2026, Contato A escreveu:
> Lorem ipsum dolor sit amet, consectetur adipiscing elit.
> Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
"""

RESPOSTA_2_0042 = """Neque porro quisquam est qui dolorem ipsum quia dolor sit amet.

Em 26/08/2026, Contato A escreveu:
> Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit.
"""

# (codigo, assunto, cliente, corpo, dias_atras, horas_atras)
CHAMADOS = [
    (
        "D-0042",
        "Lorem ipsum dolor sit amet",
        "Cliente A",
        CORPO_0042,
        19,
        0,
    ),
    (
        "D-0052",
        "Ut enim ad minim veniam",
        "Cliente B",
        "Quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.\n\n"
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.\n",
        0,
        3,
    ),
    (
        "D-0051",
        "Duis aute irure dolor",
        "Cliente C",
        "In reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.\n\n"
        "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt.\n",
        0,
        1,
    ),
    (
        "D-0038",
        "Excepteur sint occaecat",
        "Cliente B",
        "Cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.\n\n"
        "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium.\n",
        6,
        0,
    ),
    (
        "D-0031",
        "Sed ut perspiciatis unde omnis",
        "Cliente D",
        "Iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam.\n\n"
        "Eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt.\n",
        11,
        0,
    ),
    (
        "D-0027",
        "Nemo enim ipsam voluptatem",
        "Cliente A",
        "Quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores.\n\n"
        "Eos qui ratione voluptatem sequi nesciunt, neque porro quisquam est qui dolorem.\n",
        22,
        0,
    ),
    (
        "D-0036",
        "At vero eos et accusamus",
        "Cliente D",
        "Et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque.\n\n"
        "Corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident.\n",
        9,
        0,
    ),
]

# codigo -> [(dias_atras, username, setor, situacao, texto)]
REGISTROS = {
    "D-0042": [
        (19, "autor.1", "Suporte", "concluido",
         "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua, ut enim ad minim veniam."),
        (17, "autor.2", "Produto", "concluido",
         "Quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
         "Duis aute irure dolor in reprehenderit in voluptate velit esse."),
        (11, "autor.3", "Desenvolvimento", "em_andamento",
         "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt "
         "mollit anim id est laborum."),
        (1, "autor.3", "Desenvolvimento", "em_andamento",
         "Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia "
         "consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt."),
    ],
    "D-0038": [
        (6, "autor.1", "Suporte", "em_andamento",
         "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque "
         "laudantium, totam rem aperiam."),
        (5, "autor.4", "QA", "concluido",
         "Eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta "
         "sunt explicabo."),
    ],
    "D-0031": [
        (11, "autor.1", "Suporte", "em_andamento",
         "Neque porro quisquam est qui dolorem ipsum quia dolor sit amet, consectetur, adipisci "
         "velit, sed quia non numquam eius modi tempora."),
        (4, "autor.2", "Produto", "bloqueado",
         "Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit "
         "laboriosam, nisi ut aliquid ex ea commodi consequatur."),
    ],
    "D-0027": [
        (22, "autor.1", "Suporte", "em_andamento",
         "Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil "
         "molestiae consequatur."),
        (12, "autor.5", "Desenvolvimento", "duvida_cliente",
         "Vel illum qui dolorem eum fugiat quo voluptas nulla pariatur. At vero eos et "
         "accusamus et iusto odio dignissimos ducimus."),
    ],
    "D-0036": [
        (9, "autor.1", "Suporte", "em_andamento",
         "Qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas "
         "molestias excepturi sint occaecati cupiditate non provident."),
        (2, "autor.2", "Implantação", "concluido",
         "Similique sunt in culpa qui officia deserunt mollitia animi, id est laborum et dolorum "
         "fuga. Et harum quidem rerum facilis est et expedita distinctio."),
    ],
}

# Ficam na caixa de entrada, sem virar chamado. Dois deles nunca deveriam virar:
# é exatamente por isso que existe alguém decidindo.
PENDENTES = [
    (
        "Contato B",
        "contato@clienteb.com",
        "Dúvida sobre o relatório mensal",
        "Bom dia,\n\n"
        "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis "
        "praesentium voluptatum deleniti atque corrupti quos dolores.\n\n"
        "Consegue confirmar até sexta?\n\n--\nContato B\nCliente B\n",
        0,
        3,
    ),
    (
        "Contato D",
        "contato@cliented.com",
        "Resposta automática: Ausente até 20/09",
        "Estou de férias até 20/09 com acesso limitado ao e-mail.\n\n"
        "Em caso de urgência, procure a equipe pelo telefone do escritório.\n",
        1,
        2,
    ),
    (
        "Boletim Lorem",
        "noticias@boletim-lorem.example",
        "Lorem Ipsum Semanal — 12 novidades desta semana",
        "Sed ut perspiciatis unde omnis iste natus error sit voluptatem.\n\n"
        "Para deixar de receber, clique aqui.\n",
        2,
        6,
    ),
]

XLSX_FALSO = (
    b"PK\x03\x04lorem-ipsum-planilha-de-demonstracao-sem-conteudo-real\n"
)


def monta_email(*, de_nome, de_email, assunto, corpo, quando, in_reply_to=None, references=None):
    """Monta um MIME de verdade, para o seed passar pelo mesmo caminho do ingest."""
    msg = EmailMessage()
    msg["From"] = f"{de_nome} <{de_email}>"
    msg["To"] = CAIXA_EMPRESA
    msg["Subject"] = assunto
    msg["Date"] = format_datetime(quando)
    msg["Message-ID"] = make_msgid(domain="clientes.fio.app")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = " ".join(references or [in_reply_to])
    msg.set_content(corpo)
    return msg


class Command(BaseCommand):
    help = "Cria a empresa, as pessoas e os chamados de demonstração."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Apaga os chamados da empresa de demonstração antes de recriar.",
        )

    @transaction.atomic
    def handle(self, *args, **opcoes):
        agora = timezone.now()

        empresa, criada = Empresa.objects.get_or_create(
            caixa_email=CAIXA_EMPRESA,
            defaults={"nome": EMPRESA_NOME, "setores": SETORES},
        )
        if not criada:
            empresa.nome = EMPRESA_NOME
            empresa.setores = SETORES
            empresa.save(update_fields=["nome", "setores"])

        if opcoes["limpar"]:
            apagados = Chamado.objects.filter(empresa=empresa).count()
            Chamado.objects.filter(empresa=empresa).delete()  # cascata, invariante 6
            # Recriar a demonstração é jogar fora a demonstração inteira, e-mails
            # incluídos. Nenhuma operação do produto apaga `EmailRecebido` — esta é
            # a faxina do seed, não promoção nem descarte.
            recebidos = EmailRecebido.objects.filter(empresa=empresa).count()
            EmailRecebido.objects.filter(empresa=empresa).delete()
            self.stdout.write(
                f"{apagados} chamado(s) e {recebidos} e-mail(s) da demonstração apagados."
            )

        pessoas = {}
        for username, nome, setor, papel in PESSOAS:
            user, _ = User.objects.get_or_create(
                username=username, defaults={"first_name": nome}
            )
            user.set_password(SENHA_DEMO)
            user.is_staff = True
            user.save()
            pessoa, _ = Pessoa.objects.update_or_create(
                user=user,
                defaults={
                    "empresa": empresa,
                    "nome": nome,
                    "setor": setor,
                    "papel": papel,
                },
            )
            pessoas[username] = pessoa

        admin, _ = User.objects.get_or_create(
            username="admin", defaults={"is_staff": True, "is_superuser": True}
        )
        admin.is_staff = admin.is_superuser = True
        admin.set_password(SENHA_DEMO)
        admin.save()
        Pessoa.objects.update_or_create(
            user=admin,
            defaults={
                "empresa": empresa,
                "nome": "Administração",
                "setor": "Suporte",
                "papel": "admin",
            },
        )

        if Chamado.objects.filter(empresa=empresa).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Já existem chamados nesta empresa. Use --limpar para recriar a demonstração."
                )
            )
            return

        maior_numero = 0
        for codigo, assunto, cliente, corpo, dias, horas in CHAMADOS:
            quando = agora - timedelta(days=dias, hours=horas)
            contato, email_cliente = CLIENTES[cliente]
            maior_numero = max(maior_numero, int(codigo.split("-")[1]))

            chamado = Chamado.objects.create(
                empresa=empresa,
                codigo=codigo,
                assunto=assunto,
                cliente_nome=cliente,
                cliente_email=email_cliente,
            )
            Chamado.objects.filter(pk=chamado.pk).update(criado_em=quando)
            chamado.refresh_from_db()

            msg = monta_email(
                de_nome=contato,
                de_email=email_cliente,
                assunto=assunto,
                corpo=corpo,
                quando=quando,
            )
            recebido = self._receber(
                empresa, msg, contato=contato, email_cliente=email_cliente, quando=quando
            )
            if codigo == "D-0042":
                self._anexo(recebido)

            # Alguém olhou a caixa e decidiu que este e-mail era um chamado.
            promover(recebido, chamado=chamado, por=pessoas["autor.1"])

            if codigo == "D-0042":
                self._respostas_0042(
                    empresa, chamado, contato, email_cliente, assunto, msg, agora
                )

            for dias_atras, username, setor, situacao, texto_reg in REGISTROS.get(codigo, []):
                registro = Registro.objects.create(
                    chamado=chamado,
                    autor=pessoas[username],
                    setor=setor,
                    texto=texto_reg,
                    situacao=situacao,
                )
                Registro.objects.filter(pk=registro.pk).update(
                    criado_em=agora - timedelta(days=dias_atras)
                )

        for contato, email_cliente, assunto, corpo, dias, horas in PENDENTES:
            quando = agora - timedelta(days=dias, hours=horas)
            msg = monta_email(
                de_nome=contato,
                de_email=email_cliente,
                assunto=assunto,
                corpo=corpo,
                quando=quando,
            )
            # Só `receber_email`: nada de `promover`. Fica pendente, esperando decisão.
            self._receber(
                empresa, msg, contato=contato, email_cliente=email_cliente, quando=quando
            )

        Empresa.objects.filter(pk=empresa.pk).update(proximo_numero=maior_numero + 1)

        sem_registro = [
            c.codigo
            for c in Chamado.objects.filter(empresa=empresa)
            if not c.registros.exists()
        ]
        self.stdout.write(
            self.style.SUCCESS(
                f"Pronto: {Chamado.objects.filter(empresa=empresa).count()} chamados, "
                f"{Mensagem.objects.filter(chamado__empresa=empresa).count()} mensagens, "
                f"{Registro.objects.filter(chamado__empresa=empresa).count()} registros.\n"
                f"Sem nenhum registro (de propósito): {', '.join(sem_registro)}\n"
                f"Na caixa de entrada, esperando decisão: "
                f"{EmailRecebido.objects.filter(empresa=empresa, situacao='pendente').count()}\n"
                f"Entre com autor.1 … autor.5 (ou admin) e a senha {SENHA_DEMO}.\n"
                f"Caixa lida pelo ingest: {CAIXA_EMPRESA} › {settings.IMAP_FOLDER or 'INBOX'}"
            )
        )

    def _receber(self, empresa, msg, *, contato, email_cliente, quando, refs=()):
        """Faz o e-mail entrar pela caixa, exatamente como o ingest faria."""
        return receber_email(
            empresa=empresa,
            bruto=msg.as_bytes(),
            message_id=msg["Message-ID"],
            remetente_nome=contato,
            remetente_email=email_cliente,
            destinatario=CAIXA_EMPRESA,
            assunto=msg["Subject"],
            recebido_em=quando,
            refs=list(refs),
        )

    def _anexo(self, recebido):
        """O anexo entra no e-mail; a promoção o copia para a mensagem."""

        class _AnexoFalso:
            filename = "lorem-ipsum.xlsx"
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            payload = XLSX_FALSO

        salvar_anexos_recebidos(recebido, [_AnexoFalso()])

    def _respostas_0042(
        self, empresa, chamado, contato, email_cliente, assunto, primeiro, agora
    ):
        """Duas respostas do cliente na mesma conversa — cada uma entra inteira.

        Resposta dentro de conversa que já é chamado entra direto, sem passar pela
        caixa de entrada: `promovido_por=None` é o sistema, não uma pessoa.
        """
        anterior = primeiro
        referencias = [primeiro["Message-ID"]]
        for corpo, dias, horas, minutos in (
            (RESPOSTA_1_0042, 14, 14, 31),
            (RESPOSTA_2_0042, 7, 10, 4),
        ):
            # Hora marcada no fuso local: o protótipo mostra 14:31 e 10:04.
            local = timezone.localtime(agora - timedelta(days=dias))
            quando = local.replace(hour=horas, minute=minutos, second=0, microsecond=0)
            resposta = monta_email(
                de_nome=contato,
                de_email=email_cliente,
                assunto=f"Re: {assunto}",
                corpo=corpo,
                quando=quando,
                in_reply_to=anterior["Message-ID"],
                references=referencias,
            )
            recebido = self._receber(
                empresa,
                resposta,
                contato=contato,
                email_cliente=email_cliente,
                quando=quando,
                refs=referencias,
            )
            promover(recebido, chamado=chamado, por=None)
            referencias.append(resposta["Message-ID"])
            anterior = resposta
