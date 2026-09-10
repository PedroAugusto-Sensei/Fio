"""API (seção 9), incluindo o teste 7 da seção 12 e os aceites das tarefas 4 e 8.

Todo chamado destes testes nasce de um e-mail, porque é assim que nasce no produto.
Os testes de entrada manual foram removidos junto com o endpoint (invariante 7);
o que garante que ela não volte está em `test_origem_unica.py`.
"""
import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.models import Chamado, Mensagem, Registro, abrir_chamado
from ingest.entrada import promover, receber_email

from .conftest import eml, monta_mime

pytestmark = pytest.mark.django_db


def post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def chamado_de_email(empresa, assunto, corpo, cliente="Cliente A", de="Contato A <contato@clientea.com>"):
    """Um chamado pelo caminho do produto: o e-mail entra na caixa e alguém promove."""
    mime = monta_mime(assunto=assunto, corpo=corpo, de=de)
    nome, endereco = de.split(" <")[0], de.split("<")[-1].rstrip(">")
    recebido = receber_email(
        empresa=empresa,
        bruto=mime.as_bytes(),
        message_id=mime["Message-ID"],
        remetente_nome=cliente,
        remetente_email=endereco,
        destinatario=empresa.caixa_email,
        assunto=assunto,
    )
    assert nome
    return promover(recebido)


# 7 --------------------------------------------------------------------------------


def test_sem_login_a_lista_devolve_401(client, empresa):
    resposta = client.get("/api/chamados")
    assert resposta.status_code == 401
    assert resposta.json() == {"erro": "Faça login para continuar."}


def test_sem_login_o_chamado_devolve_401(client, chamado):
    assert client.get(f"/api/chamados/{chamado.id}").status_code == 401


def test_login_devolve_nome_e_setor(client, pessoa):
    resposta = post(client, "/api/auth/login", {"usuario": "autor.1", "senha": "teste12345"})
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Autor 1"
    assert resposta.json()["setor"] == "Suporte"

    me = client.get("/api/me").json()
    assert me["empresa"] == "Empresa de Teste"
    assert me["iniciais"] == "A1"
    assert me["caixa_email"] == "atendimento@suaempresa.com.br"
    assert me["pasta_email"]  # a pasta observada, vinda do ambiente


def test_senha_errada_devolve_erro_em_portugues(client, pessoa):
    resposta = post(client, "/api/auth/login", {"usuario": "autor.1", "senha": "errada"})
    assert resposta.status_code == 400
    assert resposta.json() == {"erro": "Usuário ou senha incorretos."}


# lista ---------------------------------------------------------------------------


def test_lista_mostra_o_trecho_do_cliente_e_sem_registro(cliente_logado, empresa):
    chamado_de_email(
        empresa,
        "Lorem ipsum dolor sit amet",
        "Consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore.\n",
    )

    dados = cliente_logado.get("/api/chamados").json()
    item = dados["itens"][0]

    assert item["codigo"] == "D-0001"
    assert item["situacao"] is None  # sem registro: é informação, não erro
    assert item["total_registros"] == 0
    assert item["ultimo_autor"] is None
    assert item["trecho_cliente"].startswith("Consectetur adipiscing elit")
    # O cabeçalho mostra a caixa lida, não um endereço de encaminhamento.
    assert dados["caixa_email"] == "atendimento@suaempresa.com.br"
    assert dados["pasta_email"]


def test_trecho_e_cortado_em_palavra(cliente_logado, empresa):
    chamado_de_email(empresa, "Lorem", "palavra " * 60 + "\n")
    trecho = cliente_logado.get("/api/chamados").json()["itens"][0]["trecho_cliente"]
    assert len(trecho) <= 141
    assert trecho.endswith("…")
    assert "palavr…" not in trecho  # não corta no meio da palavra


def test_lista_nao_faz_uma_consulta_por_chamado(cliente_logado, empresa, pessoa):
    """Aceite da tarefa 4: sem N+1."""
    for i in range(12):
        chamado = chamado_de_email(empresa, f"Lorem {i}", f"Texto do cliente {i}.\n")
        Registro.objects.create(
            chamado=chamado, autor=pessoa, setor="Suporte", texto=f"Feito {i}.",
            situacao="em_andamento",
        )

    with CaptureQueriesContext(connection) as consultas:
        resposta = cliente_logado.get("/api/chamados")

    assert resposta.status_code == 200
    assert len(resposta.json()["itens"]) == 12
    # sessão + usuário + pessoa + contagem de abertos + count + página + trechos
    assert len(consultas) < 12, f"{len(consultas)} consultas para 12 chamados"


def test_filtros_por_chip(cliente_logado, empresa, pessoa):
    sem_registro = chamado_de_email(empresa, "Sem", "Nada ainda.\n")
    concluido = chamado_de_email(empresa, "Feito", "Tudo certo.\n")
    Registro.objects.create(
        chamado=concluido, autor=pessoa, setor="Suporte", texto="Resolvido.", situacao="concluido"
    )

    def codigos(**params):
        r = cliente_logado.get("/api/chamados", params)
        assert r.status_code == 200
        return [i["codigo"] for i in r.json()["itens"]]

    assert codigos(situacao="sem_registro") == [sem_registro.codigo]
    assert codigos(situacao="concluidos") == [concluido.codigo]
    assert codigos(situacao="abertos") == [sem_registro.codigo]
    assert codigos(meus="true") == [concluido.codigo]


def test_filtro_desconhecido_devolve_400_em_portugues(cliente_logado, empresa):
    resposta = cliente_logado.get("/api/chamados", {"situacao": "kanban"})
    assert resposta.status_code == 400
    assert "Filtro de situação desconhecido" in resposta.json()["erro"]


def test_busca_acha_palavra_que_so_existe_no_corpo_do_email(cliente_logado, empresa):
    """Aceite da tarefa 8."""
    chamado_de_email(
        empresa, "Lorem ipsum", "O relatório de faturamento saiu com o rodapé duplicado.\n"
    )
    chamado_de_email(empresa, "Outro assunto", "Nada a ver.\n")

    achados = cliente_logado.get("/api/chamados", {"busca": "rodapé"}).json()["itens"]
    assert [c["codigo"] for c in achados] == ["D-0001"]


def test_busca_acha_palavra_que_so_existe_num_registro(cliente_logado, empresa, pessoa):
    chamado = chamado_de_email(empresa, "Lorem", "Texto do cliente.\n")
    Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte",
        texto="Reprocessamos a planilha de comissões.", situacao="concluido",
    )
    achados = cliente_logado.get("/api/chamados", {"busca": "comissões"}).json()["itens"]
    assert [c["codigo"] for c in achados] == [chamado.codigo]


# um chamado ----------------------------------------------------------------------


def test_chamado_traz_a_descricao_e_as_mensagens_seguintes(cliente_logado, chamado):
    """A descrição é a mensagem de ordem 0; a resposta do cliente vem depois dela."""
    promover(receber_email(empresa=chamado.empresa, bruto=eml("com_citacao.eml")), chamado=chamado)

    dados = cliente_logado.get(f"/api/chamados/{chamado.id}").json()

    assert dados["descricao"]["ordem"] == 0
    assert "Lorem ipsum dolor sit amet" in dados["descricao"]["texto"]
    assert len(dados["mensagens_seguintes"]) == 1

    seguinte = dados["mensagens_seguintes"][0]
    assert seguinte["citacao_offset"] is not None
    assert "> Lorem ipsum dolor sit amet" in seguinte["texto"]  # a citação vai inteira
    assert dados["situacao"] is None
    assert dados["registros"] == []
    assert dados["total_mensagens"] == 2


def test_chamado_de_outra_empresa_nao_aparece(cliente_logado):
    from core.models import Empresa

    outra = Empresa.objects.create(nome="Outra", caixa_email="x@outra.app", setores=[])
    alheio = abrir_chamado(empresa=outra, assunto="Lorem", cliente_nome="Cliente Z")

    assert cliente_logado.get(f"/api/chamados/{alheio.id}").status_code == 404


# publicar registro ---------------------------------------------------------------


def test_publicar_registro_muda_a_situacao_e_nao_toca_em_mensagem(cliente_logado, chamado):
    """Aceite da tarefa 3 — a tese do produto."""
    antes = {m.pk: m.sha256 for m in Mensagem.objects.filter(chamado=chamado)}

    resposta = post(
        cliente_logado,
        f"/api/chamados/{chamado.id}/registros",
        {"texto": "Trocamos a configuração do relatório.", "situacao": "concluido"},
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["situacao"] == "concluido"
    assert corpo["total_registros"] == 1
    assert corpo["registro"]["setor"] == "Suporte"  # copiado da pessoa
    assert corpo["registro"]["autor"]["nome"] == "Autor 1"

    assert {m.pk: m.sha256 for m in Mensagem.objects.filter(chamado=chamado)} == antes


def test_registro_sem_situacao_e_recusado(cliente_logado, chamado):
    resposta = post(
        cliente_logado, f"/api/chamados/{chamado.id}/registros", {"texto": "Fiz.", "situacao": ""}
    )
    assert resposta.status_code == 400
    assert "situação" in resposta.json()["erro"]


def test_registro_sem_texto_e_recusado(cliente_logado, chamado):
    resposta = post(
        cliente_logado,
        f"/api/chamados/{chamado.id}/registros",
        {"texto": "   ", "situacao": "concluido"},
    )
    assert resposta.status_code == 400


def test_editar_registro_cria_versao_nova(cliente_logado, chamado):
    criado = post(
        cliente_logado, f"/api/chamados/{chamado.id}/registros",
        {"texto": "Texto com erro.", "situacao": "em_andamento"},
    ).json()["registro"]

    resposta = cliente_logado.put(
        f"/api/registros/{criado['id']}",
        data=json.dumps({"texto": "Texto corrigido.", "situacao": "concluido"}),
        content_type="application/json",
    )

    assert resposta.status_code == 200
    novo = resposta.json()["registro"]
    assert novo["versao_anterior_id"] == criado["id"]
    assert novo["editado_em"] is not None
    assert resposta.json()["total_registros"] == 1

    ativos = cliente_logado.get(f"/api/chamados/{chamado.id}").json()["registros"]
    assert [r["texto"] for r in ativos] == ["Texto corrigido."]

    historico = cliente_logado.get(
        f"/api/chamados/{chamado.id}/registros", {"historico": "1"}
    ).json()
    assert [r["texto"] for r in historico] == ["Texto com erro.", "Texto corrigido."]


def test_so_o_autor_edita_o_proprio_registro(client, chamado, pessoa, outra_pessoa):
    registro = Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte", texto="Meu.", situacao="em_andamento"
    )

    assert client.login(username="autor.2", password="teste12345")
    resposta = client.put(
        f"/api/registros/{registro.id}",
        data=json.dumps({"texto": "Mexi no seu.", "situacao": "concluido"}),
        content_type="application/json",
    )
    assert resposta.status_code == 403
    assert resposta.json()["erro"] == "Só o autor pode corrigir o próprio registro."


# resto ---------------------------------------------------------------------------


def test_setores_vem_da_empresa(cliente_logado, empresa):
    assert cliente_logado.get("/api/setores").json()["setores"] == [
        "Suporte", "Produto", "Desenvolvimento"
    ]


def test_nao_existe_endpoint_para_atualizar_status(cliente_logado, chamado):
    """Invariante 4: situação só muda junto com um registro novo."""
    from api.router import api

    rotas = [
        f"{metodo} {prefixo}{caminho}"
        for prefixo, router in api._routers
        for caminho, view in router.path_operations.items()
        for operacao in view.operations
        for metodo in operacao.methods
    ]
    assert not [r for r in rotas if "status" in r or "situaco" in r or "descricao" in r], rotas

    # Também não existe PATCH em /chamados/{id}: não há como mexer no que já está lá.
    assert cliente_logado.patch(
        f"/api/chamados/{chamado.id}", data="{}", content_type="application/json"
    ).status_code in (404, 405)


def test_chamado_existe_sem_nenhum_campo_de_canal(cliente_logado, chamado):
    dados = cliente_logado.get(f"/api/chamados/{chamado.id}").json()
    assert "canal_entrada" not in dados
    assert "canal" not in dados["descricao"]
    assert Chamado.objects.count() == 1
