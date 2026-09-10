import { useState } from "react";
import type { FormEvent } from "react";

import { api, ErroApi } from "../api/client";
import type { RegistroPublicado, Situacao } from "../api/tipos";
import { SITUACOES } from "../lib/situacoes";
import { Modal } from "./Modal";
import { useSessao } from "./Sessao";

/**
 * "Registrar o que fizemos".
 *
 * O trecho do cliente fica fixo acima do campo: você escreve olhando para as
 * palavras dele. A situação é obrigatória — e é a única forma de mudá-la
 * (invariante 4: não existe tela de "atualizar status").
 */
export function ModalRegistro({
  chamadoId,
  codigo,
  trechoCliente,
  registroParaCorrigir,
  onFechar,
  onPublicado,
  onLerEmail,
}: {
  chamadoId: number;
  codigo: string;
  trechoCliente: string;
  registroParaCorrigir?: { id: number; texto: string; situacao: Situacao };
  onFechar: () => void;
  onPublicado: (resultado: RegistroPublicado) => void;
  onLerEmail: () => void;
}) {
  const { eu } = useSessao();
  const corrigindo = registroParaCorrigir !== undefined;

  const [texto, setTexto] = useState(registroParaCorrigir?.texto ?? "");
  const [situacao, setSituacao] = useState<Situacao | null>(
    registroParaCorrigir?.situacao ?? null,
  );
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  async function publicar(evento: FormEvent) {
    evento.preventDefault();
    if (!texto.trim()) {
      setErro("Escreva o que foi feito antes de publicar.");
      return;
    }
    if (!situacao) {
      setErro("Escolha em que situação o chamado fica depois deste registro.");
      return;
    }

    setErro("");
    setEnviando(true);
    try {
      const resultado = corrigindo
        ? await api.corrigirRegistro(registroParaCorrigir.id, texto.trim(), situacao)
        : await api.publicarRegistro(chamadoId, texto.trim(), situacao);
      onPublicado(resultado);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível publicar o registro.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <Modal onFechar={onFechar} rotulo="Registrar o que fizemos" largo>
      <form onSubmit={publicar}>
        <div className="modal-topo">
          <div>
            <h2>{corrigindo ? "Corrigir o registro" : "Registrar o que fizemos"}</h2>
            <p className="modal-sub">
              {eu ? `${eu.nome} · ${eu.setor}` : ""}
              {corrigindo && " · a versão anterior fica guardada"}
            </p>
          </div>
          <span className="mono" style={{ color: "var(--acento)" }}>
            {codigo}
          </span>
        </div>

        <div className="modal-corpo">
          {trechoCliente && (
            <div className="caixa-cliente">
              <span className="rotulo">O que o cliente escreveu</span>
              <p className="caixa-cliente-texto">“{trechoCliente}”</p>
              <button
                type="button"
                className="botao-texto"
                onClick={() => {
                  onFechar();
                  onLerEmail();
                }}
              >
                Ler o e-mail inteiro
              </button>
            </div>
          )}

          {erro && (
            <p className="erro" role="alert">
              {erro}
            </p>
          )}

          <label className="campo-rotulo" htmlFor="o-que-fizemos">
            O que fizemos
          </label>
          <textarea
            id="o-que-fizemos"
            className="campo"
            rows={7}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Escreva com as suas palavras o que o seu setor fez."
          />

          <p className="campo-rotulo" style={{ marginTop: 18, marginBottom: 0 }}>
            Situação do chamado depois deste registro
          </p>
          <div className="escolha-situacao">
            {SITUACOES.map((s) => (
              <button
                key={s.valor}
                type="button"
                className={`chip${situacao === s.valor ? " ativo" : ""}`}
                aria-pressed={situacao === s.valor}
                onClick={() => setSituacao(s.valor)}
              >
                {s.rotulo}
              </button>
            ))}
          </div>
          <p className="ajuda">
            É esta situação que aparece na lista de chamados, com a data do seu registro ao lado.
          </p>
        </div>

        <div className="modal-rodape">
          <p className="modal-rodape-nota">
            Seu registro entra no fim da lista, com a sua data. A descrição continua sendo o e-mail
            do cliente.
          </p>
          <div className="modal-rodape-acoes">
            <button type="button" className="botao" onClick={onFechar}>
              Cancelar
            </button>
            <button type="submit" className="botao botao-primario" disabled={enviando}>
              {enviando ? "Publicando…" : corrigindo ? "Publicar correção" : "Publicar registro"}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  );
}
