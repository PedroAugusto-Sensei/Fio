"""A caixa de entrada do Fio e a promoção a chamado (seção 7 da tarefa).

O que está sendo protegido aqui: o humano escolhe **qual** e-mail vira chamado, e
nunca **o que** está escrito nele. Nenhum teste daqui pode passar a existir junto com
um caminho que aceite texto digitado.
"""
import hashlib
import json

import pytest
from django.core.exceptions import ValidationError

from core.models import Anexo, AnexoRecebido, Chamado, EmailRecebido, Mensagem
from ingest.entrada import JaDecidido, descartar, promover, receber_email

from .conftest import AnexoFalso, eml, monta_mime

pytestmark = pytest.mark.django_db


def post(client, url, corpo=None):
    if corpo is None:
        return client.post(url, content_type="application/json")
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


# --------------------------------------------------------------- o modelo


def test_email_recebido_e_imutavel_no_conteudo(receber):
    recebido = receber(eml("simples.eml"))
    original = recebido.texto

    recebido.texto = "texto trocado por alguém"
    with pytest.raises(ValidationError) as erro:
        recebido.save()
    assert "imutável" in str(erro.value)

    assert EmailRecebido.objects.get(pk=recebido.pk).texto == original


def test_email_recebido_nao_pode_ser_apagado(receber):
    recebido = receber(eml("simples.eml"))
    with pytest.raises(ValidationError):
        recebido.delete()
    assert EmailRecebido.objects.filter(pk=recebido.pk).exists()


def test_sha256_do_email_e_do_texto_gravado(receber):
    recebido = receber(eml("simples.eml"))
    assert recebido.sha256 == hashlib.sha256(recebido.texto.encode("utf-8")).hexdigest()
    assert recebido.confere_sha256()


# --------------------------------------------------------------- promover


def test_promover_cria_chamado_e_mensagem_ordem_zero_com_o_mesmo_sha256(receber, pessoa):
    recebido = receber(eml("simples.eml"))

    chamado = promover(recebido, por=pessoa)
    recebido.refresh_from_db()

    descricao = chamado.mensagens.get(ordem=0)
    assert descricao.sha256 == recebido.sha256
    assert descricao.texto == recebido.texto
    assert bytes(descricao.bruto) == bytes(recebido.bruto)
    assert descricao.norm_v == recebido.norm_v
    assert descricao.citacao_offset == recebido.citacao_offset

    assert recebido.situacao == "promovido"
    assert recebido.chamado_id == chamado.id
    assert recebido.promovido_por_id == pessoa.id
    assert recebido.promovido_em is not None


def test_promover_duas_vezes_e_recusado(receber, pessoa):
    recebido = receber(eml("simples.eml"))
    promover(recebido, por=pessoa)

    with pytest.raises(JaDecidido):
        promover(recebido, por=pessoa)

    assert Chamado.objects.count() == 1


def test_promover_email_descartado_e_recusado(receber, pessoa):
    recebido = receber(eml("simples.eml"))
    descartar(recebido, por=pessoa)

    with pytest.raises(JaDecidido):
        promover(recebido, por=pessoa)


def test_corrupcao_no_texto_impede_a_promocao(receber, pessoa):
    """Se o texto não bate com o sha256 gravado, nada é criado."""
    recebido = receber(eml("simples.eml"))
    # Por fora do modelo, de propósito: o modelo recusaria este UPDATE.
    EmailRecebido.objects.filter(pk=recebido.pk).update(texto="outra coisa")
    recebido.refresh_from_db()

    from ingest.entrada import CorrupcaoDetectada

    with pytest.raises(CorrupcaoDetectada):
        promover(recebido, por=pessoa)


# --------------------------------------------------------------- descartar


def test_descartar_nao_apaga_o_registro(receber, pessoa):
    recebido = receber(eml("simples.eml"))

    descartar(recebido, por=pessoa)
    recebido.refresh_from_db()

    assert EmailRecebido.objects.filter(pk=recebido.pk).exists()
    assert recebido.situacao == "descartado"
    assert recebido.descartado_em is not None
    assert recebido.descartado_por_id == pessoa.id
    assert recebido.texto  # continua inteiro


# --------------------------------------------------------------- API


def test_lista_da_caixa_mostra_os_pendentes(cliente_logado, receber):
    receber(eml("simples.eml"))
    receber(monta_mime(assunto="Boletim", corpo="Newsletter qualquer.\n"))

    corpo = cliente_logado.get("/api/emails").json()

    assert corpo["total"] == 2
    assert corpo["pendentes"] == 2
    assert {i["situacao"] for i in corpo["itens"]} == {"pendente"}
    assert corpo["itens"][0]["trecho"]


def test_contagem_de_pendentes(cliente_logado, receber, pessoa):
    recebido = receber(eml("simples.eml"))
    assert cliente_logado.get("/api/emails/contagem").json() == {"pendentes": 1}

    descartar(recebido, por=pessoa)
    assert cliente_logado.get("/api/emails/contagem").json() == {"pendentes": 0}


def test_email_aberto_traz_o_texto_inteiro_com_a_citacao_marcada(cliente_logado, receber):
    recebido = receber(eml("com_citacao.eml"))

    corpo = cliente_logado.get(f"/api/emails/{recebido.id}").json()

    assert corpo["texto"] == recebido.texto
    assert corpo["citacao_offset"] == recebido.citacao_offset
    assert "> Lorem ipsum dolor sit amet" in corpo["texto"]  # a citação não foi apagada
    assert corpo["sha256"] == recebido.sha256


def test_email_com_anexo_lista_o_anexo(cliente_logado, receber):
    anexo = AnexoFalso("lorem-ipsum.xlsx", b"conteudo", "application/vnd.ms-excel")
    recebido = receber(eml("com_anexo.eml"), anexos=[anexo])

    corpo = cliente_logado.get(f"/api/emails/{recebido.id}").json()
    assert [a["nome"] for a in corpo["anexos"]] == ["lorem-ipsum.xlsx"]


def test_promover_pela_api_abre_o_chamado_com_as_palavras_do_cliente(cliente_logado, receber):
    recebido = receber(eml("simples.eml"))

    resposta = post(cliente_logado, f"/api/emails/{recebido.id}/promover")
    assert resposta.status_code == 200

    corpo = resposta.json()
    chamado = Chamado.objects.get(pk=corpo["chamado_id"])
    assert corpo["chamado_codigo"] == chamado.codigo
    assert corpo["email"]["situacao"] == "promovido"

    descricao = chamado.mensagens.get(ordem=0)
    assert descricao.texto == recebido.texto
    assert descricao.sha256 == recebido.sha256


def test_promover_duas_vezes_pela_api_devolve_409(cliente_logado, receber):
    recebido = receber(eml("simples.eml"))

    assert post(cliente_logado, f"/api/emails/{recebido.id}/promover").status_code == 200
    repetido = post(cliente_logado, f"/api/emails/{recebido.id}/promover")

    assert repetido.status_code == 409
    assert "já foi" in repetido.json()["erro"]
    assert Chamado.objects.count() == 1


def test_promover_com_corpo_na_requisicao_nao_altera_o_texto(cliente_logado, receber):
    """Não existe entrada de texto humano aqui. O corpo é simplesmente ignorado."""
    recebido = receber(eml("simples.eml"))
    original = recebido.texto

    resposta = post(
        cliente_logado,
        f"/api/emails/{recebido.id}/promover",
        {"texto": "descrição digitada por um funcionário", "assunto": "outro assunto"},
    )
    assert resposta.status_code == 200

    chamado = Chamado.objects.get(pk=resposta.json()["chamado_id"])
    descricao = chamado.mensagens.get(ordem=0)
    assert descricao.texto == original
    assert "digitada por um funcionário" not in descricao.texto
    assert chamado.assunto == recebido.assunto

    recebido.refresh_from_db()
    assert recebido.texto == original


def test_promover_copia_os_anexos(cliente_logado, receber):
    anexo = AnexoFalso("lorem-ipsum.xlsx", b"conteudo", "application/vnd.ms-excel")
    recebido = receber(eml("com_anexo.eml"), anexos=[anexo])

    resposta = post(cliente_logado, f"/api/emails/{recebido.id}/promover")
    chamado = Chamado.objects.get(pk=resposta.json()["chamado_id"])

    assert Anexo.objects.filter(mensagem__chamado=chamado).count() == 1
    assert AnexoRecebido.objects.filter(email=recebido).count() == 1


def test_descartar_pela_api_e_o_email_continua_acessivel_pelo_filtro(cliente_logado, receber):
    recebido = receber(eml("simples.eml"))

    resposta = post(cliente_logado, f"/api/emails/{recebido.id}/descartar")
    assert resposta.status_code == 200
    assert resposta.json()["situacao"] == "descartado"

    pendentes = cliente_logado.get("/api/emails?situacao=pendente").json()
    assert pendentes["itens"] == []

    descartados = cliente_logado.get("/api/emails?situacao=descartado").json()
    assert [i["id"] for i in descartados["itens"]] == [recebido.id]

    assert EmailRecebido.objects.filter(pk=recebido.pk).exists()
    assert Mensagem.objects.count() == 0


def test_descartar_duas_vezes_devolve_409(cliente_logado, receber):
    recebido = receber(eml("simples.eml"))
    assert post(cliente_logado, f"/api/emails/{recebido.id}/descartar").status_code == 200
    assert post(cliente_logado, f"/api/emails/{recebido.id}/descartar").status_code == 409


def test_filtro_desconhecido_devolve_400_em_portugues(cliente_logado, empresa):
    resposta = cliente_logado.get("/api/emails?situacao=inventado")
    assert resposta.status_code == 400
    assert "desconhecido" in resposta.json()["erro"]


def test_sem_login_a_caixa_devolve_401(client, empresa):
    assert client.get("/api/emails").status_code == 401
    assert client.post("/api/emails/1/promover").status_code == 401


def test_email_de_outra_empresa_nao_aparece(cliente_logado, receber, empresa):
    from core.models import Empresa

    outra = Empresa.objects.create(nome="Outra", caixa_email="caixa@outra.com.br")
    de_fora = receber(eml("simples.eml"), empresa_alvo=outra)

    assert cliente_logado.get("/api/emails").json()["itens"] == []
    assert cliente_logado.get(f"/api/emails/{de_fora.id}").status_code == 404
    assert post(cliente_logado, f"/api/emails/{de_fora.id}/promover").status_code == 404


# --------------------------------------------------------------- e-mail de verdade


def test_email_real_com_html_assinatura_citacao_e_acento(receber, pessoa):
    """O texto gravado é o que se espera, e a promoção não muda um byte."""
    recebido = receber(eml("com_citacao.eml"))
    esperado = recebido.texto

    # Assinatura, citação e acento continuam lá: nada é "limpo".
    assert "> Lorem ipsum dolor sit amet" in esperado
    assert recebido.citacao_offset is not None
    assert esperado[recebido.citacao_offset :].lstrip().startswith(("Em ", ">"))

    chamado = promover(recebido, por=pessoa)
    descricao = chamado.mensagens.get(ordem=0)

    assert descricao.texto == esperado
    assert descricao.texto.encode("utf-8") == esperado.encode("utf-8")
    assert descricao.sha256 == hashlib.sha256(esperado.encode("utf-8")).hexdigest()


def test_texto_de_email_com_charset_latin1_sobrevive_a_promocao(receber):
    recebido = receber(eml("charset_latin1.eml"))
    esperado = recebido.texto
    chamado = promover(recebido)
    assert chamado.mensagens.get(ordem=0).texto == esperado


# --------------------------------------------------------------- conexão IMAP


@pytest.mark.imap
def test_conexao_imap_de_verdade():
    """Só roda com credencial presente. Pulado por padrão no CI.

    Para rodar:  pytest -m imap
    """
    from django.conf import settings

    if not (settings.IMAP_HOST and settings.IMAP_USER and settings.IMAP_PASSWORD):
        pytest.skip("Sem credencial IMAP no ambiente (backend/.env).")

    from ingest.caixa import leitor_do_ambiente

    with leitor_do_ambiente() as caixa:
        # Não marca nada como lido: só prova que a sessão TLS abriu e a pasta existe.
        list(caixa.mensagens_nao_lidas(limite=1))
