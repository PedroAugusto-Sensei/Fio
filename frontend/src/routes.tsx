import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ProvedorPendentes } from "./components/Pendentes";
import { RotaDeAdmin, RotaProtegida } from "./components/Sessao";
import { Caixa } from "./pages/Caixa";
import { Chamado } from "./pages/Chamado";
import { Chamados } from "./pages/Chamados";
import { Convite } from "./pages/Convite";
import { CriarConta } from "./pages/CriarConta";
import { Login } from "./pages/Login";
import { ConfigurarImap } from "./pages/ConfigurarImap";
import { Membros } from "./pages/Membros";

/**
 * Três rotas sem sessão — entrar, cadastrar a empresa e aceitar convite — e as de
 * dentro: a caixa de entrada, a lista, o chamado e a lista de membros.
 *
 * `/configuracoes/membros` é de admin no front **e** no back. O front só evita
 * oferecer o que não vai funcionar; quem recusa de verdade é o back.
 */
export function Rotas() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/criar-conta" element={<CriarConta />} />
      <Route path="/convite/:token" element={<Convite />} />
      <Route
        element={
          <RotaProtegida>
            <ProvedorPendentes>
              <Layout />
            </ProvedorPendentes>
          </RotaProtegida>
        }
      >
        <Route path="/configuracoes/imap" element={<ConfigurarImap />} />
        <Route path="/emails" element={<Caixa />} />
        <Route path="/chamados" element={<Chamados />} />
        <Route path="/chamados/:id" element={<Chamado />} />
        <Route
          path="/configuracoes/membros"
          element={
            <RotaDeAdmin>
              <Membros />
            </RotaDeAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/chamados" replace />} />
    </Routes>
  );
}
