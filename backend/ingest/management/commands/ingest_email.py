"""Entrada de e-mail. É a única origem de um `EmailRecebido` — e, por ele, de uma `Mensagem`.

Cron a cada minuto:
    */1 * * * * cd /app/backend && python manage.py ingest_email

A empresa é a **dona da caixa de onde o e-mail veio**: resolvida por `caixa_email`
contra o endereço que o ingest leu (`IMAP_USER`). Nunca `Empresa.objects.first()` —
com mais de uma empresa no banco, `first()` faria o e-mail de um cliente entrar na
empresa errada.

A leitura é sempre da caixa de e-mail da empresa. Os três modos de instalação são
**só configuração**, não caminhos de código diferentes:

- pasta observada (padrão em produção):  IMAP_FOLDER="Demandas"
- caixa inteira (demonstração):          IMAP_FOLDER="INBOX"
- encaminhamento automático:             o servidor da empresa reencaminha para a
  caixa lida; o remetente real sai do `From` original ou do `Reply-To`, nunca do
  envelope (`Return-Path`). Ver `ingest.entrada.remetente_real`.

O destino de cada e-mail lido:

- **abre conversa nova** → fica na caixa de entrada do Fio, `pendente`, esperando
  alguém decidir. O ingest **não** cria chamado nem mensagem;
- **responde uma conversa que já virou chamado** → entra direto no chamado, sem
  clique. Sem isso, cada follow-up de cliente pediria uma decisão e a caixa de
  entrada do Fio viraria uma segunda caixa de e-mail para varrer todo dia.

Uma transação por mensagem, e a marcação de lida vem **depois** do commit. Se falhar,
o e-mail continua não lido e volta na próxima rodada. O comando nunca derruba o
processo por causa de uma mensagem ruim nem por causa do servidor fora do ar.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import EmailRecebido, Empresa
from ingest.caixa import CaixaIndisponivel, LeitorDeCaixa, leitor_do_ambiente, leitor_da_empresa
from ingest.entrada import (
    chamado_da_thread,
    ids_de,
    ja_recebido,
    promover,
    receber_email,
    remetente_real,
    salvar_anexos_recebidos,
)

log = logging.getLogger("fio.ingest")


class Command(BaseCommand):
    help = "Lê a caixa de e-mail da empresa e grava cada mensagem como e-mail recebido."

    def add_arguments(self, parser):
        parser.add_argument(
            "--empresa",
            type=int,
            default=None,
            help="ID da empresa. Sem isso, a empresa é a dona da caixa lida (IMAP_USER).",
        )
        parser.add_argument(
            "--limite", type=int, default=100, help="Máximo de mensagens por rodada."
        )

    def handle(self, *args, **opcoes):
        configuradas = Empresa.objects.exclude(imap_host="")
        if opcoes.get("empresa"):
            configuradas = configuradas.filter(pk=opcoes["empresa"])
        if configuradas.exists():
            for empresa in configuradas:
                try:
                    with leitor_da_empresa(empresa) as leitor:
                        resumo = self.rodada(empresa, leitor, opcoes["limite"])
                    self.stdout.write(f"{empresa.caixa_email}: {resumo}")
                except Exception:
                    log.warning("Não foi possível ler a caixa da empresa %s.", empresa.pk)
            if opcoes.get("empresa") or not settings.IMAP_HOST:
                return
            if not Empresa.objects.filter(caixa_email__iexact=settings.IMAP_USER, imap_host="").exists():
                return
        try:
            leitor = leitor_do_ambiente()
        except CaixaIndisponivel as exc:
            raise CommandError(str(exc)) from exc

        # A empresa sai da caixa de onde o e-mail veio, e o leitor é quem sabe qual é.
        empresa = self._empresa(opcoes.get("empresa"), leitor.usuario)

        try:
            with leitor:
                resumo = self.rodada(empresa, leitor, opcoes["limite"])
        except CaixaIndisponivel as exc:
            # Uma linha por rodada falha, não uma por tentativa, e uma só no total: o
            # cron roda a cada minuto e um servidor fora do ar não pode encher o log.
            log.warning("%s", exc)
            return

        self.stdout.write(self.style.SUCCESS(f"{leitor.usuario} › {leitor.pasta}: {resumo}"))

    def rodada(self, empresa: Empresa, leitor: LeitorDeCaixa, limite: int) -> str:
        lidas = novos = repetidos = seguindo = falhas = 0

        for msg in leitor.mensagens_nao_lidas(limite=limite):
            lidas += 1
            try:
                recebido, criado = self.ingerir(empresa, msg)
            except Exception:  # noqa: BLE001 — uma mensagem ruim não pode parar a rodada
                falhas += 1
                log.exception(
                    "Falha ao ler o e-mail %s; fica não lido para a próxima rodada.", msg.uid
                )
                continue

            if not criado:
                repetidos += 1
            elif recebido.situacao == "promovido":
                seguindo += 1
            else:
                novos += 1

            # Só agora, com a transação já comitada.
            leitor.marcar_lida(msg.uid)

        return (
            f"{lidas} e-mail(s) lidos · {novos} na caixa de entrada · "
            f"{seguindo} direto no chamado · {repetidos} repetido(s) · {falhas} falha(s)"
        )

    @transaction.atomic
    def ingerir(self, empresa: Empresa, msg):
        """Grava o e-mail. Devolve `(EmailRecebido, criado)`; `criado=False` é dedupe.

        Não cria chamado quando o e-mail abre conversa nova: quem decide isso é gente.
        """
        message_id = (msg.headers.get("message-id") or ("",))[0].strip()

        if ja_recebido(empresa, message_id):
            log.info("E-mail %s já lido antes; só marcando como lido.", message_id)
            existente = EmailRecebido.objects.get(empresa=empresa, message_id=message_id)
            return existente, False

        refs: list[str] = []
        for cabecalho in ("in-reply-to", "references"):
            for valor in msg.headers.get(cabecalho, ()):
                refs.extend(ids_de(valor))

        bruto = msg.obj.as_bytes()  # invariante 5: cru primeiro, parse depois
        nome, endereco = remetente_real(bruto, msg.headers, empresa)

        recebido = receber_email(
            empresa=empresa,
            bruto=bruto,
            message_id=message_id,
            remetente_nome=nome,
            remetente_email=endereco or msg.from_ or "",
            destinatario=", ".join(msg.to or ()),
            assunto=msg.subject or "",
            recebido_em=msg.date or timezone.now(),
            refs=refs,
        )
        salvar_anexos_recebidos(recebido, msg.attachments)

        chamado = chamado_da_thread(empresa, refs)
        if chamado is not None:
            # Continuação de uma conversa que alguém já aceitou como chamado:
            # promoção automática, sem passar pela caixa de entrada. `por=None`
            # porque quem promoveu foi o sistema, não uma pessoa.
            promover(recebido, chamado=chamado, por=None)
            recebido.refresh_from_db()

        return recebido, True

    def _empresa(self, empresa_id, caixa: str) -> Empresa:
        """A empresa dona da caixa lida. Nunca `Empresa.objects.first()`.

        Com cadastro pela interface há mais de uma empresa no banco, e escolher a
        primeira faria o e-mail de um cliente entrar na empresa de outra pessoa.
        """
        if empresa_id:
            try:
                return Empresa.objects.get(pk=empresa_id)
            except Empresa.DoesNotExist as exc:
                raise CommandError(f"Empresa {empresa_id} não existe.") from exc

        caixa = (caixa or "").strip()
        if not caixa:
            raise CommandError(
                "IMAP_USER não configurado: sem ele não há como saber de quem é a caixa."
            )

        empresa = Empresa.objects.filter(caixa_email__iexact=caixa).first()
        if empresa is None:
            raise CommandError(
                f"Nenhuma empresa lê a caixa {caixa}. Preencha `caixa_email` da empresa "
                "com o endereço que o ingest lê (IMAP_USER), ou passe --empresa <id>."
            )
        return empresa
