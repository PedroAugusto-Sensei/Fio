"""Admin do Fio.

`Mensagem` e `Anexo` são somente leitura (invariantes 1 e 6) e não podem ser criados
por aqui: não existe ação de admin que produza mensagem a partir de texto digitado
(invariante 7). A única origem é `manage.py ingest_email`.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Anexo,
    AnexoRecebido,
    Chamado,
    Convite,
    EmailRecebido,
    Empresa,
    Mensagem,
    Pessoa,
    Registro,
)


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nome", "caixa_email", "proximo_numero", "retencao_dias")
    search_fields = ("nome", "caixa_email")


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome", "setor", "papel", "empresa", "user")
    list_filter = ("papel", "setor", "empresa")
    search_fields = ("nome", "user__username")


@admin.register(Convite)
class ConviteAdmin(admin.ModelAdmin):
    """Só para olhar. Convidar e revogar são decisões da tela, não do admin."""

    list_display = ("empresa", "email", "setor", "criado_por", "expira_em", "usado_em")
    list_filter = ("empresa",)
    search_fields = ("email", "token")
    readonly_fields = ("token", "criado_em", "usado_em", "usado_por")


class MensagemInline(admin.TabularInline):
    """Somente leitura: mensagem não se edita, não se apaga e não se acrescenta pelo admin."""

    model = Mensagem
    extra = 0
    can_delete = False
    fields = ("ordem", "remetente", "recebido_em", "sha256", "citacao_offset")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class RegistroInline(admin.TabularInline):
    model = Registro
    extra = 0
    fk_name = "chamado"
    fields = ("criado_em", "setor", "autor", "situacao", "texto", "versao_anterior")
    readonly_fields = ("criado_em",)
    show_change_link = True


@admin.register(Chamado)
class ChamadoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "assunto", "cliente_nome", "situacao_projetada", "criado_em")
    list_filter = ("empresa", "criado_em")
    search_fields = ("codigo", "assunto", "cliente_nome", "cliente_email")
    date_hierarchy = "criado_em"
    inlines = [MensagemInline, RegistroInline]

    @admin.display(description="situação (projetada)")
    def situacao_projetada(self, obj):
        ultimo = obj.registros.filter(versao_seguinte__isnull=True).order_by("-criado_em").first()
        if ultimo is None:
            return format_html('<span style="color:#A34434">sem registro</span>')
        return ultimo.get_situacao_display()


@admin.register(Mensagem)
class MensagemAdmin(admin.ModelAdmin):
    """Invariante 1: nada aqui pode ser alterado."""

    list_display = ("chamado", "ordem", "remetente", "recebido_em", "norm_v")
    list_filter = ("norm_v",)
    search_fields = ("remetente", "message_id", "texto")
    readonly_fields = (
        "chamado",
        "ordem",
        "remetente",
        "destinatario",
        "assunto",
        "recebido_em",
        "texto",
        "norm_v",
        "sha256",
        "citacao_offset",
        "message_id",
    )
    exclude = ("bruto", "search")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Anexo)
class AnexoAdmin(admin.ModelAdmin):
    list_display = ("nome", "mime", "mensagem")
    readonly_fields = ("nome", "mime", "arquivo", "sha256", "mensagem")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Registro)
class RegistroAdmin(admin.ModelAdmin):
    list_display = ("chamado", "setor", "autor", "situacao", "criado_em", "substituido")
    list_filter = ("situacao", "setor")
    search_fields = ("texto", "autor__nome")
    readonly_fields = ("criado_em",)
    exclude = ("search",)

    @admin.display(boolean=True, description="substituído")
    def substituido(self, obj):
        return hasattr(obj, "versao_seguinte") and obj.versao_seguinte is not None


class AnexoRecebidoInline(admin.TabularInline):
    model = AnexoRecebido
    extra = 0
    can_delete = False
    fields = ("nome", "mime", "arquivo", "sha256")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EmailRecebido)
class EmailRecebidoAdmin(admin.ModelAdmin):
    """A caixa de entrada, vista de dentro.

    Conteúdo somente leitura: e-mail recebido não se edita e não se apaga. Promover e
    descartar são decisões da tela, não do admin — aqui só se olha o que chegou.
    """

    list_display = ("recebido_em", "remetente_email", "assunto", "situacao", "chamado")
    list_filter = ("situacao", "empresa", "recebido_em")
    search_fields = ("remetente_email", "remetente_nome", "assunto", "message_id", "texto")
    date_hierarchy = "recebido_em"
    inlines = [AnexoRecebidoInline]
    readonly_fields = (
        "empresa",
        "message_id",
        "recebido_em",
        "lido_em",
        "remetente_nome",
        "remetente_email",
        "destinatario",
        "assunto",
        "refs",
        "texto",
        "norm_v",
        "sha256",
        "citacao_offset",
        "situacao",
        "promovido_em",
        "promovido_por",
        "chamado",
        "descartado_em",
        "descartado_por",
    )
    exclude = ("bruto",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Nada é apagado: descartar carimba `descartado_em` e o registro continua.
        return False
