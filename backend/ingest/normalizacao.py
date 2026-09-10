"""Normalização do texto do cliente (seção 6 da especificação).

Determinística. Nunca roda de novo em texto já gravado — por isso `NORM_V` é gravado
junto com a mensagem.

PROIBIDO: remover assinatura, remover a citação, "limpar" o texto. O trecho citado é
marcado por `citacao_offset`, nunca apagado — apagar é exatamente a perda que este
produto existe para impedir.
"""
import email
import email.policy
import re
import unicodedata
from email.message import Message

NORM_V = 1

# Primeira linha que denuncia o começo do trecho citado.
_MARCADORES_CITACAO = (
    re.compile(r"^>", re.MULTILINE),
    re.compile(r"^Em .*escreveu:\s*$", re.MULTILINE),
    re.compile(r"^On .*wrote:\s*$", re.MULTILINE),
)

_TRES_OU_MAIS_QUEBRAS = re.compile(r"\n{3,}")


def _decodificar(parte: Message) -> str:
    """Bytes da parte -> str, respeitando o charset declarado. Nunca levanta."""
    carga = parte.get_payload(decode=True)
    if carga is None:
        carga = str(parte.get_payload()).encode("utf-8", errors="replace")
    charset = parte.get_content_charset() or "utf-8"
    try:
        return carga.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return carga.decode("utf-8", errors="replace")


def _html_para_texto(html: str) -> str:
    """Só tira <script> e <style>. Preserva quebras de parágrafo."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover - fallback grosseiro, mas nunca perde conteúdo
        sem_tags = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
        return re.sub(r"<[^>]+>", "\n", sem_tags)

    sopa = BeautifulSoup(html, "html.parser")
    for tag in sopa(["script", "style"]):
        tag.decompose()
    return sopa.get_text("\n")


def _escolher_corpo(msg: Message) -> str:
    """Prefere text/plain. Só cai para text/html se não houver plain."""
    plain: list[str] = []
    html: list[str] = []

    if msg.is_multipart():
        for parte in msg.walk():
            if parte.is_multipart():
                continue
            if (parte.get_content_disposition() or "") == "attachment":
                continue
            tipo = parte.get_content_type()
            if tipo == "text/plain":
                plain.append(_decodificar(parte))
            elif tipo == "text/html":
                html.append(_decodificar(parte))
    else:
        tipo = msg.get_content_type()
        if tipo == "text/html":
            html.append(_decodificar(msg))
        else:
            plain.append(_decodificar(msg))

    if plain:
        return "\n".join(plain)
    if html:
        return _html_para_texto("\n".join(html))
    return ""


def encontrar_citacao(texto: str) -> "int | None":
    """Índice da primeira linha citada, ou None. O texto continua inteiro."""
    inicios = [m.start() for padrao in _MARCADORES_CITACAO if (m := padrao.search(texto))]
    return min(inicios) if inicios else None


def limpar_quebras(texto: str) -> str:
    """`\\r\\n` -> `\\n`, 3+ quebras seguidas viram 2. Não mexe em mais nada."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = _TRES_OU_MAIS_QUEBRAS.sub("\n\n", texto)
    return texto.strip("\n")


def normalizar_texto(texto: str) -> "tuple[str, int | None]":
    """Os passos 3 a 5 aplicados a um texto que já veio em str (entrada colada)."""
    texto = limpar_quebras(texto)
    texto = unicodedata.normalize("NFC", texto)
    return texto, encontrar_citacao(texto)


def normalizar(mime_bytes: bytes) -> "tuple[str, int | None]":
    """Devolve (texto, citacao_offset)."""
    msg = email.message_from_bytes(mime_bytes, policy=email.policy.compat32)
    corpo = _escolher_corpo(msg)
    return normalizar_texto(corpo)
