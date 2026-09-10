"""A caixa de e-mail da empresa, vista pelo Fio.

O comando `ingest_email` não conhece IMAP: ele conhece `LeitorDeCaixa`. Hoje a única
implementação é `LeitorIMAP` (imap_tools). Se um dia a caixa for para a API REST do
Gmail com OAuth, entra outra implementação aqui e o comando não muda uma linha.

TLS sempre: `MailBox` é IMAP4 sobre SSL, porta 993. Não existe caminho sem criptografia.
"""
import logging
import time
from typing import Any, Iterator, Protocol

log = logging.getLogger("fio.ingest")

#: Porta IMAPS. 143 (sem STARTTLS) não é oferecida de propósito.
PORTA_TLS = 993


class CaixaIndisponivel(Exception):
    """Não deu para falar com o servidor. O cron tenta de novo no minuto seguinte."""


class LeitorDeCaixa(Protocol):
    """Superfície mínima de uma caixa de e-mail.

    Cada objeto devolvido por `mensagens_nao_lidas` expõe o que o ingest usa:
    `uid`, `obj` (a `email.message.Message` crua), `headers`, `subject`, `to`,
    `date` e `attachments`. É a superfície do `imap_tools.MailMessage`.
    """

    def mensagens_nao_lidas(self, limite: int) -> Iterator[Any]: ...

    def marcar_lida(self, uid: str) -> None: ...


class LeitorIMAP:
    """Leitura por IMAP sobre TLS, com timeout explícito e uma repetição.

    Uma falha de conexão não derruba o cron: vira `CaixaIndisponivel`, o comando
    registra **uma** linha por rodada e sai. As mensagens continuam não lidas.

    Use como context manager::

        with LeitorIMAP(host=..., usuario=..., senha=..., pasta="INBOX") as caixa:
            for msg in caixa.mensagens_nao_lidas(limite=100):
                ...
    """

    def __init__(
        self,
        *,
        host: str,
        usuario: str,
        senha: str,
        pasta: str = "INBOX",
        porta: int = PORTA_TLS,
        timeout: float = 30.0,
        espera_entre_tentativas: float = 2.0,
    ):
        self.host = host
        self.usuario = usuario
        self.senha = senha
        self.pasta = pasta or "INBOX"
        self.porta = porta
        self.timeout = timeout
        self.espera = espera_entre_tentativas
        self._caixa = None

    # -- conexão -------------------------------------------------------------------

    def __enter__(self) -> "LeitorIMAP":
        self._caixa = self._conectar()
        return self

    def __exit__(self, *_erro) -> None:
        if self._caixa is not None:
            try:
                self._caixa.logout()
            except Exception:  # noqa: BLE001 — desconectar mal não invalida a rodada
                log.debug("Falha ao encerrar a sessão IMAP; ignorado.", exc_info=True)
            self._caixa = None

    def _conectar(self):
        try:
            from imap_tools import MailBox
        except ImportError as exc:  # pragma: no cover
            raise CaixaIndisponivel("imap_tools não está instalado (pip install imap-tools).") from exc

        ultimo: Exception | None = None
        for tentativa in (1, 2):
            try:
                return MailBox(self.host, port=self.porta, timeout=self.timeout).login(
                    self.usuario, self.senha, initial_folder=self.pasta
                )
            except Exception as exc:  # noqa: BLE001 — qualquer falha vira uma repetição
                ultimo = exc
                # `debug`, não `warning`: uma rodada falha gera uma linha só, no comando.
                log.debug("Tentativa %d de conectar em %s falhou.", tentativa, self.host, exc_info=True)
                if tentativa == 1 and self.espera:
                    time.sleep(self.espera)

        raise CaixaIndisponivel(
            f"Não foi possível ler {self.usuario} › {self.pasta} em {self.host}: {ultimo}"
        ) from ultimo

    # -- leitura -------------------------------------------------------------------

    def mensagens_nao_lidas(self, limite: int = 100) -> Iterator[Any]:
        """Só `UNSEEN`. Nada é marcado como lido aqui — quem marca é `marcar_lida`."""
        from imap_tools import AND

        if self._caixa is None:  # pragma: no cover — uso fora do context manager
            raise CaixaIndisponivel("A caixa não está aberta.")
        return self._caixa.fetch(AND(seen=False), mark_seen=False, limit=limite, bulk=True)

    def marcar_lida(self, uid: str) -> None:
        """Chamado **depois** do commit. Se a transação falhar, o e-mail volta na rodada seguinte."""
        if self._caixa is None:  # pragma: no cover
            raise CaixaIndisponivel("A caixa não está aberta.")
        self._caixa.flag(uid, "\\Seen", True)


def leitor_do_ambiente(pasta: str | None = None) -> LeitorIMAP:
    """Monta o leitor a partir das variáveis de ambiente. Credencial nunca é logada."""
    from django.conf import settings

    if not settings.IMAP_HOST:
        raise CaixaIndisponivel("IMAP_HOST não configurado. Veja backend/.env.example.")

    return LeitorIMAP(
        host=settings.IMAP_HOST,
        usuario=settings.IMAP_USER,
        senha=settings.IMAP_PASSWORD,
        pasta=pasta or settings.IMAP_FOLDER or "INBOX",
        porta=int(getattr(settings, "IMAP_PORT", PORTA_TLS) or PORTA_TLS),
        timeout=float(getattr(settings, "IMAP_TIMEOUT", 30) or 30),
    )


def leitor_da_empresa(empresa):
    from .credenciais import decifrar
    return LeitorIMAP(host=empresa.imap_host, usuario=empresa.imap_usuario,
                      senha=decifrar(empresa.imap_senha), pasta=empresa.imap_pasta)
