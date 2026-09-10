"""Invariante 7: a única origem de uma `Mensagem` é o ingest de e-mail.

Nenhuma tela, campo, endpoint, serializer ou ação de admin cria mensagem a partir de
texto digitado. Estes testes existem para que a entrada manual não volte por descuido.
"""
import json

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Chamado, EmailRecebido, Mensagem
from ingest.entrada import promover, receber_email

from .conftest import eml

pytestmark = pytest.mark.django_db


def test_criar_mensagem_fora_do_ingest_e_recusado(chamado):
    """O caminho óbvio de quem quiser "só colar um texto" bate na trava."""
    with pytest.raises(ValidationError) as erro:
        Mensagem.objects.create(
            chamado=chamado,
            ordem=99,
            remetente="alguem@empresa.com.br",
            recebido_em=timezone.now(),
            bruto=b"texto digitado por um funcionario",
            texto="texto digitado por um funcionario",
            norm_v=1,
        )

    assert "ingest" in str(erro.value)
    assert Mensagem.objects.filter(chamado=chamado).count() == 1  # só a de ordem 0


def test_instanciar_e_salvar_a_mao_tambem_e_recusado(chamado):
    mensagem = Mensagem(
        chamado=chamado,
        ordem=99,
        recebido_em=timezone.now(),
        bruto=b"x",
        texto="x",
        norm_v=1,
    )
    with pytest.raises(ValidationError):
        mensagem.save()


def test_o_ingest_e_o_unico_caminho_que_funciona(chamado):
    """A mesma gravação, feita pela porta certa, passa."""
    antes = Mensagem.objects.filter(chamado=chamado).count()
    recebido = receber_email(empresa=chamado.empresa, bruto=eml("com_citacao.eml"))
    promover(recebido, chamado=chamado)
    assert Mensagem.objects.filter(chamado=chamado).count() == antes + 1


def test_gravar_mensagem_nao_aceita_texto_solto(chamado):
    """A assinatura não tem por onde receber texto digitado — e é de propósito."""
    import inspect

    from ingest.entrada import gravar_mensagem

    parametros = set(inspect.signature(gravar_mensagem).parameters)
    assert parametros == {"chamado", "origem"}
    assert not parametros & {"texto", "bruto", "assunto", "corpo"}


def test_mensagem_so_nasce_de_um_email_recebido_ja_gravado(chamado):
    """Toda Mensagem tem um EmailRecebido por trás, com o mesmo sha256."""
    for mensagem in Mensagem.objects.filter(chamado=chamado):
        origem = EmailRecebido.objects.get(
            empresa=chamado.empresa, message_id=mensagem.message_id
        )
        assert origem.sha256 == mensagem.sha256
        assert origem.texto == mensagem.texto


def test_nao_existe_endpoint_que_crie_chamado_ou_mensagem(cliente_logado, empresa):
    """POST /chamados não existe mais — e nenhuma rota o substitui."""
    from api.router import api

    rotas = {
        f"{metodo} {prefixo}{caminho}"
        for prefixo, router in api._routers
        for caminho, view in router.path_operations.items()
        for operacao in view.operations
        for metodo in operacao.methods
    }

    # Só se cria registro, conta e convite. Chamado e mensagem nascem do ingest.
    criacoes = {r for r in rotas if r.startswith("POST")}
    assert criacoes == {
        "POST /auth/login",
        "POST /auth/logout",
        # Contas: empresa, pessoa e convite. Nenhuma delas carrega palavra de cliente.
        "POST /auth/registrar-empresa",
        "POST /convites",
        "POST /convites/{str:token}/aceitar",
        "POST /chamados/{int:chamado_id}/registros",
        # Promover não cria texto: copia o que já está gravado no e-mail recebido.
        "POST /emails/{int:email_id}/promover",
        "POST /emails/{int:email_id}/descartar",
    }, criacoes

    resposta = cliente_logado.post(
        "/api/chamados",
        data=json.dumps({"assunto": "Lorem", "texto": "colado à mão"}),
        content_type="application/json",
    )
    assert resposta.status_code in (404, 405)
    assert Chamado.objects.filter(empresa=empresa).count() == 0


def test_nenhum_schema_da_api_aceita_texto_de_mensagem():
    """Se aparecer um schema de entrada com `texto` de cliente, a entrada manual voltou.

    A lista é fechada de propósito: um schema de entrada novo tem de ser justificado
    aqui antes de existir. Nenhum destes carrega palavra de cliente — `RegistroIn` é o
    que o **setor** escreveu, e os de conta são nome, e-mail, senha e setor.
    """
    import api.schemas as schemas
    from ninja import Schema

    entradas = {
        nome: klass
        for nome, klass in vars(schemas).items()
        if isinstance(klass, type) and issubclass(klass, Schema) and nome.endswith("In")
    }
    assert set(entradas) == {
        "LoginIn",
        "RegistroIn",
        "RegistrarEmpresaIn",
        "ConviteIn",
        "AceitarConviteIn",
        "EmpresaIn",
    }, entradas

    # E nenhum dos schemas de conta tem por onde receber texto de cliente.
    de_conta = ["RegistrarEmpresaIn", "ConviteIn", "AceitarConviteIn", "EmpresaIn"]
    for nome in de_conta:
        campos = set(entradas[nome].model_fields)
        assert not campos & {"texto", "corpo", "bruto", "descricao", "mensagem"}, nome


def test_admin_nao_deixa_criar_nem_apagar_mensagem(empresa):
    """Nem pela tela de admin, nem por inline dentro do chamado."""
    from django.contrib import admin as django_admin

    from core.admin import MensagemInline
    from core.models import Mensagem as M

    admin_mensagem = django_admin.site._registry[M]
    assert admin_mensagem.has_add_permission(None) is False
    assert admin_mensagem.has_change_permission(None) is False
    assert admin_mensagem.has_delete_permission(None) is False
    assert MensagemInline(M, django_admin.site).has_add_permission(None) is False


def test_mensagem_nao_tem_campo_de_canal():
    """E-mail é a única origem: um campo `canal` só faria sentido se houvesse outra."""
    campos = {f.name for f in Mensagem._meta.get_fields()}
    assert "canal" not in campos
