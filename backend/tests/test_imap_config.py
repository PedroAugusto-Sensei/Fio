import pytest
from unittest.mock import patch
from django.core.management import call_command
from ingest.credenciais import decifrar

pytestmark = pytest.mark.django_db

DADOS = dict(host="imap.exemplo.com", usuario="caixa@exemplo.com", caixa_email="caixa@exemplo.com", pasta="Demandas", senha="segredo-imap")


def test_criador_salva_sem_expor_senha(cliente_logado, pessoa):
    empresa = pessoa.empresa
    empresa.criador = pessoa.user
    empresa.save()
    resposta = cliente_logado.put("/api/empresa/imap", DADOS, content_type="application/json")
    assert resposta.status_code == 200
    assert "segredo-imap" not in resposta.content.decode()
    assert resposta.json()["senha_configurada"] is True
    empresa.refresh_from_db()
    assert empresa.imap_senha != DADOS["senha"]
    assert decifrar(empresa.imap_senha) == DADOS["senha"]
    assert cliente_logado.get("/api/me").json()["pasta_email"] == "Demandas"
    assert cliente_logado.put("/api/empresa/imap", {**DADOS, "senha": ""}, content_type="application/json").status_code == 200
    assert cliente_logado.put("/api/empresa/imap", {**DADOS, "usuario": "outro", "senha": ""}, content_type="application/json").status_code == 400
    with patch("ingest.management.commands.ingest_email.leitor_da_empresa") as leitor:
        leitor.return_value.__enter__.return_value.mensagens_nao_lidas.return_value = []
        call_command("ingest_email", empresa=empresa.pk)
        assert leitor.call_args.args[0].pk == empresa.pk


@pytest.mark.parametrize("papel", ["admin", "membro"])
def test_nao_criador_nao_le_nem_altera(cliente_logado, pessoa, papel):
    pessoa.papel = papel
    pessoa.save()
    assert cliente_logado.get("/api/empresa/imap").status_code == 403
    assert cliente_logado.put("/api/empresa/imap", DADOS, content_type="application/json").status_code == 403


def test_sem_login(client):
    assert client.get("/api/empresa/imap").status_code == 401


def test_caixa_outra_empresa(cliente_logado, pessoa, outra_empresa):
    pessoa.empresa.criador = pessoa.user
    pessoa.empresa.save()
    dados = {**DADOS, "caixa_email": outra_empresa.caixa_email}
    assert cliente_logado.put("/api/empresa/imap", dados, content_type="application/json").status_code == 400
