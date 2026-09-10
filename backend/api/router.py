"""API do Fio (django-ninja, prefixo /api).

Não existe endpoint para "atualizar status" (invariante 4), para editar a descrição,
nem para **criar** chamado ou mensagem (invariante 7). Chamado nasce do ingest de
e-mail e de mais lugar nenhum. A situação sempre vem junto com um registro novo.

Toda rota autenticada aqui parte de `core.escopo`, que resolve a empresa pela pessoa
logada. Nenhuma rota monta `Modelo.objects.filter(...)` na mão, e nenhuma usa
`Empresa.objects.first()`: o escopo sai de `request.user.pessoa.empresa` e de mais
nada. Chamado de outra empresa devolve 404, nunca 403.
"""
import logging

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI, Query, Status
from ninja.errors import AuthenticationError, HttpError, ValidationError as NinjaValidationError
from ninja.security import django_auth
from ninja.utils import check_csrf

from core.escopo import (
    admin_de,
    chamados_de,
    convites_de,
    emails_de,
    membros_de,
    pessoa_de,
    registros_de,
)
from core.models import (
    SITUACOES_EMAIL_VALIDAS,
    SITUACOES_VALIDAS,
    Chamado,
    Convite,
    EmailRecebido,
    Empresa,
    Mensagem,
    Pessoa,
    Registro,
    chamados_com_situacao,
    situacao_de,
)
from ingest.credenciais import cifrar
from ingest.entrada import CorrupcaoDetectada, JaDecidido, descartar, promover
from .schemas import (
    AceitarConviteIn,
    ChamadoOut,
    ChamadosOut,
    ConviteCriadoOut,
    ConviteIn,
    ConvitePublicoOut,
    ConvitesOut,
    EmailItem,
    EmailOut,
    EmailsOut,
    EmpresaIn,
    EmpresaOut,
    Erro,
    ImapIn,
    ImapOut,
    LoginIn,
    MeOut,
    MembrosOut,
    PendentesOut,
    PromovidoOut,
    RegistrarEmpresaIn,
    RegistroIn,
    RegistroOut,
    RegistroPublicadoOut,
    SetoresOut,
)

log = logging.getLogger("fio.api")

POR_PAGINA = 25

# Aberto = tudo que não está concluído, inclusive o chamado sem registro nenhum.
ABERTOS = Q(situacao__isnull=True) | ~Q(situacao="concluido")

# `django_auth` é SessionAuth com csrf=True: cookie de sessão HttpOnly + header X-CSRFToken.
api = NinjaAPI(
    title="Fio",
    version="1.0.0",
    description="Chamados com as palavras do cliente.",
    auth=django_auth,
    urls_namespace="fio",
)


# ---------------------------------------------------------------- erros em português


@api.exception_handler(AuthenticationError)
def nao_autenticado(request, exc):
    return api.create_response(request, {"erro": "Faça login para continuar."}, status=401)


@api.exception_handler(HttpError)
def erro_http(request, exc):
    return api.create_response(request, {"erro": str(exc)}, status=exc.status_code)


@api.exception_handler(Http404)
def nao_encontrado(request, exc):
    return api.create_response(request, {"erro": "Não encontrado."}, status=404)


@api.exception_handler(NinjaValidationError)
def dados_invalidos(request, exc):
    return api.create_response(
        request, {"erro": "Dados inválidos na requisição."}, status=422
    )


# ---------------------------------------------------------------- ajudantes


def _anexo(a, request):
    return {"id": a.id, "nome": a.nome, "mime": a.mime, "url": request.build_absolute_uri(a.arquivo.url)}


def _mensagem(m: Mensagem, request):
    return {
        "id": m.id,
        "ordem": m.ordem,
        "remetente": m.remetente,
        "destinatario": m.destinatario,
        "assunto": m.assunto,
        "recebido_em": m.recebido_em,
        "texto": m.texto,
        "citacao_offset": m.citacao_offset,
        "sha256": m.sha256,
        "anexos": [_anexo(a, request) for a in m.anexos.all()],
    }


def _autor(p: Pessoa):
    return {"id": p.id, "nome": p.nome, "setor": p.setor, "iniciais": p.iniciais}


def _registro(r: Registro):
    return {
        "id": r.id,
        "autor": _autor(r.autor),
        "setor": r.setor,
        "texto": r.texto,
        "situacao": r.situacao,
        "criado_em": r.criado_em,
        "editado_em": r.editado_em,
        "versao_anterior_id": r.versao_anterior_id,
    }


# ---------------------------------------------------------------- sessão


@api.post("/auth/login", auth=None, response={200: MeOut, 400: Erro, 403: Erro}, url_name="login")
def entrar(request, dados: LoginIn):
    # `auth=None` desliga a checagem do django_auth; o CSRF continua obrigatório aqui.
    if check_csrf(request) is not None:
        return Status(403, {"erro": "Sessão expirada. Recarregue a página e tente de novo."})
    user = authenticate(request, username=dados.usuario.strip(), password=dados.senha)
    if user is None or not user.is_active:
        return Status(400, {"erro": "Usuário ou senha incorretos."})
    pessoa = Pessoa.objects.select_related("empresa").filter(user=user).first()
    if pessoa is None:
        return Status(400, {"erro": "Seu usuário não está vinculado a nenhuma empresa."})
    login(request, user)
    return Status(200, _me(pessoa))


@api.post("/auth/logout", auth=None, url_name="logout")
def sair(request):
    logout(request)
    return {"ok": True}


def _me(pessoa: Pessoa):
    return {
        "nome": pessoa.nome,
        "setor": pessoa.setor,
        "empresa": pessoa.empresa.nome,
        "empresa_id": pessoa.empresa_id,
        "papel": pessoa.papel,
        "pode_configurar_imap": pessoa.empresa.criador_id == pessoa.user_id,
        "caixa_email": pessoa.empresa.caixa_email,
        "pasta_email": pessoa.empresa.imap_pasta if pessoa.empresa.imap_host else pasta_lida(),
        "caixa_configurada": bool(pessoa.empresa.caixa_email),
        "iniciais": pessoa.iniciais,
    }


def pasta_lida() -> str:
    """A pasta que o ingest observa. Configuração, não caminho de código."""
    return settings.IMAP_FOLDER or "INBOX"


@api.get("/me", response=MeOut)
def me(request):
    return _me(pessoa_de(request))


@api.get("/setores", response=SetoresOut)
def setores(request):
    empresa = pessoa_de(request).empresa
    lista = list(empresa.setores or [])
    return {"setores": lista}


# ---------------------------------------------------------------- lista de chamados


@api.get("/chamados", response=ChamadosOut)
def listar_chamados(
    request,
    busca: str = Query(""),
    situacao: str = Query(""),
    cliente: str = Query(""),
    meus: bool = Query(False),
    page: int = Query(1),
):
    """Lista com a situação projetada. Uma consulta, sem N+1."""
    pessoa = pessoa_de(request)
    qs = chamados_com_situacao(chamados_de(pessoa).filter(arquivado_em__isnull=True))

    termo = busca.strip()
    if termo:
        consulta = SearchQuery(termo, config="portuguese")
        qs = qs.filter(
            Q(mensagens__search=consulta)
            | Q(registros__search=consulta)
            | Q(assunto__icontains=termo)
        ).distinct()

    if cliente.strip():
        qs = qs.filter(cliente_nome__iexact=cliente.strip())

    chip = situacao.strip()
    if chip == "abertos":
        # Sem registro também está aberto: NULL não pode sumir dentro de um NOT.
        qs = qs.filter(ABERTOS)
    elif chip == "sem_registro":
        qs = qs.filter(situacao__isnull=True)
    elif chip == "concluidos":
        qs = qs.filter(situacao="concluido")
    elif chip in SITUACOES_VALIDAS:
        qs = qs.filter(situacao=chip)
    elif chip:
        return api.create_response(request, {"erro": f"Filtro de situação desconhecido: {chip}."}, status=400)

    if meus:
        qs = qs.filter(registros__autor=pessoa).distinct()

    # Chamado mexido mais recentemente primeiro; sem registro, vale a data de entrada.
    qs = qs.order_by(
        Coalesce("ultima_atualizacao", "criado_em").desc(), "-criado_em"
    )

    abertos = (
        chamados_com_situacao(chamados_de(pessoa).filter(arquivado_em__isnull=True))
        .filter(ABERTOS)
        .count()
    )

    paginador = Paginator(qs, POR_PAGINA)
    pagina = paginador.get_page(max(1, page))

    # Um SELECT só para todos os trechos da página — nada de N+1.
    ids = [c.id for c in pagina.object_list]
    trechos = {
        m.chamado_id: m.trecho()
        for m in Mensagem.objects.filter(chamado_id__in=ids, ordem=0)
    }

    itens = [
        {
            "id": c.id,
            "codigo": c.codigo,
            "assunto": c.assunto,
            "cliente_nome": c.cliente_nome,
            "trecho_cliente": trechos.get(c.id, ""),
            "situacao": c.situacao,
            "total_registros": c.total_registros,
            "ultimo_autor": c.ultimo_autor,
            "ultimo_setor": c.ultimo_setor,
            "ultima_atualizacao": c.ultima_atualizacao,
            "criado_em": c.criado_em,
        }
        for c in pagina.object_list
    ]

    return {
        "itens": itens,
        "total": paginador.count,
        "pagina": pagina.number,
        "paginas": paginador.num_pages,
        "por_pagina": POR_PAGINA,
        "abertos": abertos,
        "caixa_email": pessoa.empresa.caixa_email,
        "pasta_email": pessoa.empresa.imap_pasta if pessoa.empresa.imap_host else pasta_lida(),
    }


# ---------------------------------------------------------------- um chamado


def _chamado_completo(chamado: Chamado, request):
    mensagens = list(chamado.mensagens.prefetch_related("anexos").order_by("ordem"))
    registros = list(
        chamado.registros.filter(versao_seguinte__isnull=True)
        .select_related("autor")
        .order_by("criado_em")
    )

    vistos, quem = set(), []
    for r in registros:
        if r.autor_id not in vistos:
            vistos.add(r.autor_id)
            quem.append(_autor(r.autor))

    descricao = mensagens[0] if mensagens else None
    return {
        "id": chamado.id,
        "codigo": chamado.codigo,
        "assunto": chamado.assunto,
        "cliente_nome": chamado.cliente_nome,
        "cliente_email": chamado.cliente_email,
        "criado_em": chamado.criado_em,
        "situacao": registros[-1].situacao if registros else None,
        "ultima_atualizacao": registros[-1].criado_em if registros else None,
        "descricao": _mensagem(descricao, request) if descricao else None,
        "mensagens_seguintes": [_mensagem(m, request) for m in mensagens[1:]],
        "registros": [_registro(r) for r in registros],
        "quem_registrou": quem,
        "total_mensagens": len(mensagens),
    }


@api.get("/chamados/{int:chamado_id}", response=ChamadoOut)
def ver_chamado(request, chamado_id: int):
    pessoa = pessoa_de(request)
    chamado = get_object_or_404(chamados_de(pessoa), pk=chamado_id)
    return _chamado_completo(chamado, request)


@api.get("/chamados/{int:chamado_id}/registros", response=list[RegistroOut])
def listar_registros(request, chamado_id: int, historico: bool = Query(False)):
    """Sem `historico`, só os ativos. Com `historico=1`, todas as versões já escritas."""
    pessoa = pessoa_de(request)
    chamado = get_object_or_404(chamados_de(pessoa), pk=chamado_id)
    qs = chamado.registros.select_related("autor").order_by("criado_em")
    if not historico:
        qs = qs.filter(versao_seguinte__isnull=True)
    return [_registro(r) for r in qs]


# ---------------------------------------------------------------- publicar registro


@api.post(
    "/chamados/{int:chamado_id}/registros",
    response={200: RegistroPublicadoOut, 400: Erro},
)
def publicar_registro(request, chamado_id: int, dados: RegistroIn):
    """A tese: acrescenta um registro. Nenhuma Mensagem é tocada."""
    pessoa = pessoa_de(request)
    chamado = get_object_or_404(chamados_de(pessoa), pk=chamado_id)

    texto = dados.texto.strip()
    if not texto:
        return Status(400, {"erro": "Escreva o que foi feito antes de publicar."})
    if dados.situacao not in SITUACOES_VALIDAS:
        return Status(400, {"erro": "Escolha em que situação o chamado fica depois deste registro."})

    with transaction.atomic():
        registro = Registro.objects.create(
            chamado=chamado,
            autor=pessoa,
            setor=pessoa.setor,  # copiado no momento da escrita
            texto=texto,
            situacao=dados.situacao,
        )

    return Status(200, {
        "registro": _registro(registro),
        "situacao": situacao_de(chamado),
        "ultima_atualizacao": registro.criado_em,
        "total_registros": chamado.registros.filter(versao_seguinte__isnull=True).count(),
    })


@api.put("/registros/{int:registro_id}", response={200: RegistroPublicadoOut, 400: Erro, 403: Erro})
def editar_registro(request, registro_id: int, dados: RegistroIn):
    """Não faz UPDATE no texto: cria uma versão nova apontando para a antiga."""
    pessoa = pessoa_de(request)
    antigo = get_object_or_404(
        registros_de(pessoa), pk=registro_id, versao_seguinte__isnull=True
    )
    if antigo.autor_id != pessoa.id:
        return Status(403, {"erro": "Só o autor pode corrigir o próprio registro."})

    texto = dados.texto.strip()
    if not texto:
        return Status(400, {"erro": "Escreva o que foi feito antes de publicar."})
    if dados.situacao not in SITUACOES_VALIDAS:
        return Status(400, {"erro": "Escolha em que situação o chamado fica depois deste registro."})

    with transaction.atomic():
        novo = Registro.objects.create(
            chamado=antigo.chamado,
            autor=pessoa,
            setor=antigo.setor,
            texto=texto,
            situacao=dados.situacao,
            editado_em=timezone.now(),
            versao_anterior=antigo,
        )

    return Status(200, {
        "registro": _registro(novo),
        "situacao": situacao_de(antigo.chamado),
        "ultima_atualizacao": novo.criado_em,
        "total_registros": antigo.chamado.registros.filter(versao_seguinte__isnull=True).count(),
    })


# ---------------------------------------------------------------- caixa de entrada

# Entre a caixa de e-mail e o chamado existe uma etapa: todo e-mail lido é gravado,
# e um humano decide quais viram chamado. O humano escolhe **qual** e-mail vira
# chamado — nunca **o que** está escrito nele. Por isso nenhum endpoint daqui aceita
# corpo na requisição, e continua não existindo `POST /chamados`.


def _email_item(e: EmailRecebido):
    return {
        "id": e.id,
        "remetente_nome": e.remetente_nome,
        "remetente_email": e.remetente_email,
        "assunto": e.assunto,
        "trecho": e.trecho(),
        "recebido_em": e.recebido_em,
        "situacao": e.situacao,
        "total_anexos": getattr(e, "total_anexos", None) or e.anexos.count(),
        "chamado_id": e.chamado_id,
        "chamado_codigo": e.chamado.codigo if e.chamado_id else None,
        "promovido_em": e.promovido_em,
        "promovido_por": e.promovido_por.nome if e.promovido_por_id else None,
        "descartado_em": e.descartado_em,
        "descartado_por": e.descartado_por.nome if e.descartado_por_id else None,
    }


def _email_completo(e: EmailRecebido, request):
    item = _email_item(e)
    item.update(
        {
            "destinatario": e.destinatario,
            # O texto vai inteiro. `citacao_offset` marca onde começa a citação;
            # quem decide a cor é a tela, e nada é apagado no caminho.
            "texto": e.texto,
            "citacao_offset": e.citacao_offset,
            "sha256": e.sha256,
            "anexos": [
                {
                    "id": a.id,
                    "nome": a.nome,
                    "mime": a.mime,
                    "url": request.build_absolute_uri(a.arquivo.url),
                }
                for a in e.anexos.all()
            ],
        }
    )
    return item


def _emails_da_empresa(pessoa: Pessoa):
    return emails_de(pessoa).select_related("chamado", "promovido_por", "descartado_por")


def pendentes_de(pessoa: Pessoa) -> int:
    return emails_de(pessoa).filter(situacao="pendente").count()


@api.get("/emails/contagem", response=PendentesOut)
def contar_pendentes(request):
    """O contador da navegação. É o que faz alguém lembrar de olhar a caixa."""
    return {"pendentes": pendentes_de(pessoa_de(request))}


@api.get("/emails", response=EmailsOut)
def listar_emails(request, situacao: str = Query("pendente"), page: int = Query(1)):
    """Mais recentes primeiro. Nada some da interface para sempre: descartado é filtro."""
    pessoa = pessoa_de(request)
    qs = _emails_da_empresa(pessoa)

    filtro = (situacao or "pendente").strip()
    if filtro and filtro != "todos":
        if filtro not in SITUACOES_EMAIL_VALIDAS:
            return api.create_response(
                request, {"erro": f"Filtro de situação desconhecido: {filtro}."}, status=400
            )
        qs = qs.filter(situacao=filtro)

    qs = qs.annotate(total_anexos=Count("anexos")).order_by("-recebido_em", "-id")

    paginador = Paginator(qs, POR_PAGINA)
    pagina = paginador.get_page(max(1, page))

    return {
        "itens": [_email_item(e) for e in pagina.object_list],
        "total": paginador.count,
        "pagina": pagina.number,
        "paginas": paginador.num_pages,
        "por_pagina": POR_PAGINA,
        "pendentes": pendentes_de(pessoa),
        "caixa_email": pessoa.empresa.caixa_email,
        "pasta_email": pessoa.empresa.imap_pasta if pessoa.empresa.imap_host else pasta_lida(),
    }


@api.get("/emails/{int:email_id}", response=EmailOut)
def ver_email(request, email_id: int):
    pessoa = pessoa_de(request)
    recebido = get_object_or_404(
        _emails_da_empresa(pessoa).prefetch_related("anexos"), pk=email_id
    )
    return _email_completo(recebido, request)


@api.post(
    "/emails/{int:email_id}/promover",
    response={200: PromovidoOut, 409: Erro, 500: Erro},
)
def promover_email(request, email_id: int):
    """Cria o chamado com as palavras exatas do cliente. Não aceita campo nenhum.

    Se vier corpo na requisição — `assunto`, `texto`, o que for — ele é ignorado:
    a operação não declara schema de entrada, e não existe entrada de texto humano aqui.
    """
    pessoa = pessoa_de(request)
    recebido = get_object_or_404(_emails_da_empresa(pessoa), pk=email_id)

    try:
        chamado = promover(recebido, por=pessoa)
    except JaDecidido as exc:
        return Status(409, {"erro": str(exc)})
    except CorrupcaoDetectada as exc:
        # Não é caso de seguir: o texto gravado não bate com o número gravado.
        log.error("Corrupção ao promover o e-mail %s: %s", email_id, exc)
        return Status(
            500,
            {"erro": "O texto gravado deste e-mail não confere. Nada foi criado."},
        )

    recebido.refresh_from_db()
    return Status(
        200,
        {
            "chamado_id": chamado.id,
            "chamado_codigo": chamado.codigo,
            "email": _email_item(recebido),
        },
    )


@api.post("/emails/{int:email_id}/descartar", response={200: EmailItem, 409: Erro})
def descartar_email(request, email_id: int):
    """Carimba `descartado_em`. O e-mail continua no banco e continua consultável."""
    pessoa = pessoa_de(request)
    recebido = get_object_or_404(_emails_da_empresa(pessoa), pk=email_id)

    try:
        descartar(recebido, por=pessoa)
    except JaDecidido as exc:
        return Status(409, {"erro": str(exc)})

    recebido.refresh_from_db()
    return Status(200, _email_item(recebido))


# ---------------------------------------------------------------- empresa e contas
#
# Não existe senha compartilhada de empresa. Cada funcionário tem conta própria porque
# `Registro.autor` e `Registro.setor` são a resposta do produto para "quem agiu": com
# login compartilhado o feed do chamado viraria ficção. A empresa é um container, não
# uma credencial.
#
# O que um admin pode e um membro não pode: convidar pessoas, editar a lista de setores
# e mexer na configuração da caixa. Ler chamado e publicar registro é de todos —
# permissão por setor continua fora de escopo, e isso é parte da tese.

#: Usado quando o cadastro não manda setor nenhum. É palpite razoável, não obrigação:
#: o admin muda a lista depois, em `PUT /empresa`.
SETORES_PADRAO = ["Suporte", "Produto", "Desenvolvimento", "QA", "Implantação"]

MINIMO_DA_SENHA = 8

#: `login()` precisa do backend explícito quando o usuário não veio de `authenticate()`.
BACKEND_DE_SESSAO = "django.contrib.auth.backends.ModelBackend"

CSRF_EXPIRADO = "Sessão expirada. Recarregue a página e tente de novo."


def _uma_linha(texto: str, limite: int) -> str:
    return " ".join((texto or "").split())[:limite]


def _limpar_setores(setores) -> list[str]:
    """Tira espaço sobrando, vazio e repetido, preservando a ordem que a pessoa digitou."""
    limpos: list[str] = []
    for setor in setores or []:
        nome = _uma_linha(str(setor), 80)
        if nome and nome not in limpos:
            limpos.append(nome)
    return limpos


def _email_valido(email: str) -> str:
    email = (email or "").strip().lower()
    try:
        validate_email(email)
    except DjangoValidationError:
        raise HttpError(400, "Informe um e-mail válido.") from None
    if len(email) > 150:
        # O e-mail é o nome de usuário, e `User.username` cabe 150 caracteres.
        raise HttpError(400, "Este e-mail é longo demais para virar nome de usuário.")
    return email


def _senha_valida(senha: str) -> str:
    if len(senha or "") < MINIMO_DA_SENHA:
        raise HttpError(400, f"A senha precisa de pelo menos {MINIMO_DA_SENHA} caracteres.")
    return senha


def _email_livre(email: str) -> None:
    if User.objects.filter(Q(username__iexact=email) | Q(email__iexact=email)).exists():
        raise HttpError(400, "Já existe uma conta com este e-mail. Entre com ela ou use outro.")


def _criar_conta(*, empresa: Empresa, nome: str, email: str, senha: str, setor: str, papel: str):
    """O e-mail é o nome de usuário: quem se cadastra entra com o próprio e-mail."""
    user = User.objects.create_user(username=email, email=email, password=senha, first_name=nome)
    return Pessoa.objects.create(empresa=empresa, user=user, nome=nome, setor=setor, papel=papel)


@api.post(
    "/auth/registrar-empresa",
    auth=None,
    response={200: MeOut, 400: Erro, 403: Erro},
    url_name="registrar_empresa",
)
def registrar_empresa(request, dados: RegistrarEmpresaIn):
    """Cria a empresa, a conta de quem cadastrou (admin) e já entra. Um passo só.

    A configuração da caixa de e-mail **não** entra aqui: a empresa existe antes de
    ter caixa, e enquanto não tiver, nenhum e-mail entra para ela.
    """
    if check_csrf(request) is not None:
        return Status(403, {"erro": CSRF_EXPIRADO})

    nome_empresa = _uma_linha(dados.empresa_nome, 200)
    if not nome_empresa:
        raise HttpError(400, "Escreva o nome da sua empresa.")

    nome = _uma_linha(dados.nome, 200)
    if not nome:
        raise HttpError(400, "Escreva seu nome.")

    email = _email_valido(dados.email)
    _senha_valida(dados.senha)
    _email_livre(email)

    setores = _limpar_setores(dados.setores) or list(SETORES_PADRAO)

    try:
        with transaction.atomic():
            empresa = Empresa.objects.create(nome=nome_empresa, setores=setores)
            pessoa = _criar_conta(
                empresa=empresa,
                nome=nome,
                email=email,
                senha=dados.senha,
                # Quem cadastra fica no primeiro setor da lista; troca depois se quiser.
                setor=setores[0],
                papel="admin",
            )
            empresa.criador = pessoa.user
            empresa.save(update_fields=["criador"])
    except IntegrityError:  # dois cadastros com o mesmo e-mail no mesmo instante
        raise HttpError(400, "Já existe uma conta com este e-mail. Entre com ela.") from None

    login(request, pessoa.user, backend=BACKEND_DE_SESSAO)
    return Status(200, _me(pessoa))


# ---------------------------------------------------------------- convites


def _url_do_convite(request, token: str) -> str:
    """O link que a pessoa convidada vai abrir.

    O Fio não manda e-mail (está fora de escopo): quem convida copia este link e
    entrega pelo canal que a empresa já usa.
    """
    base = (request.headers.get("Origin") or "").strip().rstrip("/")
    if not base:
        base = request.build_absolute_uri("/").rstrip("/")
    return f"{base}/convite/{token}"


def _convite_item(convite: Convite, request):
    return {
        "id": convite.id,
        "email": convite.email,
        "setor": convite.setor,
        "url": _url_do_convite(request, convite.token),
        "criado_em": convite.criado_em,
        "expira_em": convite.expira_em,
        "criado_por": convite.criado_por.nome,
    }


def _convite_aberto(token: str) -> Convite:
    """O convite do token, se ele ainda aceita alguém.

    Usado devolve 410, expirado devolve 410, inexistente devolve 404 — e nenhum dos
    três conta nada sobre a empresa.
    """
    convite = Convite.objects.select_related("empresa").filter(token=token).first()
    if convite is None:
        raise HttpError(404, "Este convite não existe.")
    if convite.usado:
        raise HttpError(410, "Este convite já foi usado.")
    if convite.expirado:
        raise HttpError(410, "Este convite expirou. Peça um novo a quem administra a empresa.")
    return convite


@api.post("/convites", response={200: ConviteCriadoOut, 400: Erro, 403: Erro})
def criar_convite(request, dados: ConviteIn):
    """Gera o link. `email` e `setor` são sugestão de preenchimento, não restrição."""
    pessoa = admin_de(request)

    email = (dados.email or "").strip().lower()
    if email:
        email = _email_valido(email)

    setor = _uma_linha(dados.setor, 80)
    if setor and setor not in list(pessoa.empresa.setores or []):
        raise HttpError(400, "Este setor não está na lista da empresa.")

    convite = Convite.objects.create(
        empresa=pessoa.empresa, criado_por=pessoa, email=email, setor=setor
    )
    return Status(
        200,
        {
            "id": convite.id,
            "token": convite.token,
            "url": _url_do_convite(request, convite.token),
            "email": convite.email,
            "setor": convite.setor,
            "expira_em": convite.expira_em,
        },
    )


@api.get("/convites", response=ConvitesOut)
def listar_convites(request):
    """Só os que ainda aceitam alguém: usado ou expirado não é convite pendente."""
    pessoa = admin_de(request)
    pendentes = (
        convites_de(pessoa)
        .filter(usado_em__isnull=True, expira_em__gt=timezone.now())
        .select_related("criado_por")
    )
    return {"itens": [_convite_item(c, request) for c in pendentes]}


# A rota de `id` vem **antes** da de `token`: as duas viram padrões de URL diferentes,
# e o primeiro que casa é o que responde. Com a de token na frente, um DELETE em
# /convites/7 bateria nela e voltaria 405.
@api.delete("/convites/{int:convite_id}", response={200: None, 403: Erro, 404: Erro})
def revogar_convite(request, convite_id: int):
    """Revoga um convite que ninguém usou. Link revogado não abre mais."""
    pessoa = admin_de(request)
    convite = get_object_or_404(convites_de(pessoa), pk=convite_id, usado_em__isnull=True)
    convite.delete()
    return Status(200, None)


@api.get(
    "/convites/{str:token}",
    auth=None,
    response={200: ConvitePublicoOut, 404: Erro, 410: Erro},
)
def ver_convite(request, token: str):
    """Sem sessão: é a tela de quem ainda não tem conta.

    Devolve o nome da empresa e os setores, e nada mais. Nem chamado, nem gente, nem
    a caixa de e-mail — um link vazado não pode virar janela para dentro da empresa.
    """
    convite = _convite_aberto(token)
    return Status(
        200,
        {
            "empresa_nome": convite.empresa.nome,
            "setores": list(convite.empresa.setores or []),
            "email": convite.email,
            "setor": convite.setor,
        },
    )


@api.post(
    "/convites/{str:token}/aceitar",
    auth=None,
    response={200: MeOut, 400: Erro, 403: Erro, 404: Erro, 410: Erro},
)
def aceitar_convite(request, token: str, dados: AceitarConviteIn):
    """Cria a conta da pessoa dentro da empresa do convite e já entra."""
    if check_csrf(request) is not None:
        return Status(403, {"erro": CSRF_EXPIRADO})

    convite = _convite_aberto(token)

    nome = _uma_linha(dados.nome, 200)
    if not nome:
        raise HttpError(400, "Escreva seu nome.")

    email = _email_valido(dados.email)
    _senha_valida(dados.senha)
    _email_livre(email)

    setor = _uma_linha(dados.setor, 80)
    if setor not in list(convite.empresa.setores or []):
        raise HttpError(400, "Escolha um dos setores da empresa.")

    try:
        with transaction.atomic():
            # Dois cliques no mesmo link não podem criar duas contas com um convite.
            travado = (
                Convite.objects.select_for_update().select_related("empresa").get(pk=convite.pk)
            )
            if not travado.valido:
                raise HttpError(410, "Este convite já foi usado.")

            pessoa = _criar_conta(
                empresa=travado.empresa,
                nome=nome,
                email=email,
                senha=dados.senha,
                setor=setor,
                papel="membro",
            )
            travado.usado_em = timezone.now()
            travado.usado_por = pessoa
            travado.save(update_fields=["usado_em", "usado_por"])
    except IntegrityError:
        raise HttpError(400, "Já existe uma conta com este e-mail. Entre com ela.") from None

    login(request, pessoa.user, backend=BACKEND_DE_SESSAO)
    return Status(200, _me(pessoa))


# ---------------------------------------------------------------- membros e empresa


@api.get("/membros", response=MembrosOut)
def listar_membros(request):
    """Visível a todo mundo: saber quem está aqui é parte de todos lerem tudo."""
    pessoa = pessoa_de(request)
    pessoas = membros_de(pessoa).select_related("user").order_by("nome")
    return {
        "itens": [
            {
                "id": p.id,
                "nome": p.nome,
                "setor": p.setor,
                "papel": p.papel,
                "iniciais": p.iniciais,
                "usuario": p.user.username,
            }
            for p in pessoas
        ]
    }


@api.put("/empresa", response={200: EmpresaOut, 400: Erro, 403: Erro})
def editar_empresa(request, dados: EmpresaIn):
    """Nome e lista de setores. A caixa de e-mail não se mexe por aqui.

    Tirar um setor da lista **não** altera o `setor` já gravado em nenhum `Registro`:
    lá é cópia histórica de quem agiu, e reescrever histórico não é opção.
    """
    pessoa = admin_de(request)

    nome = _uma_linha(dados.nome, 200)
    if not nome:
        raise HttpError(400, "Escreva o nome da empresa.")

    setores = _limpar_setores(dados.setores)
    if not setores:
        raise HttpError(400, "A empresa precisa de pelo menos um setor.")

    empresa = pessoa.empresa
    empresa.nome = nome
    empresa.setores = setores
    empresa.save(update_fields=["nome", "setores"])

    return Status(
        200,
        {
            "id": empresa.id,
            "nome": empresa.nome,
            "setores": list(empresa.setores),
            "caixa_email": empresa.caixa_email,
            "pasta_email": pessoa.empresa.imap_pasta if pessoa.empresa.imap_host else pasta_lida(),
        },
    )


def _empresa_imap(request):
    pessoa = pessoa_de(request)
    if pessoa.empresa.criador_id != pessoa.user_id:
        raise HttpError(403, "Só quem criou a conta da empresa pode configurar o IMAP.")
    return pessoa.empresa


def _imap_out(empresa):
    return dict(host=empresa.imap_host, usuario=empresa.imap_usuario,
                caixa_email=empresa.caixa_email, pasta=empresa.imap_pasta,
                senha_configurada=bool(empresa.imap_senha))


@api.get("/empresa/imap", response=ImapOut)
def obter_imap(request):
    return _imap_out(_empresa_imap(request))


@api.put("/empresa/imap", response=ImapOut)
def salvar_imap(request, dados: ImapIn):
    empresa = _empresa_imap(request)
    host, usuario, pasta = dados.host.strip(), dados.usuario.strip(), dados.pasta.strip()
    if (not host or len(host) > 253 or any(c in host for c in "/:@ \r\n")
            or not usuario or len(usuario) > 254 or not pasta or len(pasta) > 255
            or any(c in usuario + pasta for c in "\r\n")):
        raise HttpError(400, "Informe servidor, usuário e pasta válidos.")
    email = _email_valido(dados.caixa_email)
    if not dados.senha and (not empresa.imap_senha or host != empresa.imap_host or usuario != empresa.imap_usuario):
        raise HttpError(400, "Informe a senha para esta conexão IMAP.")
    empresa.imap_host, empresa.imap_usuario, empresa.imap_pasta = host, usuario, pasta
    empresa.caixa_email = email
    if dados.senha:
        empresa.imap_senha = cifrar(dados.senha)
    try:
        with transaction.atomic():
            empresa.save(update_fields=["imap_host", "imap_usuario", "imap_pasta", "imap_senha", "caixa_email"])
    except IntegrityError:
        raise HttpError(400, "Esta caixa já está configurada em outra empresa.") from None
    return _imap_out(empresa)
