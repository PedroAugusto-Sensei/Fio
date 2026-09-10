import { useCallback, useEffect, useState } from "react";

import { api, ErroApi } from "../api/client";
import type { ConvitePendente, Membro } from "../api/tipos";
import { Envelope } from "../components/Icones";
import { Avatar } from "../components/PontoSituacao";
import { useSessao } from "../components/Sessao";
import { dataCompleta, tempoRelativo } from "../lib/tempo";

/**
 * Quem está na empresa e quem foi convidado.
 *
 * Convidar é gerar um link e copiar. O Fio **não manda e-mail** — notificação por
 * e-mail está fora de escopo, e a empresa já tem por onde mandar um link.
 */
export function Membros() {
  const { eu } = useSessao();
  const [membros, setMembros] = useState<Membro[]>([]);
  const [convites, setConvites] = useState<ConvitePendente[]>([]);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const [emailConvidado, setEmailConvidado] = useState("");
  const [setorConvidado, setSetorConvidado] = useState("");
  const [setores, setSetores] = useState<string[]>([]);
  const [copiado, setCopiado] = useState("");
  const [gerando, setGerando] = useState(false);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const [pessoas, pendentes, lista] = await Promise.all([
        api.membros(),
        api.convites(),
        api.setores(),
      ]);
      setMembros(pessoas.itens);
      setConvites(pendentes.itens);
      setSetores(lista.setores);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível carregar os membros.");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function copiar(url: string, chave: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(chave);
      window.setTimeout(() => setCopiado(""), 2500);
    } catch {
      // Sem área de transferência (http, permissão negada): o link fica na tela para
      // a pessoa copiar à mão. Nunca some.
      window.prompt("Copie o link do convite:", url);
    }
  }

  async function convidar() {
    setErro("");
    setGerando(true);
    try {
      const convite = await api.criarConvite({
        email: emailConvidado.trim(),
        setor: setorConvidado,
      });
      setEmailConvidado("");
      setSetorConvidado("");
      await copiar(convite.url, String(convite.id));
      await carregar();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível gerar o convite.");
    } finally {
      setGerando(false);
    }
  }

  async function revogar(convite: ConvitePendente) {
    setErro("");
    try {
      await api.revogarConvite(convite.id);
      setConvites((atuais) => atuais.filter((c) => c.id !== convite.id));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível revogar o convite.");
    }
  }

  return (
    <>
      <header className="topo">
        <div>
          <h1>Membros</h1>
          <p className="topo-sub">
            {eu?.empresa} · cada pessoa tem conta própria — é o nome dela que aparece nos
            registros
          </p>
        </div>
      </header>

      {erro && <p className="erro">{erro}</p>}

      <p className={`linha-caixa${eu?.caixa_configurada ? "" : " linha-caixa-alerta"}`}>
        <Envelope />
        {eu?.caixa_configurada ? (
          <>
            <span className="mono">{eu.caixa_email}</span>
            <span className="linha-caixa-pasta">&rsaquo; {eu.pasta_email}</span>
          </>
        ) : (
          <span>
            Caixa de e-mail ainda não configurada — esta empresa não recebe chamados por
            enquanto.
          </span>
        )}
      </p>

      <section className="cartao-convite">
        <h2>Convidar pessoa</h2>
        <p className="ajuda">
          O Fio gera o link e copia para a área de transferência. Entregue pelo canal que
          vocês já usam — o Fio não manda e-mail. O link vale por 7 dias e serve uma vez só.
        </p>

        <div className="linha-convite">
          <input
            className="campo"
            type="email"
            value={emailConvidado}
            onChange={(e) => setEmailConvidado(e.target.value)}
            placeholder="E-mail (opcional)"
            aria-label="E-mail de quem vai ser convidado"
          />
          <select
            className="campo chip-select"
            value={setorConvidado}
            onChange={(e) => setSetorConvidado(e.target.value)}
            aria-label="Setor sugerido"
          >
            <option value="">Setor (opcional)</option>
            {setores.map((setor) => (
              <option key={setor} value={setor}>
                {setor}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="botao botao-primario"
            onClick={() => void convidar()}
            disabled={gerando}
          >
            {gerando ? "Gerando…" : "Convidar pessoa"}
          </button>
        </div>
      </section>

      <h2 className="titulo-secao">Na empresa</h2>
      <div className="tabela-caixa">
        <table className="tabela">
          <thead>
            <tr>
              <th>Pessoa</th>
              <th className="col-situacao">Setor</th>
              <th className="col-situacao">Papel</th>
            </tr>
          </thead>
          <tbody>
            {membros.map((m) => (
              <tr key={m.id}>
                <td>
                  <div className="ultimo-registro">
                    <Avatar iniciais={m.iniciais} title={m.nome} />
                    <div>
                      <div className="ultimo-registro-nome">{m.nome}</div>
                      <div className="ultimo-registro-setor">{m.usuario}</div>
                    </div>
                  </div>
                </td>
                <td className="col-situacao">{m.setor}</td>
                <td className="col-situacao">
                  {m.papel === "admin" ? (
                    <span className="chip-setor">Administrador</span>
                  ) : (
                    <span className="sem-registro">membro</span>
                  )}
                </td>
              </tr>
            ))}

            {!carregando && membros.length === 0 && (
              <tr>
                <td colSpan={3}>
                  <div className="vazio">
                    <strong>Ninguém aqui ainda.</strong>
                    Gere um convite acima e mande o link.
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <h2 className="titulo-secao">Convites esperando</h2>
      <div className="tabela-caixa">
        <table className="tabela">
          <thead>
            <tr>
              <th>Para</th>
              <th className="col-situacao">Setor</th>
              <th className="col-atualizado">Expira</th>
              <th className="col-registro">Link</th>
            </tr>
          </thead>
          <tbody>
            {convites.map((c) => (
              <tr key={c.id}>
                <td>
                  <div className="linha-assunto">{c.email || "qualquer pessoa com o link"}</div>
                  <p className="trecho-cliente">
                    de {c.criado_por} · {tempoRelativo(c.criado_em)}
                  </p>
                </td>
                <td className="col-situacao">{c.setor || "—"}</td>
                <td className="col-atualizado" title={dataCompleta(c.expira_em)}>
                  {dataCompleta(c.expira_em)}
                </td>
                <td className="col-registro">
                  <div className="acoes-convite">
                    <button
                      type="button"
                      className="botao"
                      onClick={() => void copiar(c.url, String(c.id))}
                    >
                      {copiado === String(c.id) ? "Copiado" : "Copiar link"}
                    </button>
                    <button
                      type="button"
                      className="botao-texto"
                      onClick={() => void revogar(c)}
                    >
                      Revogar
                    </button>
                  </div>
                </td>
              </tr>
            ))}

            {!carregando && convites.length === 0 && (
              <tr>
                <td colSpan={4}>
                  <div className="vazio">
                    <strong>Nenhum convite esperando.</strong>
                    Convite usado ou expirado sai desta lista.
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
