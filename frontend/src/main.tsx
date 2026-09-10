import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import "./styles/app.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// Service worker só para o Fio ser instalável. Ele não cacheia resposta de API.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* sem service worker o app continua funcionando, só não instala */
    });
  });
}
