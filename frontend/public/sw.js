// Service worker minimo: existe so para o navegador oferecer instalar o Fio.
// NAO cacheia resposta de API — chamado velho na tela seria pior que tela vazia.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (evento) => evento.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
