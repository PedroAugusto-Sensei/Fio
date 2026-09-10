import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ErroApi } from "../api/client";
import type { Chamado as ChamadoDados, Mensagem, Registro, Situacao } from "../api/tipos";
import { Cadeado, Papel } from "../components/Icones";
import { ModalRegistro } from "../components/ModalRegistro";
import { Avatar, PontoSituacao } from "../components/PontoSituacao";
import { TextoDoCliente } from "../components/TextoDoCliente";
import { useSessao } from "../components/Sessao";
import {
  dataCompleta,
  dataCurta,
  dataHora,
  dataHoraCurta,
  relativoComData,
} from "../lib/tempo";

/** Uma entrada do feed: um registro nosso, ou o aviso de que o cliente escreveu. */
type ItemFeed =
  | { tipo: "registro"; quando: string; registro: Registro }
  | { tipo: "mensagem"; quando: string; mensagem: Mensagem };

export function Chamado() {
  const { id } = useParams();
  const chamadoId = Number(id);
  const { eu } = useSessao();

  const [dados, setDados] = useState<ChamadoDados | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [modalAberto, setModalAberto] = useState(false);
  const [corrigindo, setCorrigindo] = useState<Registro | null>(null);
  const [copiado, setCopiado] = useState(false);

  const descricaoRef = useRef<HTMLDivElement>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      setDados(await api.chamado(chamadoId));
    } catch (e) {
      setErro(
        e instanceof ErroApi
          ? e.message
          : "Não foi possível carregar este chamado.",
      );
    } finally {
      setCarregando(false);
    }
  }, [chamadoId]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // O feed mistura registros e chegadas de e-mail, tudo em ordem de data.
  const feed = useMemo<ItemFeed[]>(() => {
    if (!dados) return [];
    const itens: ItemFeed[] = [
      ...dados.registros.map((r) => ({
        tipo: "registro" as const,
        quando: r.criado_em,
        registro: r,
      })),
      ...dados.mensagens_seguintes.map((m) => ({
        tipo: "mensagem" as const,
        quando: m.recebido_em,
        mensagem: m,
      })),
    ];
    return itens.sort((a, b) => a.quando.localeCompare(b.quando));
  }, [dados]);

  const trechoCliente = useMemo(() => {
    const texto = dados?.descricao?.texto ?? "";
    const proprio =
      dados?.descricao?.citacao_offset != null
        ? texto.slice(0, dados.descricao.citacao_offset)
        : texto;
    const limpo = proprio.replace(/\s+/g, " ").trim();
    return limpo.length > 240 ? `${limpo.slice(0, 240).trimEnd()}…` : limpo;
  }, [dados]);

  function irParaDescricao() {
    descricaoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function copiarLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
    } catch {
      // Navegador sem permissão de área de transferência: o link continua na barra.
    }
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 2000);
  }

  if (carregando && !dados) return <p className="carregando">Carregando o chamado…</p>;
  if (erro) {
    return (
      <div className="aviso">
        <p>{erro}</p>
        <Link to="/chamados">Voltar para a lista</Link>
      </div>
    );
  }
  if (!dados) return null;

  const descricao = dados.descricao;
  const ultimo = dados.registros[dados.registros.length - 1];

  return (
    <>
      <nav className="migalha">
        <Link to="/chamados">Chamados</Link>
        <span>/</span>
        <span className="mono">{dados.codigo}</span>
      </nav>

      <header className="cabecalho-chamado">
        <div>
          <h1>{dados.assunto}</h1>
          <div className="meta-chamado">
            {dados.cliente_nome && <span>{dados.cliente_nome}</span>}
            {dados.cliente_email && <span>{dados.cliente_email}</span>}
            <span>e-mail recebido em {dataCurta(dados.criado_em)}</span>
            <span>aberto para toda a empresa</span>
          </div>
        </div>

        <div className="topo-acoes">
          <button type="button" className="botao" onClick={() => void copiarLink()}>
            {copiado ? "Link copiado" : "Copiar link do chamado"}
          </button>
          <button
            type="button"
            className="botao botao-primario"
            onClick={() => {
              setCorrigindo(null);
              setModalAberto(true);
            }}
          >
            Registrar o que fizemos
          </button>
        </div>
      </header>

      {/* Bloco da descrição: superfície verde-clara, distinta do resto da página.
          Esta separação visual é o produto. */}
      <section className="bloco-cliente" ref={descricaoRef}>
        <div className="descricao">
          <div className="descricao-rotulo">
            <Cadeado />
            Descrição do chamado · palavras do cliente · não editável
          </div>

          {descricao ? (
            <>
              <div className="cabecalho-email">
                <div>De: {descricao.remetente || dados.cliente_email || "—"}</div>
                {descricao.destinatario && <div>Para: {descricao.destinatario}</div>}
                <div>Assunto: {descricao.assunto || dados.assunto}</div>
                <div>Recebido: {dataHora(descricao.recebido_em)}</div>
              </div>

              <TextoDoCliente
                className="corpo-email"
                texto={descricao.texto}
                citacaoOffset={descricao.citacao_offset}
              />

              {descricao.anexos.length > 0 && (
                <div className="anexos">
                  {descricao.anexos.map((a) => (
                    <a
                      key={a.id}
                      className="chip-anexo"
                      href={a.url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Papel />
                      {a.nome}
                    </a>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="ajuda">Este chamado ainda não tem a mensagem do cliente.</p>
          )}
        </div>

        <div className="mensagens-seguintes">
          <span className="rotulo">O cliente escreveu de novo</span>

          {dados.mensagens_seguintes.length === 0 ? (
            <p className="nota-cliente" style={{ marginTop: 14 }}>
              Nenhuma resposta nova até agora. Quando o cliente responder, o texto entra aqui
              inteiro.
            </p>
          ) : (
            dados.mensagens_seguintes.map((m) => (
              <article className="mensagem-seguinte" key={m.id}>
                <div className="mensagem-seguinte-data">
                  {dataHoraCurta(m.recebido_em)} · resposta na mesma conversa
                </div>
                <TextoDoCliente
                  className="mensagem-seguinte-texto"
                  texto={m.texto}
                  citacaoOffset={m.citacao_offset}
                />
              </article>
            ))
          )}

          <p className="nota-cliente">
            Cada resposta do cliente entra aqui inteira. Nada substitui o texto ao lado.
          </p>
        </div>
      </section>

      <div className="grade-chamado">
        <section className="painel">
          <div className="painel-topo">
            <span className="rotulo">O que foi feito, em ordem</span>
            <div className="situacao-atual">
              <span className="rotulo">Situação</span>
              <PontoSituacao situacao={dados.situacao} />
              {ultimo && <span className="setor-atual">· {ultimo.setor}</span>}
            </div>
          </div>

          <div className="feed">
            {feed.length === 0 ? (
              <div className="feed-vazio">
                <strong>Ninguém registrou nada ainda.</strong>
                <p style={{ margin: "6px 0 0", color: "var(--texto-3)" }}>
                  O chamado está aqui, com as palavras do cliente. Falta contar o que o seu setor
                  fez.
                </p>
              </div>
            ) : (
              feed.map((item) =>
                item.tipo === "registro" ? (
                  <div className="feed-linha" key={`r${item.registro.id}`}>
                    <div className="feed-data">{dataCurta(item.quando)}</div>
                    <div className="feed-fio">
                      <span className="feed-ponto" />
                    </div>
                    <div className="feed-conteudo">
                      <div className="feed-cabecalho">
                        <span className="chip-setor">{item.registro.setor}</span>
                        <span className="feed-autor">{item.registro.autor.nome}</span>
                        <PontoSituacao situacao={item.registro.situacao} />
                        {eu && item.registro.autor.nome === eu.nome && (
                          <button
                            type="button"
                            className="botao-texto"
                            onClick={() => {
                              setCorrigindo(item.registro);
                              setModalAberto(true);
                            }}
                          >
                            corrigir
                          </button>
                        )}
                      </div>
                      <p className="feed-texto">{item.registro.texto}</p>
                      {item.registro.editado_em && (
                        <p className="feed-editado">
                          Corrigido em {dataCompleta(item.registro.editado_em)} · a versão anterior
                          continua guardada.
                        </p>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="feed-linha" key={`m${item.mensagem.id}`}>
                    <div className="feed-data">{dataCurta(item.quando)}</div>
                    <div className="feed-fio">
                      <span className="feed-ponto vazio" />
                    </div>
                    <div className="feed-marcador">
                      O cliente respondeu no e-mail — o texto entrou na descrição, acima.
                    </div>
                  </div>
                ),
              )
            )}
          </div>
        </section>

        <aside className="ficha">
          <div className="cartao">
            <span className="rotulo">Ficha</span>
            <dl>
              <div className="ficha-linha">
                <dt>Cliente</dt>
                <dd>{dados.cliente_nome || "—"}</dd>
              </div>
              <div className="ficha-linha">
                <dt>Contato</dt>
                <dd>{dados.cliente_email || "—"}</dd>
              </div>
              <div className="ficha-linha">
                {/* Constante, não campo: e-mail é a única origem que existe. */}
                <dt>Canal de entrada</dt>
                <dd>E-mail</dd>
              </div>
              <div className="ficha-linha">
                <dt>Aberto em</dt>
                <dd>{dataCompleta(dados.criado_em)}</dd>
              </div>
              <div className="ficha-linha">
                <dt>Último registro</dt>
                <dd>
                  {dados.ultima_atualizacao ? (
                    relativoComData(dados.ultima_atualizacao)
                  ) : (
                    <span className="sem-registro">sem registro</span>
                  )}
                </dd>
              </div>
              <div className="ficha-linha">
                <dt>Visibilidade</dt>
                <dd>Toda a empresa</dd>
              </div>
            </dl>
          </div>

          <div className="cartao">
            <span className="rotulo">Quem já registrou</span>
            {dados.quem_registrou.length === 0 ? (
              <p style={{ margin: 0 }}>Ninguém ainda.</p>
            ) : (
              dados.quem_registrou.map((p) => (
                <div className="pessoa-linha" key={p.id}>
                  <Avatar iniciais={p.iniciais} title={p.nome} />
                  <span>{p.nome}</span>
                  <span className="setor">{p.setor}</span>
                </div>
              ))
            )}
          </div>

          <div className="cartao">
            <span className="rotulo">Conversa com o cliente</span>
            <p>
              {dados.total_mensagens}{" "}
              {dados.total_mensagens === 1 ? "mensagem recebida" : "mensagens recebidas"} por
              e-mail, todas guardadas inteiras no chamado.
            </p>
            <button type="button" className="botao" onClick={irParaDescricao}>
              Ver a conversa completa
            </button>
          </div>
        </aside>
      </div>

      {modalAberto && (
        <ModalRegistro
          chamadoId={dados.id}
          codigo={dados.codigo}
          trechoCliente={trechoCliente}
          registroParaCorrigir={
            corrigindo
              ? {
                  id: corrigindo.id,
                  texto: corrigindo.texto,
                  situacao: corrigindo.situacao as Situacao,
                }
              : undefined
          }
          onFechar={() => {
            setModalAberto(false);
            setCorrigindo(null);
          }}
          onLerEmail={irParaDescricao}
          onPublicado={() => {
            setModalAberto(false);
            setCorrigindo(null);
            // Recarrega o chamado: o feed e a situação atualizam sem recarregar a página.
            void carregar();
          }}
        />
      )}
    </>
  );
}
