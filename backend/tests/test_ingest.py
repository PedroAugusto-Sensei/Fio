"""Entrada de e-mail (seção 7): dedupe, threading e remetente real, sem servidor IMAP.

O ingest **grava**; ele não decide. E-mail que abre conversa nova fica na caixa de
entrada esperando gente. Só resposta dentro de uma conversa que já virou chamado entra
sozinha — sem isso, cada follow-up de cliente pediria um clique.
"""
import pytest

from core.models import Anexo, AnexoRecebido, Chamado, EmailRecebido, Mensagem
from ingest.entrada import ids_de, promover, remetente_real, separar_remetente
from ingest.management.commands.ingest_email import Command

from .conftest import AnexoFalso, MensagemFalsa, eml, monta_mime

pytestmark = pytest.mark.django_db


def ingerir_bruto(empresa, mime, anexos=()):
    """Devolve `(EmailRecebido, criado)`, como o comando devolve."""
    return Command().ingerir(empresa, MensagemFalsa(mime, attachments=anexos))


# --------------------------------------------------------------- a etapa nova


def test_email_que_abre_conversa_nova_fica_na_caixa_e_nao_vira_chamado(empresa):
    """O ingest grava e para aí. Quem decide se isto é um chamado é uma pessoa."""
    recebido, criado = ingerir_bruto(empresa, eml("simples.eml"))

    assert criado is True
    assert recebido.situacao == "pendente"
    assert recebido.chamado_id is None
    assert "Lorem ipsum dolor sit amet" in recebido.texto

    assert Chamado.objects.filter(empresa=empresa).count() == 0
    assert Mensagem.objects.filter(chamado__empresa=empresa).count() == 0


def test_todo_email_lido_e_gravado_mesmo_o_que_nao_e_demanda(empresa):
    """Nada é filtrado por conteúdo: classificar é decisão humana, não heurística."""
    ingerir_bruto(
        empresa,
        monta_mime(assunto="Resposta automática: Ausente até 20/09", corpo="Estou de férias.\n"),
    )
    ingerir_bruto(
        empresa,
        monta_mime(assunto="Boletim semanal", corpo="Para deixar de receber, clique aqui.\n"),
    )

    assert EmailRecebido.objects.filter(empresa=empresa, situacao="pendente").count() == 2
    assert Chamado.objects.filter(empresa=empresa).count() == 0


def test_mesmo_email_duas_vezes_cria_um_recebido_so(empresa):
    """Teste 2 da seção 12: a dedupe agora é o UNIQUE(empresa, message_id)."""
    bruto = eml("simples.eml")

    primeiro, criado = ingerir_bruto(empresa, bruto)
    segundo, repetido = ingerir_bruto(empresa, bruto)

    assert criado is True
    assert repetido is False
    assert segundo.pk == primeiro.pk
    assert EmailRecebido.objects.filter(empresa=empresa).count() == 1


def test_resposta_entra_no_mesmo_chamado_sem_passar_pela_caixa(empresa):
    """Teste 3 da seção 12: `com_citacao.eml` responde a `simples.eml`."""
    primeiro, _ = ingerir_bruto(empresa, eml("simples.eml"))
    chamado = promover(primeiro)

    resposta, criado = ingerir_bruto(empresa, eml("com_citacao.eml"))
    resposta.refresh_from_db()

    assert criado is True
    assert resposta.situacao == "promovido"
    assert resposta.chamado_id == chamado.id
    assert resposta.promovido_por_id is None  # promovido pelo sistema, não por gente
    assert resposta.promovido_em is not None

    assert Chamado.objects.filter(empresa=empresa).count() == 1
    assert list(chamado.mensagens.values_list("ordem", flat=True)) == [0, 1]

    seguinte = chamado.mensagens.get(ordem=1)
    assert "Nemo enim ipsam voluptatem" in seguinte.texto
    assert seguinte.citacao_offset is not None  # a citação foi marcada, não apagada
    assert "> Lorem ipsum dolor sit amet" in seguinte.texto


def test_resposta_a_email_ainda_pendente_tambem_espera_na_caixa(empresa):
    """Ninguém aceitou a conversa ainda: não há chamado onde a resposta pudesse entrar."""
    ingerir_bruto(empresa, eml("simples.eml"))  # fica pendente, sem promover
    resposta, _ = ingerir_bruto(empresa, eml("com_citacao.eml"))

    assert resposta.situacao == "pendente"
    assert Chamado.objects.filter(empresa=empresa).count() == 0
    assert EmailRecebido.objects.filter(empresa=empresa, situacao="pendente").count() == 2


def test_falha_no_meio_da_transacao_nao_grava_nada_pela_metade(empresa, monkeypatch):
    """A mensagem não é marcada como lida e volta na rodada seguinte, inteira."""
    import ingest.management.commands.ingest_email as comando

    def explode(*_a, **_k):
        raise RuntimeError("disco cheio no meio da gravação")

    monkeypatch.setattr(comando, "salvar_anexos_recebidos", explode)

    class CaixaFalsa:
        def __init__(self, mensagens):
            self.mensagens = mensagens
            self.lidas = []

        def mensagens_nao_lidas(self, limite=100):
            return iter(self.mensagens)

        def marcar_lida(self, uid):
            self.lidas.append(uid)

    caixa = CaixaFalsa([MensagemFalsa(eml("simples.eml"), uid="7")])
    resumo = Command().rodada(empresa, caixa, limite=10)

    assert "1 falha" in resumo
    assert caixa.lidas == []  # continua não lida
    assert EmailRecebido.objects.filter(empresa=empresa).count() == 0
    assert Chamado.objects.filter(empresa=empresa).count() == 0


def test_e_mail_lido_com_sucesso_e_marcado_depois_do_commit(empresa):
    class CaixaFalsa:
        def __init__(self, mensagens):
            self.mensagens = mensagens
            self.lidas = []

        def mensagens_nao_lidas(self, limite=100):
            return iter(self.mensagens)

        def marcar_lida(self, uid):
            # No momento em que o servidor é avisado, o e-mail já está no banco.
            assert EmailRecebido.objects.filter(empresa=empresa).exists()
            self.lidas.append(uid)

    caixa = CaixaFalsa([MensagemFalsa(eml("simples.eml"), uid="7")])
    Command().rodada(empresa, caixa, limite=10)

    assert caixa.lidas == ["7"]


# --------------------------------------------------------------- conteúdo


def test_mime_cru_e_gravado_antes_do_parse(empresa):
    """Invariante 5: dá para reprocessar sem pedir nada ao cliente."""
    bruto = eml("simples.eml")
    recebido, _ = ingerir_bruto(empresa, bruto)

    assert bytes(recebido.bruto) == bruto
    assert b"Message-ID" in bytes(recebido.bruto)


def test_anexos_sao_guardados_no_email_e_copiados_na_promocao(empresa):
    anexo = AnexoFalso("lorem-ipsum.xlsx", b"conteudo-de-teste", "application/vnd.ms-excel")
    recebido, _ = ingerir_bruto(empresa, eml("com_anexo.eml"), anexos=[anexo])

    guardado = AnexoRecebido.objects.get()
    assert guardado.nome == "lorem-ipsum.xlsx"
    assert guardado.arquivo.read() == b"conteudo-de-teste"
    assert len(guardado.sha256) == 64

    promover(recebido)

    copiado = Anexo.objects.get()
    assert copiado.nome == "lorem-ipsum.xlsx"
    assert copiado.arquivo.read() == b"conteudo-de-teste"
    assert copiado.sha256 == guardado.sha256
    # O e-mail continua com o dele: nada é movido, tudo é copiado.
    assert AnexoRecebido.objects.count() == 1


def test_anexo_grande_demais_e_recusado_e_o_texto_entra_do_mesmo_jeito(empresa, settings):
    settings.ANEXO_MAX_BYTES = 10
    anexo = AnexoFalso("grande.bin", b"x" * 50)

    recebido, _ = ingerir_bruto(empresa, eml("com_anexo.eml"), anexos=[anexo])

    assert AnexoRecebido.objects.count() == 0
    assert recebido.texto  # o que importa entrou inteiro


# --------------------------------------------------------------- remetente real


def test_cliente_vem_do_remetente_do_primeiro_email(empresa):
    recebido, _ = ingerir_bruto(empresa, eml("simples.eml"))
    assert recebido.remetente_nome == "Contato A"
    assert recebido.remetente_email == "contato@clientea.com"

    chamado = promover(recebido)
    assert chamado.cliente_nome == "Contato A"
    assert chamado.cliente_email == "contato@clientea.com"


def test_encaminhamento_automatico_usa_reply_to_e_nunca_o_envelope(empresa):
    """O From é o servidor da empresa; o cliente está no Reply-To."""
    recebido, _ = ingerir_bruto(empresa, eml("encaminhado_automatico.eml"))

    assert recebido.remetente_email == "contato@clientec.com"
    assert recebido.remetente_nome == "Contato C"
    # O Return-Path (envelope) está no arquivo e não pode ter sido usado.
    assert "mailer-daemon" not in recebido.remetente_email
    assert "suaempresa" not in recebido.remetente_email


def test_encaminhamento_como_anexo_usa_o_from_do_original(empresa):
    recebido, _ = ingerir_bruto(empresa, eml("encaminhado_como_anexo.eml"))

    assert recebido.remetente_email == "contato@cliented.com"
    assert recebido.remetente_nome == "Contato D"


def test_remetente_real_nunca_le_o_envelope(empresa):
    """Return-Path é ignorado mesmo quando é o único cabeçalho com cara de remetente."""
    bruto = eml("encaminhado_automatico.eml")
    cabecalhos = {
        "return-path": ("<mailer-daemon@suaempresa.com.br>",),
        "from": ("Atendimento <atendimento@suaempresa.com.br>",),
        "reply-to": ("Contato C <contato@clientec.com>",),
    }
    assert remetente_real(bruto, cabecalhos, empresa) == ("Contato C", "contato@clientec.com")


def test_from_do_cliente_tem_prioridade_sobre_reply_to(empresa):
    """Sem reencaminhamento, o From já é o cliente e manda."""
    mime = monta_mime(
        assunto="Lorem",
        corpo="Texto.\n",
        de="Contato A <contato@clientea.com>",
        reply_to="Suporte <atendimento@suaempresa.com.br>",
    )
    cabecalhos = {"from": (mime["From"],), "reply-to": (mime["Reply-To"],)}
    assert remetente_real(mime.as_bytes(), cabecalhos, empresa) == (
        "Contato A",
        "contato@clientea.com",
    )


def test_cabecalho_x_original_from_e_respeitado(empresa):
    cabecalhos = {
        "from": ("Atendimento <atendimento@suaempresa.com.br>",),
        "x-original-from": ("Contato B <contato@clienteb.com>",),
    }
    assert remetente_real(b"", cabecalhos, empresa) == ("Contato B", "contato@clienteb.com")


# --------------------------------------------------------------- utilitários


def test_ids_de_referencias():
    assert ids_de("<a@x> <b@y>") == ["<a@x>", "<b@y>"]
    assert ids_de("") == []


def test_separar_remetente():
    assert separar_remetente("Contato A <contato@clientea.com>") == (
        "Contato A",
        "contato@clientea.com",
    )
    assert separar_remetente("contato@clientea.com") == ("contato", "contato@clientea.com")
