"""Testes das invariantes (seção 12 da especificação).

Cada teste aqui existe porque uma invariante do CLAUDE.md pode ser quebrada por descuido.
"""
import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.models import Chamado, Mensagem, Registro, chamados_com_situacao, situacao_de
from ingest.entrada import promover, receber_email
from ingest.normalizacao import NORM_V

from .conftest import eml

pytestmark = pytest.mark.django_db


def nova_mensagem(chamado, arquivo="com_citacao.eml"):
    """Entra pela única porta que existe: e-mail recebido, depois promovido."""
    recebido = receber_email(empresa=chamado.empresa, bruto=eml(arquivo))
    promover(recebido, chamado=chamado)
    return chamado.mensagens.order_by("-ordem").first()


# 1 --------------------------------------------------------------------------------


def test_mensagem_ja_salva_nao_pode_ser_salva_de_novo(chamado):
    """Invariante 1: Mensagem é imutável."""
    mensagem = chamado.descricao
    original = mensagem.texto

    mensagem.texto = "outro texto qualquer"
    with pytest.raises(ValidationError):
        mensagem.save()

    assert Mensagem.objects.get(pk=mensagem.pk).texto == original


def test_mensagem_nao_pode_ser_apagada_sozinha(chamado):
    """Invariante 6: só existe exclusão em cascata, apagando o chamado inteiro."""
    mensagem = chamado.descricao

    with pytest.raises(ValidationError):
        mensagem.delete()

    assert Mensagem.objects.filter(pk=mensagem.pk).exists()

    chamado.delete()
    assert not Mensagem.objects.filter(pk=mensagem.pk).exists()


def test_chamado_nao_tem_campo_descricao_nem_situacao():
    """Invariantes 2 e 3: se os campos existissem, alguém acabaria escrevendo neles."""
    colunas = {f.name for f in Chamado._meta.get_fields() if getattr(f, "concrete", False)}
    assert "descricao" not in colunas
    assert "situacao" not in colunas


# 5 --------------------------------------------------------------------------------


def test_situacao_e_a_do_registro_mais_recente(chamado, pessoa, outra_pessoa):
    """Invariante 3: a situação é projeção, não campo."""
    assert situacao_de(chamado) is None  # sem registro nenhum

    antigo = Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte", texto="Primeiro.", situacao="em_andamento"
    )
    Registro.objects.filter(pk=antigo.pk).update(
        criado_em=timezone.now() - timezone.timedelta(days=2)
    )
    Registro.objects.create(
        chamado=chamado, autor=outra_pessoa, setor="Produto", texto="Depois.", situacao="bloqueado"
    )

    assert situacao_de(chamado) == "bloqueado"

    projetado = chamados_com_situacao().get(pk=chamado.pk)
    assert projetado.situacao == "bloqueado"
    assert projetado.ultimo_autor == "Autor 2"
    assert projetado.ultimo_setor == "Produto"
    assert projetado.total_registros == 2


def test_chamado_sem_registro_nao_tem_situacao(chamado):
    projetado = chamados_com_situacao().get(pk=chamado.pk)
    assert projetado.situacao is None
    assert projetado.total_registros == 0
    assert projetado.ultimo_autor is None


def test_versao_nova_de_registro_substitui_a_antiga_no_feed(chamado, pessoa):
    """Editar registro não faz UPDATE: cria versão nova apontando para a antiga."""
    antigo = Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte", texto="Texto com erro.",
        situacao="em_andamento",
    )
    novo = Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte", texto="Texto corrigido.",
        situacao="concluido", editado_em=timezone.now(), versao_anterior=antigo,
    )

    ativos = list(chamado.registros.filter(versao_seguinte__isnull=True))
    assert ativos == [novo]
    assert Registro.objects.filter(pk=antigo.pk).exists()  # continua no banco
    assert Registro.objects.get(pk=antigo.pk).texto == "Texto com erro."
    assert situacao_de(chamado) == "concluido"


# 6 --------------------------------------------------------------------------------


def test_publicar_registro_nao_altera_nenhuma_mensagem(chamado, pessoa):
    """A tese: o registro acrescenta; as palavras do cliente ficam intactas."""
    m0 = chamado.descricao
    m1 = nova_mensagem(chamado)
    antes = {m.pk: (m.sha256, m.texto) for m in Mensagem.objects.filter(chamado=chamado)}

    Registro.objects.create(
        chamado=chamado, autor=pessoa, setor="Suporte",
        texto="Fizemos alguma coisa.", situacao="em_andamento",
    )

    depois = {m.pk: (m.sha256, m.texto) for m in Mensagem.objects.filter(chamado=chamado)}
    assert antes == depois
    assert set(antes) == {m0.pk, m1.pk}


def test_norm_v_e_gravado_junto_com_a_mensagem(chamado):
    assert chamado.descricao.norm_v == NORM_V
