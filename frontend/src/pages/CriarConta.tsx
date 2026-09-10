import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";

import { ErroApi } from "../api/client";
import { Olho, Onda } from "../components/Icones";
import { useSessao } from "../components/Sessao";
import { Setores } from "../components/Setores";

/** O mesmo padrão que o back usa quando o cadastro não manda setor nenhum. */
const SETORES_PADRAO = ["Suporte", "Produto", "Desenvolvimento", "QA", "Implantação"];

/**
 * Cadastro da empresa e da conta de quem cadastra, em um passo só.
 *
 * Não existe senha compartilhada de empresa: quem se cadastra vira o admin, e as
 * outras pessoas entram por convite, cada uma com a própria conta. É `Registro.autor`
 * que responde "quem agiu" no feed do chamado — com login compartilhado, o feed
 * viraria ficção.
 *
 * A caixa de e-mail não entra aqui: a empresa existe antes de ter caixa.
 */
export function CriarConta() {
  const { eu, carregando, registrarEmpresa } = useSessao();
  const [empresaNome, setEmpresaNome] = useState("");
  const [setores, setSetores] = useState<string[]>(SETORES_PADRAO);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  if (carregando) return <p className="carregando">Carregando…</p>;
  if (eu) return <Navigate to="/chamados" replace />;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await registrarEmpresa({ empresa_nome: empresaNome, setores, nome, email, senha });
    } catch (e) {
      setErro(
        e instanceof ErroApi ? e.message : "Não foi possível criar a conta. Tente de novo.",
      );
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

      <form className="cartao-login cartao-largo" onSubmit={enviar}>
        <h1>Criar conta da minha empresa</h1>
        <p className="sub">
          Você fica como administrador e convida o resto do time depois. Cada pessoa tem a
          própria conta.
        </p>

        {erro && (
          <p className="erro" role="alert">
            {erro}
          </p>
        )}

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="empresa">
            Nome da empresa
          </label>
          <input
            id="empresa"
            className="campo"
            value={empresaNome}
            onChange={(e) => setEmpresaNome(e.target.value)}
            placeholder="Sua Empresa"
            autoFocus
            required
          />
        </div>

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="setor-novo">
            Setores
          </label>
          <Setores setores={setores} aoMudar={setSetores} />
          <p className="ajuda">
            É a lista que aparece quando alguém publica um registro. Dá para mudar depois.
          </p>
        </div>

        <hr className="risco" />

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="nome">
            Seu nome
          </label>
          <input
            id="nome"
            className="campo"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome e sobrenome"
            autoComplete="name"
            required
          />
        </div>

        <div className="campo-grupo">
          <label className="campo-rotulo" htmlFor="email">
            Seu e-mail
          </label>
          <input
            id="email"
            className="campo"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="voce@suaempresa.com.br"
            autoComplete="email"
            required
          />
          <p className="ajuda">É com ele que você vai entrar.</p>
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
              autoComplete="new-password"
              minLength={8}
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
          <p className="ajuda">Pelo menos 8 caracteres.</p>
        </div>

        <button
          type="submit"
          className="botao botao-primario"
          disabled={enviando || setores.length === 0}
        >
          {enviando ? "Criando…" : "Criar conta"}
        </button>
      </form>

      <p className="nota-login">
        Já tem conta? <Link to="/login">Entrar</Link>
      </p>
    </div>
  );
}
