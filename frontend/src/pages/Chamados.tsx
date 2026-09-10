import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, ErroApi } from "../api/client";
import type { ListaChamados } from "../api/tipos";
import { Envelope, Lupa } from "../components/Icones";
import { Avatar, PontoSituacao, iniciaisDe } from "../components/PontoSituacao";
import { useSessao } from "../components/Sessao";
import { tempoRelativo } from "../lib/tempo";

const CHIPS = [
  { chave: "abertos", rotulo: "Abertos" },
  { chave: "sem_registro", rotulo: "Sem registro nenhum" },
  { chave: "meus", rotulo: "Onde eu registrei" },
  { chave: "concluidos", rotulo: "Concluídos" },
] as const;

export function Chamados() {
  const { eu } = useSessao();
  const [params, setParams] = useSearchParams();
  const [dados, setDados] = useState<ListaChamados | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const filtro = params.get("filtro") ?? "";
  const cliente = params.get("cliente") ?? "";
  const busca = params.get("busca") ?? "";
  const pagina = Number(params.get("page") ?? 1);

  const [textoBusca, setTextoBusca] = useState(busca);
  useEffect(() => setTextoBusca(busca), [busca]);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      setDados(
        await api.chamados({
          busca,
          situacao: filtro === "meus" ? "" : filtro,
          meus: filtro === "meus",
          cliente,
          page: pagina,
        }),
      );
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar os chamados.");
    } finally {
      setCarregando(false);
    }
  }, [busca, filtro, cliente, pagina]);

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
  }

  // Busca com respiro: não dispara uma requisição por tecla.
  const temporizador = useRef<number | undefined>(undefined);
  function digitarBusca(valor: string) {
    setTextoBusca(valor);
    window.clearTimeout(temporizador.current);
    temporizador.current = window.setTimeout(() => mudarParams({ busca: valor }), 300);
  }

  const clientes = useMemo(() => {
    const nomes = new Set((dados?.itens ?? []).map((c) => c.cliente_nome).filter(Boolean));
    if (cliente) nomes.add(cliente);
    return [...nomes].sort((a, b) => a.localeCompare(b, "pt-BR"));
  }, [dados, cliente]);

  // A caixa que o Fio lê — não é endereço de encaminhamento: ninguém encaminha nada.
  const caixa = dados?.caixa_email ?? eu?.caixa_email ?? "";
  const pasta = dados?.pasta_email ?? eu?.pasta_email ?? "";

  return (
    <>
      <header className="topo">
        <div>
          <h1>Chamados</h1>
          <p className="topo-sub">
            {dados ? `${dados.abertos} aberto${dados.abertos === 1 ? "" : "s"}` : "…"} · o que o
            cliente escreveu, do jeito que escreveu
          </p>
        </div>

        <div className="topo-acoes">
          <span className="intake" title="A caixa de e-mail que o Fio lê">
            <Envelope />
            {caixa}
            {pasta && <span className="intake-pasta">&rsaquo; {pasta}</span>}
          </span>

          <div className="busca">
            <Lupa />
            <input
              className="campo"
              value={textoBusca}
              onChange={(e) => digitarBusca(e.target.value)}
              placeholder="Buscar no texto do cliente"
              aria-label="Buscar no texto do cliente"
              type="search"
            />
          </div>

        </div>
      </header>

      <div className="chips">
        {CHIPS.map((chip) => (
          <button
            key={chip.chave}
            type="button"
            className={`chip${filtro === chip.chave ? " ativo" : ""}`}
            onClick={() =>
              mudarParams({ filtro: filtro === chip.chave ? "" : chip.chave, cliente: "" })
            }
          >
            {chip.rotulo}
          </button>
        ))}

        <select
          className={`chip chip-select${cliente ? " ativo" : ""}`}
          value={cliente}
          onChange={(e) => mudarParams({ cliente: e.target.value })}
          aria-label="Filtrar por cliente"
        >
          <option value="">Por cliente</option>
          {clientes.map((nome) => (
            <option key={nome} value={nome}>
              {nome}
            </option>
          ))}
        </select>
      </div>

      {erro && <p className="erro">{erro}</p>}

      <div className="tabela-caixa">
        <table className="tabela">
          <thead>
            <tr>
              <th className="col-codigo">Chamado</th>
              <th>Assunto e palavras do cliente</th>
              <th className="col-situacao">Situação</th>
              <th className="col-registro">Último registro</th>
              <th className="col-atualizado">Atualizado</th>
            </tr>
          </thead>
          <tbody>
            {dados?.itens.map((c) => (
              <tr key={c.id}>
                <td className="col-codigo">
                  <Link className="mono" to={`/chamados/${c.id}`}>
                    {c.codigo}
                  </Link>
                </td>

                <td>
                  <div className="linha-assunto">
                    <Link to={`/chamados/${c.id}`}>{c.assunto}</Link>
                    {c.cliente_nome && <span className="linha-cliente">{c.cliente_nome}</span>}
                  </div>
                  {/* O trecho do cliente vive na própria linha da tabela. */}
                  {c.trecho_cliente && <p className="trecho-cliente">“{c.trecho_cliente}”</p>}

                  {/* Só no celular, onde as colunas da direita somem. */}
                  <div className="resumo-movel">
                    <PontoSituacao situacao={c.situacao} />
                    <span className="resumo-movel-tempo">
                      {c.ultimo_autor ? `${c.ultimo_autor} · ` : ""}
                      {tempoRelativo(c.ultima_atualizacao ?? c.criado_em)}
                    </span>
                  </div>
                </td>

                <td className="col-situacao">
                  <PontoSituacao situacao={c.situacao} />
                </td>

                <td className="col-registro">
                  {c.ultimo_autor ? (
                    <div className="ultimo-registro">
                      <Avatar iniciais={iniciaisDe(c.ultimo_autor)} title={c.ultimo_autor} />
                      <div>
                        <div className="ultimo-registro-nome">{c.ultimo_autor}</div>
                        <div className="ultimo-registro-setor">{c.ultimo_setor}</div>
                      </div>
                    </div>
                  ) : (
                    <span className="sem-registro">ninguém registrou ainda</span>
                  )}
                </td>

                <td className="col-atualizado">
                  {tempoRelativo(c.ultima_atualizacao ?? c.criado_em)}
                </td>
              </tr>
            ))}

            {!carregando && dados?.itens.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <div className="vazio">
                    <strong>Nenhum chamado por aqui.</strong>
                    {busca || filtro || cliente
                      ? "Tente outro filtro ou outra palavra."
                      : `Nada chegou em ${caixa}${pasta ? ` › ${pasta}` : ""} até agora. ` +
                        "Assim que um cliente escrever, o chamado aparece aqui sozinho."}
                  </div>
                </td>
              </tr>
            )}

            {carregando && !dados && (
              <tr>
                <td colSpan={5}>
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
            Página {dados.pagina} de {dados.paginas} · {dados.total} chamados
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
