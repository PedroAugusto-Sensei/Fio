import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { api, ErroApi } from "../api/client";
import type { ConvitePublico } from "../api/tipos";
import { Olho, Onda } from "../components/Icones";
import { useSessao } from "../components/Sessao";

/**
 * Quem foi convidado cria a **própria** conta aqui.
 *
 * A tela sabe o nome da empresa e os setores, e nada mais: um link vazado não pode
 * virar janela para dentro da empresa. Token usado, expirado ou revogado não abre.
 */
export function Convite() {
  const { token = "" } = useParams();
  const { eu, aceitarConvite } = useSessao();

  const [convite, setConvite] = useState<ConvitePublico | null>(null);
  const [erroDoLink, setErroDoLink] = useState("");
  const [carregando, setCarregando] = useState(true);

  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [setor, setSetor] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    let ativo = true;
    (async () => {
      try {
        const dados = await api.convite(token);
        if (!ativo) return;
        setConvite(dados);
        setEmail(dados.email);
        setSetor(dados.setor || dados.setores[0] || "");
      } catch (e) {
        if (ativo) {
          setErroDoLink(
            e instanceof ErroApi ? e.message : "Não foi possível abrir este convite.",
          );
        }
      } finally {
        if (ativo) setCarregando(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, [token]);

  if (eu) return <Navigate to="/chamados" replace />;
  if (carregando) return <p className="carregando">Carregando…</p>;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await aceitarConvite(token, { nome, email, senha, setor });
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

      {!convite ? (
        <div className="cartao-login">
          <div className="vazio">
            <strong>Este convite não vale mais.</strong>
            {erroDoLink || "O link pode ter sido usado, revogado ou ter expirado."}
            <p className="nota-login">
              Peça um link novo a quem administra a empresa, ou <Link to="/login">entre</Link> com
              a conta que você já tem.
            </p>
          </div>
        </div>
      ) : (
        <form className="cartao-login" onSubmit={enviar}>
          <h1>Você foi convidado para {convite.empresa_nome}</h1>
          <p className="sub">
            A conta é sua: é o seu nome que vai aparecer nos registros que você publicar.
          </p>

          {erro && (
            <p className="erro" role="alert">
              {erro}
            </p>
          )}

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
              autoFocus
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
            <label className="campo-rotulo" htmlFor="setor">
              Seu setor
            </label>
            <select
              id="setor"
              className="campo chip-select"
              value={setor}
              onChange={(e) => setSetor(e.target.value)}
              required
            >
              {convite.setores.map((nomeSetor) => (
                <option key={nomeSetor} value={nomeSetor}>
                  {nomeSetor}
                </option>
              ))}
            </select>
            <p className="ajuda">Fica junto de cada registro que você publicar.</p>
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

          <button type="submit" className="botao botao-primario" disabled={enviando}>
            {enviando ? "Criando…" : "Criar minha conta"}
          </button>
        </form>
      )}
    </div>
  );
}
