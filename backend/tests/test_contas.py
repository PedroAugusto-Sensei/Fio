"""Cadastro de empresa, contas individuais e escopo por empresa.

Duas coisas se provam aqui, e a segunda é a que quebra em silêncio se ficar pela metade:

1. **Cada funcionário tem conta própria.** Não existe senha compartilhada de empresa,
   porque `Registro.autor` e `Registro.setor` são a resposta do produto para "quem
   agiu" — com login compartilhado o feed do chamado viraria ficção.
2. **Todo queryset autenticado é escopado por `request.user.pessoa.empresa`.** Chamado
   de outra empresa devolve 404, nunca 403: 403 confirmaria que o chamado existe.

Nada aqui cria, edita ou apaga `Mensagem`. As invariantes 1 a 7 continuam valendo, e o
teste que as guarda continua em `test_invariantes.py` e `test_origem_unica.py`.
"""
import json

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Chamado, Convite, Empresa, Mensagem, Pessoa, Registro
from ingest.entrada import promover, receber_email

from .conftest import SENHA, monta_mime

pytestmark = pytest.mark.django_db


def post(client, url, corpo=None):
    return client.post(url, data=json.dumps(corpo or {}), content_type="application/json")


def put(client, url, corpo):
    return client.put(url, data=json.dumps(corpo), content_type="application/json")


def chamado_de(empresa, assunto="Lorem ipsum", corpo="Texto do cliente.\n"):
    """Um chamado pelo caminho do produto: o e-mail entra na caixa e alguém promove."""
    mime = monta_mime(assunto=assunto, corpo=corpo, para=empresa.caixa_email)
    recebido = receber_email(
        empresa=empresa,
        bruto=mime.as_bytes(),
        message_id=mime["Message-ID"],
        remetente_nome="Contato A",
        remetente_email="contato@clientea.com",
        destinatario=empresa.caixa_email,
        assunto=assunto,
    )
    return promover(recebido)


def convite_de(pessoa, **campos):
    return Convite.objects.create(empresa=pessoa.empresa, criado_por=pessoa, **campos)


# ---------------------------------------------------------------- cadastro da empresa


CADASTRO = {
    "empresa_nome": "Padaria do Bairro",
    "setores": ["Atendimento", "Cozinha"],
    "nome": "Joana Ribeiro",
    "email": "joana@padaria.com.br",
    "senha": "padaria2026",
}


def test_registrar_empresa_cria_empresa_admin_e_ja_entra(client):
    resposta = post(client, "/api/auth/registrar-empresa", CADASTRO)

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["empresa"] == "Padaria do Bairro"
    assert corpo["papel"] == "admin"
    assert corpo["pode_configurar_imap"] is True
    assert corpo["nome"] == "Joana Ribeiro"

    empresa = Empresa.objects.get(nome="Padaria do Bairro")
    assert empresa.setores == ["Atendimento", "Cozinha"]
    # A caixa de e-mail não entra no cadastro: é configuração de admin, depois.
    assert empresa.caixa_email == ""

    pessoa = Pessoa.objects.get(empresa=empresa)
    assert pessoa.papel == "admin"
    assert empresa.criador_id == pessoa.user_id
    assert pessoa.setor == "Atendimento"
    # O e-mail é o nome de usuário: quem se cadastra entra com o próprio e-mail.
    assert pessoa.user.username == "joana@padaria.com.br"

    # A sessão já está autenticada — nada de mandar a pessoa para o login logo depois.
    assert client.get("/api/me").json()["empresa_id"] == empresa.id


def test_registrar_empresa_sem_setores_usa_o_padrao(client):
    post(client, "/api/auth/registrar-empresa", {**CADASTRO, "setores": []})
    empresa = Empresa.objects.get(nome="Padaria do Bairro")
    assert empresa.setores == [
        "Suporte", "Produto", "Desenvolvimento", "QA", "Implantação"
    ]


def test_registrar_empresa_com_email_ja_existente_devolve_400_em_portugues(client, pessoa):
    User.objects.create_user(username="joana@padaria.com.br", password=SENHA)

    resposta = post(client, "/api/auth/registrar-empresa", CADASTRO)

    assert resposta.status_code == 400
    assert resposta.json()["erro"] == (
        "Já existe uma conta com este e-mail. Entre com ela ou use outro."
    )
    assert not Empresa.objects.filter(nome="Padaria do Bairro").exists()


def test_registrar_empresa_com_senha_curta_devolve_400(client):
    resposta = post(client, "/api/auth/registrar-empresa", {**CADASTRO, "senha": "curta12"})
    assert resposta.status_code == 400
    assert "8 caracteres" in resposta.json()["erro"]
    assert not Empresa.objects.filter(nome="Padaria do Bairro").exists()


# ---------------------------------------------------------------- convites


def test_admin_cria_convite_com_link(cliente_logado, pessoa):
    resposta = post(cliente_logado, "/api/convites", {"email": "novo@empresa.com", "setor": "Produto"})

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["url"].endswith(f"/convite/{corpo['token']}")
    assert corpo["setor"] == "Produto"

    pendentes = cliente_logado.get("/api/convites").json()["itens"]
    assert [c["email"] for c in pendentes] == ["novo@empresa.com"]


def test_link_do_convite_aponta_para_o_front_que_pediu(cliente_logado):
    """O link é para a tela, não para a API: o front e o back podem estar em portas
    diferentes, e é o `Origin` de quem pediu que diz onde a tela mora."""
    resposta = cliente_logado.post(
        "/api/convites",
        data=json.dumps({}),
        content_type="application/json",
        HTTP_ORIGIN="http://localhost:5173",
    )

    corpo = resposta.json()
    assert corpo["url"] == f"http://localhost:5173/convite/{corpo['token']}"


def test_convite_publico_mostra_a_empresa_e_os_setores_e_nada_mais(client, pessoa):
    chamado_de(pessoa.empresa)
    convite = convite_de(pessoa, email="novo@empresa.com", setor="Produto")

    resposta = client.get(f"/api/convites/{convite.token}")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo == {
        "empresa_nome": "Empresa de Teste",
        "setores": ["Suporte", "Produto", "Desenvolvimento"],
        "email": "novo@empresa.com",
        "setor": "Produto",
    }
    # Um link vazado não pode virar janela para dentro da empresa.
    assert "caixa_email" not in corpo
    assert "chamados" not in corpo


def test_convite_inexistente_devolve_404(client):
    assert client.get("/api/convites/nao-existe-este-token").status_code == 404


def test_aceitar_convite_cria_membro_na_empresa_certa_e_ja_entra(client, pessoa, outra_empresa):
    convite = convite_de(pessoa, email="novo@empresa.com", setor="Produto")

    resposta = post(
        client,
        f"/api/convites/{convite.token}/aceitar",
        {
            "nome": "Novo Fulano",
            "email": "novo@empresa.com",
            "senha": "senhaboa123",
            "setor": "Produto",
        },
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["papel"] == "membro"

    nova = Pessoa.objects.get(nome="Novo Fulano")
    assert nova.papel == "membro"
    assert nova.empresa == pessoa.empresa
    assert nova.empresa != outra_empresa
    assert nova.setor == "Produto"

    convite.refresh_from_db()
    assert convite.usado_em is not None
    assert convite.usado_por == nova

    # A sessão já está aberta na conta recém-criada.
    assert client.get("/api/me").json()["nome"] == "Novo Fulano"


def test_aceitar_convite_com_setor_de_fora_da_lista_devolve_400(client, pessoa):
    convite = convite_de(pessoa)

    resposta = post(
        client,
        f"/api/convites/{convite.token}/aceitar",
        {"nome": "Novo", "email": "novo@empresa.com", "senha": "senhaboa123", "setor": "Jurídico"},
    )

    assert resposta.status_code == 400
    assert resposta.json()["erro"] == "Escolha um dos setores da empresa."
    assert not Pessoa.objects.filter(nome="Novo").exists()


def test_convite_expirado_devolve_410_em_ver_e_em_aceitar(client, pessoa):
    convite = convite_de(pessoa, expira_em=timezone.now() - timezone.timedelta(minutes=1))

    ver = client.get(f"/api/convites/{convite.token}")
    assert ver.status_code == 410
    assert "expirou" in ver.json()["erro"]

    aceitar = post(
        client,
        f"/api/convites/{convite.token}/aceitar",
        {"nome": "Novo", "email": "novo@empresa.com", "senha": "senhaboa123", "setor": "Suporte"},
    )
    assert aceitar.status_code == 410
    assert not Pessoa.objects.filter(nome="Novo").exists()


def test_convite_ja_usado_devolve_410_em_ver_e_em_aceitar(client, pessoa, outra_pessoa):
    convite = convite_de(pessoa, usado_em=timezone.now(), usado_por=outra_pessoa)

    ver = client.get(f"/api/convites/{convite.token}")
    assert ver.status_code == 410
    assert "já foi usado" in ver.json()["erro"]

    aceitar = post(
        client,
        f"/api/convites/{convite.token}/aceitar",
        {"nome": "Novo", "email": "novo@empresa.com", "senha": "senhaboa123", "setor": "Suporte"},
    )
    assert aceitar.status_code == 410
    assert not Pessoa.objects.filter(nome="Novo").exists()


def test_revogar_convite_fecha_o_link(cliente_logado, client, pessoa):
    convite = convite_de(pessoa)

    assert cliente_logado.delete(f"/api/convites/{convite.id}").status_code == 200
    assert client.get(f"/api/convites/{convite.token}").status_code == 404
    assert cliente_logado.get("/api/convites").json()["itens"] == []


def test_convite_de_outra_empresa_nao_pode_ser_revogado(cliente_logado, pessoa_vizinha):
    alheio = convite_de(pessoa_vizinha)

    assert cliente_logado.delete(f"/api/convites/{alheio.id}").status_code == 404
    assert Convite.objects.filter(pk=alheio.pk).exists()


# ---------------------------------------------------------------- papel


def test_membro_nao_convida_nem_edita_a_empresa(client, outra_pessoa):
    """Papel decide três coisas. Ler chamado e publicar registro não é uma delas."""
    assert client.login(username="autor.2", password=SENHA)

    convidar = post(client, "/api/convites", {"email": "alguem@empresa.com"})
    assert convidar.status_code == 403
    assert convidar.json()["erro"] == "Só um administrador da empresa pode fazer isso."

    editar = put(client, "/api/empresa", {"nome": "Outro Nome", "setores": ["Suporte"]})
    assert editar.status_code == 403

    assert client.get("/api/convites").status_code == 403
    assert Convite.objects.count() == 0


def test_membro_le_chamados_e_publica_registro(client, outra_pessoa, empresa):
    """A tese: sem permissão por setor. Quem está autenticado lê tudo e registra."""
    chamado = chamado_de(empresa)
    assert client.login(username="autor.2", password=SENHA)

    assert client.get(f"/api/chamados/{chamado.id}").status_code == 200
    publicado = post(
        client,
        f"/api/chamados/{chamado.id}/registros",
        {"texto": "Conferi a planilha.", "situacao": "concluido"},
    )
    assert publicado.status_code == 200
    assert publicado.json()["registro"]["setor"] == "Produto"


def test_membros_lista_a_empresa_inteira_e_so_ela(cliente_logado, outra_pessoa, pessoa_vizinha):
    itens = cliente_logado.get("/api/membros").json()["itens"]

    assert [(m["nome"], m["papel"]) for m in itens] == [
        ("Autor 1", "admin"),
        ("Autor 2", "membro"),
    ]
    assert "Vizinha 1" not in [m["nome"] for m in itens]


def test_editar_empresa_nao_mexe_no_setor_ja_gravado_em_registro(cliente_logado, empresa, pessoa):
    """Setor no `Registro` é cópia histórica de quem agiu. Não se reescreve histórico."""
    chamado = chamado_de(empresa)
    registro = Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Produto", texto="Feito.", situacao="concluido"
    )

    resposta = put(
        cliente_logado, "/api/empresa", {"nome": "Empresa de Teste", "setores": ["Suporte"]}
    )

    assert resposta.status_code == 200
    assert resposta.json()["setores"] == ["Suporte"]
    registro.refresh_from_db()
    assert registro.setor == "Produto"  # continua o que era quando a pessoa agiu


# ---------------------------------------------------------------- escopo por empresa


def test_chamado_de_outra_empresa_devolve_404_e_nao_403(cliente_logado, outra_empresa):
    """404, nunca 403: 403 confirmaria que o chamado existe."""
    alheio = chamado_de(outra_empresa, assunto="Assunto da vizinha")

    resposta = cliente_logado.get(f"/api/chamados/{alheio.id}")

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "Não encontrado."}


def test_lista_de_chamados_nao_mostra_nada_da_outra_empresa(
    cliente_logado, cliente_vizinho, empresa, outra_empresa
):
    meu = chamado_de(empresa, assunto="Meu chamado")
    alheio = chamado_de(outra_empresa, assunto="Chamado da vizinha")

    minha_lista = cliente_logado.get("/api/chamados").json()
    assert [c["id"] for c in minha_lista["itens"]] == [meu.id]
    assert minha_lista["total"] == 1

    lista_vizinha = cliente_vizinho.get("/api/chamados").json()
    assert [c["id"] for c in lista_vizinha["itens"]] == [alheio.id]


def test_busca_nao_atravessa_empresa(cliente_logado, empresa, outra_empresa):
    chamado_de(outra_empresa, corpo="O rodapé do relatório saiu duplicado.\n")
    assert cliente_logado.get("/api/chamados", {"busca": "rodapé"}).json()["itens"] == []


def test_registro_de_outra_empresa_nao_pode_ser_editado(cliente_logado, pessoa_vizinha, outra_empresa):
    alheio = chamado_de(outra_empresa)
    registro = Registro.objects.create(
        chamado=alheio, autor=pessoa_vizinha, setor="Suporte", texto="Feito.",
        situacao="em_andamento",
    )

    resposta = put(
        cliente_logado, f"/api/registros/{registro.id}", {"texto": "Mexi.", "situacao": "concluido"}
    )

    assert resposta.status_code == 404
    registro.refresh_from_db()
    assert registro.texto == "Feito."


def test_publicar_registro_em_chamado_de_outra_empresa_devolve_404(cliente_logado, outra_empresa):
    alheio = chamado_de(outra_empresa)

    resposta = post(
        cliente_logado, f"/api/chamados/{alheio.id}/registros",
        {"texto": "Não deveria entrar.", "situacao": "concluido"},
    )

    assert resposta.status_code == 404
    assert not Registro.objects.filter(chamado=alheio).exists()


def test_caixa_de_entrada_nao_atravessa_empresa(cliente_logado, empresa, outra_empresa):
    alheio = receber_email(
        empresa=outra_empresa,
        bruto=monta_mime(assunto="Da vizinha", corpo="Texto.\n").as_bytes(),
        remetente_email="contato@clientea.com",
        assunto="Da vizinha",
    )

    lista = cliente_logado.get("/api/emails", {"situacao": "todos"}).json()
    assert lista["itens"] == []
    assert cliente_logado.get(f"/api/emails/{alheio.id}").status_code == 404
    assert post(cliente_logado, f"/api/emails/{alheio.id}/promover").status_code == 404
    assert post(cliente_logado, f"/api/emails/{alheio.id}/descartar").status_code == 404

    alheio.refresh_from_db()
    assert alheio.situacao == "pendente"
    assert not Chamado.objects.filter(empresa=outra_empresa).exists()


def test_setores_vem_da_empresa_de_quem_esta_logado(cliente_logado, cliente_vizinho):
    assert cliente_logado.get("/api/setores").json()["setores"] == [
        "Suporte", "Produto", "Desenvolvimento"
    ]
    assert cliente_vizinho.get("/api/setores").json()["setores"] == ["Suporte", "Financeiro"]


def test_nenhuma_mensagem_e_criada_por_nada_disto(client, pessoa, outra_empresa):
    """Invariante 7 de novo, agora com contas: cadastro não é porta de entrada de texto."""
    antes = Mensagem.objects.count()

    post(client, "/api/auth/registrar-empresa", CADASTRO)
    convite = convite_de(pessoa)
    post(
        client,
        f"/api/convites/{convite.token}/aceitar",
        {"nome": "Novo", "email": "novo@empresa.com", "senha": "senhaboa123", "setor": "Suporte"},
    )

    assert Mensagem.objects.count() == antes
