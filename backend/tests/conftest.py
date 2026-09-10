"""Fixtures compartilhadas.

Um Postgres de verdade é obrigatório: o produto usa SearchVectorField e índices GIN,
e testar em outro banco não provaria nada.

Não há atalho para criar `Mensagem` nos testes: tudo entra como `EmailRecebido` e só
vira mensagem por promoção, porque é o único caminho que existe no produto (invariante 7).
"""
import pathlib
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Empresa, Pessoa

SENHA = "teste12345"
CAIXA_EMPRESA = "atendimento@suaempresa.com.br"
FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def eml(nome: str) -> bytes:
    """Lê um e-mail de verdade do diretório de fixtures, em bytes crus."""
    return (FIXTURES / nome).read_bytes()


class AnexoFalso:
    """Mesma superfície do anexo do imap_tools."""

    def __init__(self, filename, payload, content_type="application/octet-stream"):
        self.filename = filename
        self.payload = payload
        self.content_type = content_type


class MensagemFalsa:
    """Imita `imap_tools.MailMessage` — o suficiente para exercitar o ingest sem IMAP.

    Construída a partir do MIME cru, do mesmo jeito que o imap_tools faz.
    """

    def __init__(self, mime, uid="1", attachments=()):
        if isinstance(mime, (bytes, bytearray)):
            import email
            import email.policy

            mime = email.message_from_bytes(bytes(mime), policy=email.policy.compat32)
        self.obj = mime
        self.uid = uid
        self.attachments = list(attachments)
        self.subject = mime["Subject"] or ""
        self.from_ = mime["From"] or ""
        self.to = [t.strip() for t in (mime["To"] or "").split(",") if t.strip()]
        self.date = timezone.now()
        self.headers = {}
        for chave, valor in mime.items():
            self.headers.setdefault(chave.lower(), ())
            self.headers[chave.lower()] += (valor,)


def monta_mime(
    *,
    assunto,
    corpo,
    de="Contato A <contato@clientea.com>",
    para=CAIXA_EMPRESA,
    in_reply_to=None,
    references=None,
    message_id=None,
    reply_to=None,
):
    """MIME montado na hora, para os casos que não valem um arquivo de fixture."""
    msg = EmailMessage()
    msg["From"] = de
    msg["To"] = para
    msg["Subject"] = assunto
    msg["Date"] = format_datetime(timezone.now())
    msg["Message-ID"] = message_id or make_msgid(domain="teste.fio")
    if reply_to:
        msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = " ".join(references or [in_reply_to])
    msg.set_content(corpo)
    return msg


@pytest.fixture
def empresa(db):
    return Empresa.objects.create(
        nome="Empresa de Teste",
        caixa_email=CAIXA_EMPRESA,
        setores=["Suporte", "Produto", "Desenvolvimento"],
    )


@pytest.fixture
def pessoa(empresa):
    """Quem cadastrou a empresa: papel de admin, como em `registrar-empresa`."""
    user = User.objects.create_user(username="autor.1", password=SENHA)
    return Pessoa.objects.create(
        user=user, empresa=empresa, nome="Autor 1", setor="Suporte", papel="admin"
    )


@pytest.fixture
def outra_pessoa(empresa):
    """Membro comum: lê tudo e publica registro, mas não convida nem edita setores."""
    user = User.objects.create_user(username="autor.2", password=SENHA)
    return Pessoa.objects.create(
        user=user, empresa=empresa, nome="Autor 2", setor="Produto", papel="membro"
    )


@pytest.fixture
def cliente_logado(client, pessoa):
    assert client.login(username="autor.1", password=SENHA)
    return client


# -- duas empresas -------------------------------------------------------------------
#
# O escopo por empresa só se prova com duas empresas no banco. Com uma só, um
# `.filter()` esquecido passa despercebido e o vazamento aparece em produção.


@pytest.fixture
def outra_empresa(db):
    return Empresa.objects.create(
        nome="Empresa Vizinha",
        caixa_email="atendimento@empresavizinha.com.br",
        setores=["Suporte", "Financeiro"],
    )


@pytest.fixture
def pessoa_vizinha(outra_empresa):
    user = User.objects.create_user(username="vizinha.1", password=SENHA)
    return Pessoa.objects.create(
        user=user, empresa=outra_empresa, nome="Vizinha 1", setor="Suporte", papel="admin"
    )


@pytest.fixture
def cliente_vizinho(pessoa_vizinha):
    """Sessão própria: duas sessões abertas ao mesmo tempo, uma por empresa."""
    from django.test import Client

    outro = Client()
    assert outro.login(username="vizinha.1", password=SENHA)
    return outro


@pytest.fixture
def receber(empresa):
    """Faz um e-mail entrar pela caixa, como o ingest faria. Devolve o EmailRecebido.

    O ingest só grava: quem decide se vira chamado é gente (ou, nas respostas de uma
    conversa que já é chamado, o próprio ingest).
    """
    from ingest.management.commands.ingest_email import Command

    def _receber(mime, anexos=(), empresa_alvo=None):
        alvo = empresa_alvo or empresa
        recebido, _criado = Command().ingerir(alvo, MensagemFalsa(mime, attachments=anexos))
        recebido.refresh_from_db()
        return recebido

    return _receber


@pytest.fixture
def promovido(receber):
    """Recebe um e-mail e promove, como quem clica em "Criar chamado". Devolve o chamado."""
    from ingest.entrada import promover

    def _promovido(mime, anexos=(), por=None):
        return promover(receber(mime, anexos=anexos), por=por)

    return _promovido


@pytest.fixture
def chamado(promovido):
    """Um chamado nascido de um e-mail de verdade, com a mensagem de ordem 0."""
    return promovido(eml("simples.eml"))
