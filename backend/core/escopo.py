"""Escopo por empresa. Um lugar só, usado por toda rota autenticada.

Toda consulta autenticada nasce de `request.user.pessoa.empresa` e de mais nada. Não
existe middleware de tenant, subdomínio nem cabeçalho de empresa: o escopo sai da
pessoa logada, e é isso que impede o chamado de uma empresa aparecer para outra.

**Nunca** `Empresa.objects.first()`. Enquanto havia uma empresa só, `first()` parecia
inofensivo; com cadastro pela interface ele entrega os chamados de quem se cadastrou
primeiro para quem se cadastrou depois.

Chamado de outra empresa devolve **404**, nunca 403: 403 confirmaria que o chamado
existe, e quem está de fora não tem por que saber disso.
"""
from django.db.models import QuerySet
from ninja.errors import HttpError

from .models import Chamado, Convite, EmailRecebido, Empresa, Pessoa, Registro


def pessoa_de(request) -> Pessoa:
    """A pessoa logada, com a empresa já carregada. É a origem de todo escopo."""
    pessoa = Pessoa.objects.select_related("empresa").filter(user=request.user).first()
    if pessoa is None:
        raise HttpError(403, "Seu usuário não está vinculado a nenhuma empresa.")
    return pessoa


def admin_de(request) -> Pessoa:
    """Só para convidar pessoas, editar a lista de setores e mexer na caixa de e-mail.

    Ler chamado e publicar registro não passa por aqui: é de todos, e é parte da tese.
    """
    pessoa = pessoa_de(request)
    if not pessoa.e_admin:
        raise HttpError(403, "Só um administrador da empresa pode fazer isso.")
    return pessoa


def empresa_de(request) -> Empresa:
    return pessoa_de(request).empresa


# ------------------------------------------------------------------ querysets escopados
#
# Cada função abaixo é o **único** ponto de partida permitido para o seu modelo. Se
# uma rota monta `Modelo.objects.filter(...)` na mão, o escopo passa a depender de
# quem escreveu a rota — e é assim que dado de uma empresa vaza para outra.


def chamados_de(pessoa: Pessoa) -> QuerySet[Chamado]:
    return Chamado.objects.filter(empresa=pessoa.empresa)


def registros_de(pessoa: Pessoa) -> QuerySet[Registro]:
    return Registro.objects.filter(chamado__empresa=pessoa.empresa)


def emails_de(pessoa: Pessoa) -> QuerySet[EmailRecebido]:
    return EmailRecebido.objects.filter(empresa=pessoa.empresa)


def membros_de(pessoa: Pessoa) -> QuerySet[Pessoa]:
    return Pessoa.objects.filter(empresa=pessoa.empresa)


def convites_de(pessoa: Pessoa) -> QuerySet[Convite]:
    return Convite.objects.filter(empresa=pessoa.empresa)
