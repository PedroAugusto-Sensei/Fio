"""Regras de entrada. Único caminho pelo qual um `EmailRecebido` e uma `Mensagem` nascem.

O caminho tem duas etapas, e nesta ordem:

1. `receber_email` grava o que veio da caixa como `EmailRecebido`. Todo e-mail lido é
   gravado, inclusive o que não é demanda — nada é filtrado por conteúdo.
2. `promover` copia `texto` e `bruto` desse `EmailRecebido`, sem alteração nenhuma, para
   uma `Mensagem` de um chamado (novo, ou o da conversa que as referências apontam).

O MIME cru é gravado antes de qualquer parse (invariante 5). Se o parser errar,
reprocessa-se a partir de `EmailRecebido.bruto` sem pedir nada ao cliente.

Não existe entrada manual (invariante 7): nada aqui aceita texto digitado por
um funcionário. O humano escolhe **qual** e-mail vira chamado — nunca **o que**
está escrito nele. Se você veio adicionar entrada de texto, leia o CLAUDE.md primeiro.
"""
import email
import email.policy
import hashlib
import logging
import re
from email.message import Message
from email.utils import getaddresses

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.models import (
    Anexo,
    AnexoRecebido,
    Chamado,
    EmailRecebido,
    Empresa,
    Mensagem,
    Pessoa,
    abrir_chamado,
)

from .normalizacao import NORM_V, normalizar

log = logging.getLogger("fio.ingest")

_ANGULOS = re.compile(r"<([^<>]+)>")

# Cabeçalhos que servidores usam para preservar o autor original ao reencaminhar.
# `Return-Path` NÃO entra: é o envelope, e no encaminhamento automático o envelope
# é o servidor da empresa, nunca o cliente.
_CABECALHOS_ORIGINAIS = ("x-original-from", "x-forwarded-from", "x-original-sender")


def ids_de(cabecalho: str) -> list[str]:
    """Extrai message-ids de In-Reply-To / References."""
    if not cabecalho:
        return []
    achados = _ANGULOS.findall(cabecalho)
    if achados:
        return [f"<{a.strip()}>" for a in achados]
    return [p.strip() for p in cabecalho.split() if p.strip()]


def separar_remetente(bruto: str) -> tuple[str, str]:
    """'Fulano <f@x.com>' -> ('Fulano', 'f@x.com'). Sem nome, usa a parte antes do @."""
    pares = getaddresses([bruto or ""])
    if not pares:
        return "", ""
    nome, endereco = pares[0]
    nome = (nome or "").strip().strip('"')
    endereco = (endereco or "").strip()
    if not nome and endereco:
        nome = endereco.split("@")[0]
    return nome, endereco


def _dominio(endereco: str) -> str:
    return endereco.rsplit("@", 1)[-1].lower() if "@" in endereco else ""


def enderecos_da_empresa(empresa: Empresa) -> set[str]:
    """A caixa que o Fio lê. Quem escreve de lá é a própria empresa, não o cliente."""
    from django.conf import settings

    return {
        e.strip().lower()
        for e in (empresa.caixa_email, (empresa.imap_usuario if empresa.imap_host else getattr(settings, "IMAP_USER", "")))
        if e and e.strip()
    }


def _e_da_empresa(endereco: str, empresa: Empresa) -> bool:
    endereco = (endereco or "").strip().lower()
    if not endereco:
        return True
    proprios = enderecos_da_empresa(empresa)
    if endereco in proprios:
        return True
    return _dominio(endereco) in {_dominio(e) for e in proprios if _dominio(e)}


def _from_do_original_embutido(mime_bytes: bytes) -> "tuple[str, str] | None":
    """Encaminhamento como anexo: o e-mail original vem inteiro, em message/rfc822."""
    try:
        msg = email.message_from_bytes(mime_bytes, policy=email.policy.compat32)
    except Exception:  # noqa: BLE001 — MIME quebrado não pode derrubar o ingest
        return None

    for parte in msg.walk():
        if parte.get_content_type() != "message/rfc822":
            continue
        carga = parte.get_payload()
        embutido: Message | None = None
        if isinstance(carga, list) and carga:
            embutido = carga[0]
        elif isinstance(carga, Message):
            embutido = carga
        if embutido is None:
            continue
        nome, endereco = separar_remetente(embutido.get("From", ""))
        if endereco:
            return nome, endereco
    return None


def remetente_real(mime_bytes: bytes, cabecalhos: dict, empresa: Empresa) -> tuple[str, str]:
    """Quem é o cliente, quando o e-mail pode ter sido reencaminhado pelo servidor.

    Ordem: original embutido → cabeçalhos de reencaminho → `From` (se não for da
    empresa) → `Reply-To` → `From` como último recurso.

    **Nunca** olha o envelope (`Return-Path`): no encaminhamento automático o envelope
    é o servidor da empresa, e usá-lo faria todo chamado nascer com o cliente errado.
    """

    def _primeiro(nome_cabecalho: str) -> str:
        valores = cabecalhos.get(nome_cabecalho) or ()
        if isinstance(valores, str):
            return valores
        return valores[0] if valores else ""

    embutido = _from_do_original_embutido(mime_bytes)
    if embutido:
        return embutido

    for cabecalho in _CABECALHOS_ORIGINAIS:
        nome, endereco = separar_remetente(_primeiro(cabecalho))
        if endereco and not _e_da_empresa(endereco, empresa):
            return nome, endereco

    do_from = separar_remetente(_primeiro("from"))
    if do_from[1] and not _e_da_empresa(do_from[1], empresa):
        return do_from

    # O From é a própria empresa: o servidor reencaminhou. O cliente está no Reply-To.
    nome, endereco = separar_remetente(_primeiro("reply-to"))
    if endereco and not _e_da_empresa(endereco, empresa):
        return nome, endereco

    return do_from


def proxima_ordem(chamado: Chamado) -> int:
    atual = chamado.mensagens.aggregate(m=Max("ordem"))["m"]
    return 0 if atual is None else atual + 1


def chamado_da_thread(empresa: Empresa, refs: list[str]) -> "Chamado | None":
    """Chamado de alguma Mensagem cujo message_id esteja nas referências."""
    if not refs:
        return None
    msg = (
        Mensagem.objects.filter(chamado__empresa=empresa, message_id__in=refs)
        .select_related("chamado")
        .order_by("chamado_id", "ordem")
        .first()
    )
    return msg.chamado if msg else None


class CorrupcaoDetectada(Exception):
    """O texto gravado não bate com o sha256 gravado. Não é caso de seguir em frente."""


class JaDecidido(Exception):
    """Promover ou descartar um e-mail que já saiu da caixa de entrada."""


def ja_recebido(empresa: Empresa, message_id: str) -> bool:
    """Dedupe do ingest: o `UNIQUE(empresa, message_id)` de `EmailRecebido`."""
    if not message_id:
        return False
    return EmailRecebido.objects.filter(empresa=empresa, message_id=message_id).exists()


def receber_email(
    *,
    empresa: Empresa,
    bruto: bytes,
    message_id: str = "",
    remetente_nome: str = "",
    remetente_email: str = "",
    destinatario: str = "",
    assunto: str = "",
    recebido_em=None,
    refs: "list[str] | None" = None,
) -> EmailRecebido:
    """Grava o que veio da caixa. Nenhum filtro por conteúdo: todo e-mail lido entra.

    É a **única** porta de entrada de `EmailRecebido`, e por isso a única origem
    possível de uma `Mensagem` — ver `gravar_mensagem`.
    """
    texto, citacao_offset = normalizar(bruto)

    message_id = (message_id or "").strip()[:998]
    if not message_id:
        # Sem Message-ID não haveria dedupe. Um id derivado do próprio conteúdo faz o
        # mesmo trabalho: o mesmo e-mail lido duas vezes continua sendo um só.
        digest = hashlib.sha256(bruto).hexdigest()
        message_id = f"<sem-message-id-{digest[:40]}@fio.local>"

    return EmailRecebido.objects.create(
        empresa=empresa,
        message_id=message_id,
        recebido_em=recebido_em or timezone.now(),
        remetente_nome=(remetente_nome or "")[:200],
        remetente_email=(remetente_email or "")[:320],
        destinatario=(destinatario or "")[:320],
        assunto=(assunto or "")[:500],
        refs=list(refs or []),
        bruto=bruto,
        texto=texto,
        norm_v=NORM_V,
        citacao_offset=citacao_offset,
        situacao="pendente",
    )


def _limite_de_anexo() -> int:
    from django.conf import settings

    return int(getattr(settings, "ANEXO_MAX_BYTES", 10 * 1024 * 1024))


def salvar_anexos_recebidos(
    email_recebido: EmailRecebido, anexos, maximo: "int | None" = None
) -> int:
    """`anexos`: iterável de objetos com .filename, .content_type e .payload (bytes).

    Anexo acima do limite é recusado e registrado no log — o e-mail entra do mesmo
    jeito, com o texto íntegro. Perder o texto do cliente por causa de um anexo
    grande demais seria trocar o essencial pelo acessório.
    """
    limite = _limite_de_anexo() if maximo is None else maximo
    total = 0
    for a in anexos:
        conteudo = getattr(a, "payload", b"") or b""
        nome = (getattr(a, "filename", "") or "anexo").strip()[:300]
        if len(conteudo) > limite:
            log.warning(
                "Anexo recusado por tamanho: %s (%d bytes > %d) no e-mail %s.",
                nome,
                len(conteudo),
                limite,
                email_recebido.message_id,
            )
            continue
        AnexoRecebido.objects.create(
            email=email_recebido,
            nome=nome,
            mime=(getattr(a, "content_type", "") or "application/octet-stream")[:180],
            arquivo=ContentFile(conteudo, name=nome),
            sha256=hashlib.sha256(conteudo).hexdigest(),
        )
        total += 1
    return total


def gravar_mensagem(*, chamado: Chamado, origem: EmailRecebido) -> Mensagem:
    """Copia `texto` e `bruto` do `EmailRecebido` para uma `Mensagem`, sem alteração.

    É a **única** porta de entrada de `Mensagem`: `Mensagem.save()` recusa qualquer
    objeto que não tenha passado por aqui, e aqui só entra o que já está gravado num
    `EmailRecebido`. Não existe parâmetro de texto — não há como alguém digitar a
    descrição de um chamado (invariante 7).
    """
    if not origem.confere_sha256():
        raise CorrupcaoDetectada(
            f"O texto do e-mail {origem.pk} não bate com o sha256 gravado. "
            "Nada é promovido a partir de conteúdo corrompido."
        )

    mensagem = Mensagem(
        chamado=chamado,
        ordem=proxima_ordem(chamado),
        remetente=origem.remetente[:320],
        destinatario=origem.destinatario[:320],
        assunto=origem.assunto[:500],
        recebido_em=origem.recebido_em,
        bruto=bytes(origem.bruto),
        texto=origem.texto,
        norm_v=origem.norm_v,
        citacao_offset=origem.citacao_offset,
        message_id=origem.message_id[:998],
    )
    mensagem._via_ingest = True
    mensagem.save()

    if mensagem.sha256 != origem.sha256:  # pragma: no cover — defesa, não fluxo
        raise CorrupcaoDetectada(
            f"O sha256 da mensagem {mensagem.pk} não bate com o do e-mail {origem.pk}."
        )
    return mensagem


def copiar_anexos(origem: EmailRecebido, mensagem: Mensagem) -> int:
    """Os anexos do e-mail viram anexos da mensagem. O e-mail continua com os dele."""
    total = 0
    for a in origem.anexos.all():
        with a.arquivo.open("rb") as arquivo:
            conteudo = arquivo.read()
        Anexo.objects.create(
            mensagem=mensagem,
            nome=a.nome,
            mime=a.mime,
            arquivo=ContentFile(conteudo, name=a.nome),
            sha256=a.sha256,
        )
        total += 1
    return total


def _ja_decidido(email_recebido: EmailRecebido) -> JaDecidido:
    fim = (
        "promovido a chamado."
        if email_recebido.situacao == "promovido"
        else "descartado."
    )
    return JaDecidido("Este e-mail já foi " + fim)


@transaction.atomic
def promover(
    email_recebido: EmailRecebido,
    *,
    chamado: "Chamado | None" = None,
    por: "Pessoa | None" = None,
) -> Chamado:
    """O e-mail vira mensagem de um chamado. `por=None` significa promovido pelo sistema.

    Com `chamado`, entra como resposta na conversa que já existe (ordem seguinte).
    Sem `chamado`, abre um chamado novo e a mensagem fica de ordem 0 — a descrição.

    Nenhum texto entra por aqui: o conteúdo é copiado do `EmailRecebido` e mais nada.
    O humano escolhe qual e-mail vira chamado, nunca o que está escrito nele.
    """
    email_recebido = EmailRecebido.objects.select_for_update().get(pk=email_recebido.pk)
    if email_recebido.situacao != "pendente":
        raise _ja_decidido(email_recebido)

    if chamado is None:
        chamado = abrir_chamado(
            empresa=email_recebido.empresa,
            assunto=email_recebido.assunto,
            cliente_nome=email_recebido.remetente_nome,
            cliente_email=email_recebido.remetente_email,
        )

    mensagem = gravar_mensagem(chamado=chamado, origem=email_recebido)
    copiar_anexos(email_recebido, mensagem)

    email_recebido.situacao = "promovido"
    email_recebido.promovido_em = timezone.now()
    email_recebido.promovido_por = por
    email_recebido.chamado = chamado
    email_recebido.save(update_fields=["situacao", "promovido_em", "promovido_por", "chamado"])
    return chamado


@transaction.atomic
def descartar(email_recebido: EmailRecebido, *, por: "Pessoa | None" = None) -> EmailRecebido:
    """Carimba `descartado_em`. O registro continua no banco e continua consultável."""
    email_recebido = EmailRecebido.objects.select_for_update().get(pk=email_recebido.pk)
    if email_recebido.situacao != "pendente":
        raise _ja_decidido(email_recebido)

    email_recebido.situacao = "descartado"
    email_recebido.descartado_em = timezone.now()
    email_recebido.descartado_por = por
    email_recebido.save(update_fields=["situacao", "descartado_em", "descartado_por"])
    return email_recebido
