import { NavLink, Outlet } from "react-router-dom";

import { Onda } from "./Icones";
import { usePendentes } from "./Pendentes";
import { Avatar } from "./PontoSituacao";
import { useSessao } from "./Sessao";

/**
 * Casca da aplicação. A navegação lista só o que existe: a caixa de entrada, a lista
 * de chamados e a tela do chamado.
 *
 * O contador de pendentes fica visível de propósito: é o que faz alguém lembrar de
 * olhar a caixa. Sem ele, e-mail de cliente ficaria esperando sem que ninguém soubesse.
 */
export function Layout() {
  const { eu, sair } = useSessao();
  const { pendentes } = usePendentes();

  return (
    <div className="app">
      <aside className="lateral">
        <div className="marca">
          <Onda size={30} />
          <span>Fio</span>
        </div>

        <nav>
          <NavLink
            to="/emails"
            className={({ isActive }) => `nav-item${isActive ? " ativo" : ""}`}
          >
            Caixa de entrada
            {pendentes > 0 && (
              <span className="nav-contador" title={`${pendentes} esperando decisão`}>
                {pendentes}
              </span>
            )}
          </NavLink>
          <NavLink
            to="/chamados"
            className={({ isActive }) => `nav-item${isActive ? " ativo" : ""}`}
          >
            Chamados
          </NavLink>
          {/* Só o admin convida gente e edita a lista de setores. Quem recusa de
              verdade é o back; aqui é só não oferecer o que não vai funcionar. */}
          {eu?.papel === "admin" && (
            <NavLink
              to="/configuracoes/membros"
              className={({ isActive }) => `nav-item${isActive ? " ativo" : ""}`}
            >
              Membros
            </NavLink>
          )}
        </nav>

        <div className="lateral-rodape">
          <div className="cartao-acesso">
            <span className="rotulo">Acesso</span>
            Todos os funcionários leem todos os chamados.
          </div>

          {eu && (
            <div className="eu">
              <Avatar iniciais={eu.iniciais} title={eu.nome} />
              <div>
                <div className="eu-nome">{eu.nome}</div>
                <div className="eu-setor">{eu.setor}</div>
              </div>
              <button type="button" className="botao-texto" onClick={() => void sair()}>
                Sair
              </button>
            </div>
          )}
        </div>
      </aside>

      <main className="conteudo">
        <Outlet />
      </main>
    </div>
  );
}
