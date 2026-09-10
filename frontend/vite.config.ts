import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// O front fala com o Django pela mesma origem: /api vai por proxy para :8000.
// Assim o cookie de sessao e o CSRF funcionam sem CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
      "/media": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
});
