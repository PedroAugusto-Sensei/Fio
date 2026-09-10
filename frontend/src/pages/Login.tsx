import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { ErroApi } from "../api/client";
import { Olho, Onda } from "../components/Icones";
import { useSessao } from "../components/Sessao";

/**
 * Cartão centrado, sem SSO. Quem ainda não tem empresa no Fio cadastra por aqui; quem
 * já tem entra com a **própria** conta — não existe senha compartilhada de empresa.
 */
export function Login() {
  const { eu, carregando, entrar } = useSessao();
  const local = useLocation();
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  const destino = (local.state as { de?: string } | null)?.de ?? "/chamados";

  if (carregando) return <p className="carregando">Carregando…</p>;
  if (eu) return <Navigate to={destino} replace />;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await entrar(usuario, senha);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.message : "Não foi possível entrar. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <div className="login-marca">
        <Onda size={44} />
        <span>Fio</span>
      </div>

      <form className="cartao-login" onSubmit={enviar}>
        <h1>Entrar</h1>
        <p className="sub">Use a conta da sua empresa.</p>

        {erro && (
          <p className="erro" role="alert">
            {erro}
          </p>
        )}

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="usuario">
            Usuário
          </label>
          <input
            id="usuario"
            className="campo"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            placeholder="seu e-mail"
            autoComplete="username"
            autoFocus
            required
          />
        </div>

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="senha">
            Senha
          </label>
          <div className="campo-senha">
            <input
              id="senha"
              className="campo"
              type={mostrarSenha ? "text" : "password"}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete="current-password"
              required
            />
            <button
              type="button"
              className="olho"
              onClick={() => setMostrarSenha((v) => !v)}
              aria-label={mostrarSenha ? "Esconder a senha" : "Mostrar a senha"}
            >
              <Olho aberto={!mostrarSenha} />
            </button>
          </div>
        </div>

        <button type="submit" className="botao botao-primario" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </form>

      <p className="nota-login">
        Sua empresa ainda não usa o Fio?{" "}
        <Link to="/criar-conta">Criar conta da minha empresa</Link>
      </p>

      <p className="nota-login">Todos os funcionários da empresa leem todos os chamados.</p>

      <p className="dica-demo">
        Demonstração: <span className="mono">autor.1</span> … <span className="mono">autor.5</span>{" "}
        com a senha <span className="mono">fio12345</span>.
      </p>
    </div>
  );
}
