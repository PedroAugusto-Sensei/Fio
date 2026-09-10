"""Schemas da API.

Nada aqui expõe um campo `situacao` ou `descricao` gravado em Chamado, e nada aqui
aceita texto de mensagem: não existe schema de entrada de chamado (invariante 7).
"""
from datetime import datetime

from ninja import Schema


class Erro(Schema):
    erro: str


class LoginIn(Schema):
    usuario: str
    senha: str


class MeOut(Schema):
    nome: str
    setor: str
    empresa: str
    #: Escopo de tudo que esta pessoa vê. Vem de `request.user.pessoa.empresa`.
    empresa_id: int
    #: "admin" ou "membro". Decide só convidar, editar setores e mexer na caixa.
    pode_configurar_imap: bool = False
    papel: str
    #: A caixa que o Fio lê, e a pasta observada dentro dela.
    caixa_email: str
    pasta_email: str
    #: Falso na empresa que ainda não tem caixa. Não é "quase pronto": sem caixa,
    #: nenhum e-mail entra para esta empresa, e a tela precisa dizer isso.
    caixa_configurada: bool
    iniciais: str


class SetoresOut(Schema):
    setores: list[str]


class ChamadoItem(Schema):
    """Item da lista. `situacao` vem da projeção; `None` = sem registro nenhum."""

    id: int
    codigo: str
    assunto: str
    cliente_nome: str
    trecho_cliente: str
    situacao: str | None = None
    total_registros: int = 0
    ultimo_autor: str | None = None
    ultimo_setor: str | None = None
    ultima_atualizacao: datetime | None = None
    criado_em: datetime


class ChamadosOut(Schema):
    itens: list[ChamadoItem]
    total: int
    pagina: int
    paginas: int
    por_pagina: int
    abertos: int
    caixa_email: str
    pasta_email: str


class AnexoOut(Schema):
    id: int
    nome: str
    mime: str
    url: str


class MensagemOut(Schema):
    id: int
    ordem: int
    remetente: str
    destinatario: str
    assunto: str
    recebido_em: datetime
    texto: str
    citacao_offset: int | None = None
    sha256: str
    anexos: list[AnexoOut] = []


class AutorOut(Schema):
    id: int
    nome: str
    setor: str
    iniciais: str


class RegistroOut(Schema):
    id: int
    autor: AutorOut
    setor: str
    texto: str
    situacao: str
    criado_em: datetime
    editado_em: datetime | None = None
    versao_anterior_id: int | None = None


class ChamadoOut(Schema):
    id: int
    codigo: str
    assunto: str
    cliente_nome: str
    cliente_email: str
    criado_em: datetime
    situacao: str | None = None
    ultima_atualizacao: datetime | None = None
    descricao: MensagemOut | None = None
    mensagens_seguintes: list[MensagemOut] = []
    registros: list[RegistroOut] = []
    quem_registrou: list[AutorOut] = []
    total_mensagens: int = 0


class RegistroIn(Schema):
    texto: str
    situacao: str


class RegistroPublicadoOut(Schema):
    """O registro criado E a nova situação projetada — o front não refaz a busca."""

    registro: RegistroOut
    situacao: str | None = None
    ultima_atualizacao: datetime | None = None
    total_registros: int


# ---------------------------------------------------------------- caixa de entrada

#: Não existe `EmailIn`. Promover e descartar não aceitam corpo nenhum: o humano
#: escolhe **qual** e-mail vira chamado, nunca **o que** está escrito nele.


class AnexoRecebidoOut(Schema):
    id: int
    nome: str
    mime: str
    url: str


class EmailItem(Schema):
    """Linha da caixa de entrada: quem escreveu, sobre o quê, e a primeira linha."""

    id: int
    remetente_nome: str
    remetente_email: str
    assunto: str
    trecho: str
    recebido_em: datetime
    situacao: str
    total_anexos: int = 0
    chamado_id: int | None = None
    chamado_codigo: str | None = None
    promovido_em: datetime | None = None
    promovido_por: str | None = None
    descartado_em: datetime | None = None
    descartado_por: str | None = None


class EmailsOut(Schema):
    itens: list[EmailItem]
    total: int
    pagina: int
    paginas: int
    por_pagina: int
    #: Quantos esperam decisão. É o número do contador na navegação.
    pendentes: int
    caixa_email: str
    pasta_email: str


class EmailOut(EmailItem):
    """O e-mail aberto: texto inteiro, com a citação marcada e nunca cortada."""

    destinatario: str
    texto: str
    citacao_offset: int | None = None
    sha256: str
    anexos: list[AnexoRecebidoOut] = []


class PendentesOut(Schema):
    pendentes: int


class PromovidoOut(Schema):
    """Depois de promover, o front navega direto para o chamado criado."""

    chamado_id: int
    chamado_codigo: str
    email: EmailItem


# ---------------------------------------------------------------- empresa e contas
#
# Nenhum schema daqui carrega palavra de cliente: são dados de conta (nome, e-mail,
# senha, setor). A descrição do chamado continua nascendo só de `EmailRecebido`.


class RegistrarEmpresaIn(Schema):
    """Cadastro da empresa junto com a conta de quem cadastrou. Um passo, sem wizard.

    A configuração IMAP não entra aqui: a caixa é coisa de admin, depois, e a empresa
    existe antes de ter caixa.
    """

    empresa_nome: str
    nome: str
    email: str
    senha: str
    setores: list[str] = []


class ConviteIn(Schema):
    """`email` e `setor` são sugestão de preenchimento, não restrição de quem aceita."""

    email: str = ""
    setor: str = ""


class ConviteCriadoOut(Schema):
    id: int
    token: str
    #: O link inteiro, pronto para a pessoa colar onde quiser. O Fio não manda e-mail.
    url: str
    email: str
    setor: str
    expira_em: datetime


class ConviteItem(Schema):
    id: int
    email: str
    setor: str
    url: str
    criado_em: datetime
    expira_em: datetime
    criado_por: str


class ConvitesOut(Schema):
    itens: list[ConviteItem]


class ConvitePublicoOut(Schema):
    """O que a tela de aceitar convite pode saber sem sessão: o nome e os setores.

    Nada além disso — nem chamado, nem gente, nem a caixa de e-mail da empresa.
    """

    empresa_nome: str
    setores: list[str]
    email: str
    setor: str


class AceitarConviteIn(Schema):
    nome: str
    email: str
    senha: str
    setor: str


class MembroOut(Schema):
    id: int
    nome: str
    setor: str
    papel: str
    iniciais: str
    #: Quem se cadastrou pela interface entra com o e-mail como usuário.
    usuario: str


class MembrosOut(Schema):
    itens: list[MembroOut]


class EmpresaIn(Schema):
    """Remover um setor daqui não mexe no `setor` já gravado em nenhum `Registro`:
    lá é cópia histórica de quem agiu, e reescrever histórico não é opção."""

    nome: str
    setores: list[str]


class EmpresaOut(Schema):
    id: int
    nome: str
    setores: list[str]
    caixa_email: str
    pasta_email: str


class ImapIn(Schema):
    host: str
    usuario: str
    caixa_email: str
    pasta: str = "INBOX"
    senha: str = ""


class ImapOut(Schema):
    host: str
    usuario: str
    caixa_email: str
    pasta: str
    senha_configurada: bool
