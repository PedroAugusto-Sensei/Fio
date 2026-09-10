"""Normalização (seção 6), sobre e-mails reais do diretório `fixtures/`.

O trecho citado é MARCADO, nunca apagado.
"""
import base64
import quopri

import pytest

from ingest.normalizacao import NORM_V, encontrar_citacao, normalizar, normalizar_texto

from .conftest import eml


def test_normalizar_preserva_a_citacao_e_aponta_o_offset():
    """Teste 4 da seção 12, sobre `com_citacao.eml`."""
    texto, offset = normalizar(eml("com_citacao.eml"))

    assert offset is not None
    assert "Lorem ipsum dolor sit amet" in texto  # a citação continua no texto
    assert texto[offset:].startswith("Em 21/08/2026, Contato A escreveu:")
    assert "> Lorem ipsum dolor sit amet" in texto[offset:]
    assert "Nemo enim ipsam voluptatem" in texto[:offset]


def test_sem_citacao_o_offset_e_none():
    texto, offset = normalizar(eml("simples.eml"))
    assert offset is None
    assert texto.startswith("Lorem ipsum dolor sit amet")


def test_assinatura_nao_e_removida():
    texto, _ = normalizar(eml("simples.eml"))
    assert "Atenciosamente," in texto
    assert "Contato A" in texto
    assert "Cliente A" in texto


def test_prefere_text_plain_quando_ha_html_junto():
    texto, _ = normalizar(eml("multipart_alternativo.eml"))
    assert "versao em texto puro" in texto
    assert "versao em HTML" not in texto


def test_html_sem_plain_vira_texto_sem_script_nem_style():
    texto, _ = normalizar(eml("somente_html.eml"))
    assert "Quis nostrud exercitation ullamco laboris." in texto
    assert "Duis aute irure dolor" in texto
    assert "rastreador" not in texto
    assert "#ff0000" not in texto


def test_charset_declarado_e_respeitado():
    texto, _ = normalizar(eml("charset_latin1.eml"))
    assert "informação do orçamento" in texto
    assert "terceira página" in texto
    assert "Não consegui corrigir sozinho" in texto


def test_anexo_nao_entra_no_corpo():
    texto, _ = normalizar(eml("com_anexo.eml"))
    assert "Segue a planilha em anexo." in texto
    assert "Y29udGV1ZG8" not in texto  # o base64 do anexo não vaza para o texto


def test_quebras_sao_colapsadas_mas_paragrafos_ficam():
    texto, _ = normalizar_texto("Um.\r\n\r\n\r\n\r\nDois.\r\n")
    assert texto == "Um.\n\nDois."


def test_marcador_em_ingles_tambem_conta():
    texto = "Reply here.\n\nOn Aug 21, 2026, Contact A wrote:\n> original\n"
    assert encontrar_citacao(texto) == texto.index("On Aug 21")


def test_normalizacao_e_deterministica():
    bruto = eml("com_citacao.eml")
    assert normalizar(bruto) == normalizar(bruto)
    assert NORM_V == 2


@pytest.mark.parametrize("tipo", ["text/plain", "text/html"])
@pytest.mark.parametrize("transferencia", ["8bit", "base64", "quoted-printable"])
@pytest.mark.parametrize(
    "codificacao,charset",
    [
        ("utf-8", "utf-8"),
        ("utf-8", "inexistente"),
        ("utf-8", "us-ascii"),
        ("utf-8", None),
        ("iso-8859-1", "iso-8859-1"),
        ("iso-8859-1", "utf-8"),
        ("iso-8859-1", None),
        ("windows-1252", "windows-1252"),
        ("windows-1252", "utf-8"),
        ("windows-1252", None),
    ],
)
def test_acentos_com_charset_ausente_ou_invalido(tipo, transferencia, codificacao, charset):
    esperado = "Comunicação, notícias, instituição. Não receber notificações."
    if codificacao == "windows-1252":
        esperado += " “Olá” — €"
    corpo = f"<p>{esperado}</p>" if tipo == "text/html" else esperado
    carga = corpo.encode(codificacao)
    if transferencia == "base64":
        carga = base64.b64encode(carga)
    elif transferencia == "quoted-printable":
        carga = quopri.encodestring(carga)
    content_type = tipo + (f"; charset={charset}" if charset else "")
    bruto = (
        f"Content-Type: {content_type}\r\n"
        f"Content-Transfer-Encoding: {transferencia}\r\n\r\n"
    ).encode("ascii") + carga

    assert normalizar(bruto) == (esperado, None)
