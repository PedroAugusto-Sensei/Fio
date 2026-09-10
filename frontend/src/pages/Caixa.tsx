import { Fragment, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, ErroApi } from "../api/client";
import type { EmailCompleto, ListaEmails } from "../api/tipos";
import { Envelope, Papel } from "../components/Icones";
import { usePendentes } from "../components/Pendentes";
import { useSessao } from "../components/Sessao";
import { TextoDoCliente } from "../components/TextoDoCliente";
import { dataHoraCurta, tempoRelativo } from "../lib/tempo";

/**
 * A caixa de entrada do Fio: o que chegou por e-mail, antes de alguém decidir se é
 * um chamado. A decisão é humana e explícita — não há classificação automática, nota
 * de relevância nem palpite por assunto.
 *
 * Ninguém digita nada aqui. As duas ações são escolher **qual** e-mail vira chamado;
 * o que está escrito nele nunca passa por um teclado nosso.
 */

const CHIPS = [
  { chave: "pendente", rotulo: "Esperando decisão" },
  { chave: "promovido", rotulo: "Viraram chamado" },
  { chave: "descartado", rotulo: "Descartados" },
  { chave: "todos", rotulo: "Tudo que chegou" },
] as const;

export function Caixa() {
  const { eu } = useSessao();
  const { recarregar: recarregarContador } = usePendentes();
  const navegar = useNavigate();
  const [params, setParams] = useSearchParams();

  const filtro = params.get("filtro") ?? "pendente";
  const pagina = Number(params.get("page") ?? 1);

  const [dados, setDados] = useState<ListaEmails | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const [aberto, setAberto] = useState<number | null>(null);
  const [detalhe, setDetalhe] = useState<EmailCompleto | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [agindo, setAgindo] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      setDados(await api.emails({ situacao: filtro, page: pagina }));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível abrir a caixa de entrada.");
    } finally {
      setCarregando(false);
    }
  }, [filtro, pagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function mudarParams(mudancas: Record<string, string>) {
    const novos = new URLSearchParams(params);
    for (const [chave, valor] of Object.entries(mudancas)) {
      if (valor) novos.set(chave, valor);
      else novos.delete(chave);
    }
    if (!("page" in mudancas)) novos.delete("page");
    setParams(novos, { replace: true });
    setAberto(null);
    setDetalhe(null);
  }

  async function abrir(id: number) {
    if (aberto === id) {
      setAberto(null);
      setDetalhe(null);
      return;
    }
    setAberto(id);
    setDetalhe(null);
    setCarregandoDetalhe(true);
    setErro("");
    try {
      setDetalhe(await api.email(id));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível abrir este e-mail.");
    } finally {
      setCarregandoDetalhe(false);
    }
  }

  async function criarChamado(id: number) {
    setAgindo(true);
    setErro("");
    try {
      const { chamado_id } = await api.promoverEmail(id);
      void recarregarContador();
      // Depois de promover, o chamado é o lugar onde a pessoa quer estar.
      navegar(`/chamados/${chamado_id}`);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível criar o chamado.");
      void carregar();
    } finally {
      setAgindo(false);
    }
  }

  async function descartar(id: number) {
    setAgindo(true);
    setErro("");
    try {
      await api.descartarEmail(id);
      setAberto(null);
      setDetalhe(null);
      void recarregarContador();
      await carregar();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível descartar este e-mail.");
    } finally {
      setAgindo(false);
    }
  }

  const caixa = dados?.caixa_email ?? eu?.caixa_email ?? "";
  const pasta = dados?.pasta_email ?? eu?.pasta_email ?? "";
  const pendentes = dados?.pendentes ?? 0;

  return (
    <>
      <header className="topo">
        <div>
          <h1>Caixa de entrada</h1>
          <p className="topo-sub">
            {dados
              ? `${pendentes} ${pendentes === 1 ? "e-mail espera" : "e-mails esperam"} decisão`
              : "…"}{" "}
            · nada vira chamado sozinho, exceto resposta numa conversa que já é chamado
          </p>
        </div>

        <div className="topo-acoes">
          <span className="intake" title="A caixa de e-mail que o Fio lê">
            <Envelope />
            {caixa}
            {pasta && <span className="intake-pasta">&rsaquo; {pasta}</span>}
          </span>
        </div>
      </header>

      <div className="chips">
        {CHIPS.map((chip) => (
          <button
            key={chip.chave}
            type="button"
            className={`chip${filtro === chip.chave ? " ativo" : ""}`}
            onClick={() => mudarParams({ filtro: chip.chave })}
          >
            {chip.rotulo}
            {chip.chave === "pendente" && pendentes > 0 && (
              <span className="chip-contador">{pendentes}</span>
            )}
          </button>
        ))}
      </div>

      {erro && <p className="erro">{erro}</p>}

      <div className="tabela-caixa">
        <table className="tabela">
          <thead>
            <tr>
              <th className="col-remetente">Quem escreveu</th>
              <th>Assunto e palavras do cliente</th>
              <th className="col-email-situacao">Situação</th>
              <th className="col-atualizado">Recebido</th>
            </tr>
          </thead>
          <tbody>
            {dados?.itens.map((e) => (
              <Fragment key={e.id}>
                <tr
                  className={`linha-email${aberto === e.id ? " aberta" : ""}`}
                  onClick={() => void abrir(e.id)}
                >
                  <td className="col-remetente">
                    <div className="remetente-nome">{e.remetente_nome || e.remetente_email}</div>
                    <div className="remetente-email">{e.remetente_email}</div>
                  </td>

                  <td>
                    <div className="linha-assunto">
                      <strong>{e.assunto || "(sem assunto)"}</strong>
                      {e.total_anexos > 0 && (
                        <span className="linha-cliente">
                          {e.total_anexos} {e.total_anexos === 1 ? "anexo" : "anexos"}
                        </span>
                      )}
                    </div>
                    {e.trecho && <p className="trecho-cliente">“{e.trecho}”</p>}

                    {/* Só no celular, onde a coluna de quem escreveu some. */}
                    <div className="resumo-movel">
                      <SituacaoEmail email={e} />
                      <span className="resumo-movel-tempo">
                        {e.remetente_nome || e.remetente_email} · {tempoRelativo(e.recebido_em)}
                      </span>
                    </div>
                  </td>

                  <td className="col-email-situacao">
                    <SituacaoEmail email={e} />
                  </td>

                  <td className="col-atualizado" title={dataHoraCurta(e.recebido_em)}>
                    {tempoRelativo(e.recebido_em)}
                  </td>
                </tr>

                {aberto === e.id && (
                  <tr className="linha-email-aberta">
                    <td colSpan={4}>
                      {carregandoDetalhe && <p className="ajuda">Abrindo o e-mail…</p>}

                      {detalhe && detalhe.id === e.id && (
                        <div className="email-aberto">
                          <div className="cabecalho-email">
                            <div>
                              De: {detalhe.remetente_nome} &lt;{detalhe.remetente_email}&gt;
                            </div>
                            {detalhe.destinatario && <div>Para: {detalhe.destinatario}</div>}
                            <div>Assunto: {detalhe.assunto || "(sem assunto)"}</div>
                            <div>Recebido: {dataHoraCurta(detalhe.recebido_em)}</div>
                          </div>

                          {/* Texto inteiro. A citação sai em cor secundária, nunca apagada. */}
                          <TextoDoCliente
                            className="corpo-email"
                            texto={detalhe.texto}
                            citacaoOffset={detalhe.citacao_offset}
                          />

                          {detalhe.anexos.length > 0 && (
                            <div className="anexos">
                              {detalhe.anexos.map((a) => (
                                <a
                                  key={a.id}
                                  className="chip-anexo"
                                  href={a.url}
                                  target="_blank"
                                  rel="noreferrer"
                                  onClick={(evento) => evento.stopPropagation()}
                                >
                                  <Papel />
                                  {a.nome}
                                </a>
                              ))}
                            </div>
                          )}

                          <div className="email-acoes">
                            {detalhe.situacao === "pendente" ? (
                              <>
                                <p className="email-acoes-nota">
                                  O texto acima entra no chamado exatamente como está. Ninguém
                                  reescreve, resume nem corrige.
                                </p>
                                <div className="email-acoes-botoes">
                                  <button
                                    type="button"
                                    className="botao"
                                    disabled={agindo}
                                    onClick={() => void descartar(detalhe.id)}
                                  >
                                    Descartar
                                  </button>
                                  <button
                                    type="button"
                                    className="botao botao-primario"
                                    disabled={agindo}
                                    onClick={() => void criarChamado(detalhe.id)}
                                  >
                                    {agindo ? "Criando…" : "Criar chamado"}
                                  </button>
                                </div>
                              </>
                            ) : (
                              <p className="email-acoes-nota">
                                <DestinoDoEmail email={detalhe} />
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}

            {!carregando && dados?.itens.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <div className="vazio">
                    <strong>
                      {filtro === "pendente"
                        ? "Nenhum e-mail esperando decisão."
                        : "Nada por aqui com este filtro."}
                    </strong>
                    {filtro === "pendente"
                      ? `O Fio lê ${caixa}${pasta ? ` › ${pasta}` : ""} a cada minuto. ` +
                        "Quando um cliente escrever, o e-mail aparece aqui."
                      : "Nada some da caixa para sempre — troque o filtro para ver o resto."}
                  </div>
                </td>
              </tr>
            )}

            {carregando && !dados && (
              <tr>
                <td colSpan={4}>
                  <div className="vazio">Carregando…</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {dados && dados.paginas > 1 && (
        <div className="paginacao">
          <button
            type="button"
            className="botao"
            disabled={dados.pagina <= 1}
            onClick={() => mudarParams({ page: String(dados.pagina - 1) })}
          >
            Anterior
          </button>
          <span>
            Página {dados.pagina} de {dados.paginas} · {dados.total} e-mails
          </span>
          <button
            type="button"
            className="botao"
            disabled={dados.pagina >= dados.paginas}
            onClick={() => mudarParams({ page: String(dados.pagina + 1) })}
          >
            Próxima
          </button>
        </div>
      )}
    </>
  );
}

function SituacaoEmail({ email }: { email: { situacao: string; chamado_codigo: string | null } }) {
  if (email.situacao === "promovido") {
    return (
      <span className="situacao situacao-ok">
        <span className="ponto" />
        {email.chamado_codigo ?? "virou chamado"}
      </span>
    );
  }
  if (email.situacao === "descartado") {
    return (
      <span className="situacao">
        <span className="ponto" />
        descartado
      </span>
    );
  }
  return (
    <span className="situacao situacao-atencao">
      <span className="ponto" />
      esperando decisão
    </span>
  );
}

/** O que aconteceu com um e-mail que já saiu da fila — e quem decidiu. */
function DestinoDoEmail({ email }: { email: EmailCompleto }) {
  if (email.situacao === "descartado") {
    return (
      <>
        Descartado {email.descartado_por ? `por ${email.descartado_por} ` : ""}
        em {dataHoraCurta(email.descartado_em)}. O e-mail continua guardado inteiro.
      </>
    );
  }
  return (
    <>
      {email.promovido_por
        ? `${email.promovido_por} criou o chamado`
        : "Entrou sozinho, por ser resposta numa conversa que já é chamado"}{" "}
      em {dataHoraCurta(email.promovido_em)}.{" "}
      {email.chamado_id && <Link to={`/chamados/${email.chamado_id}`}>Abrir {email.chamado_codigo}</Link>}
    </>
  );
}
