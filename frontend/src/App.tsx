import { BrowserRouter } from "react-router-dom";

import { ProvedorSessao } from "./components/Sessao";
import { Rotas } from "./routes";

export function App() {
  return (
    <BrowserRouter>
      <ProvedorSessao>
        <Rotas />
      </ProvedorSessao>
    </BrowserRouter>
  );
}
