import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../api/client";
import type { ConfigImap } from "../api/client";
import { useSessao } from "../components/Sessao";

export function ConfigurarImap() {
  const { eu, atualizar } = useSessao();
  const [dados, setDados] = useState<ConfigImap | null>(null);
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState(false);
  const [salvando, setSalvando] = useState(false);
  useEffect(() => {
    if (!eu?.pode_configurar_imap) return;
    let ativo = true;
    api.imap().then(d => { if (ativo) setDados(d); }).catch(e => { if (ativo) setErro(e.message); });
    return () => { ativo = false; };
  }, [eu?.pode_configurar_imap]);
  if (!eu?.pode_configurar_imap) return <Navigate to="/chamados" replace />;
  async function salvar(event: FormEvent) {
    event.preventDefault();
    if (!dados) return;
    setSalvando(true); setErro(""); setSucesso(false);
    try {
      setDados(await api.salvarImap({ ...dados, senha }));
      setSenha(""); await atualizar(); setSucesso(true);
    } catch (e) { setErro(e instanceof Error ? e.message : "Não foi possível salvar."); }
    finally { setSalvando(false); }
  }
  return <>
    <h1>Configurar IMAP</h1>
    <p className="ajuda">Conecte a caixa de e-mail da empresa. Só quem criou a conta pode alterar esta configuração.</p>
    {erro && <p role="alert">{erro}</p>}
    {sucesso && <p role="status">Configuração salva. Os próximos ciclos de leitura usarão estes dados.</p>}
    {!dados && !erro && <p>Carregando…</p>}
    {dados && <form onSubmit={salvar} className="cartao-convite imap-form">
      <fieldset disabled={salvando}>
        {([
          ["host", "Servidor IMAP", "imap.exemplo.com", "text"],
          ["usuario", "Usuário IMAP", "atendimento@empresa.com", "text"],
          ["caixa_email", "Endereço da caixa", "atendimento@empresa.com", "email"],
          ["pasta", "Pasta observada", "INBOX", "text"],
        ] as const).map(([chave, titulo, exemplo, tipo]) => <label key={chave}>
          {titulo}
          <input className="campo" type={tipo} required maxLength={chave === "host" ? 253 : chave === "pasta" ? 255 : 254}
            placeholder={exemplo} value={dados[chave]} onChange={e => { setDados({ ...dados, [chave]: e.target.value }); setSucesso(false); }} />
        </label>)}
        <label>Senha ou senha de aplicativo
          <input className="campo" type="password" autoComplete="new-password" value={senha}
            required={!dados.senha_configurada} onChange={e => { setSenha(e.target.value); setSucesso(false); }} />
        </label>
        <p className="ajuda">{dados.senha_configurada ? "Deixe a senha em branco para manter a atual. Ao mudar servidor ou usuário, informe a senha novamente. " : ""}Use uma senha de aplicativo se o provedor exigir. Conexão segura por TLS, porta 993.</p>
        <button className="botao" type="submit">{salvando ? "Salvando…" : "Salvar configuração"}</button>
      </fieldset>
    </form>}
  </>;
}
