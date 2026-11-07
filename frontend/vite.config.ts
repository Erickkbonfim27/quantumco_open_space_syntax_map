import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

import pkg from "./package.json" with { type: "json" };

// QC_API_PROXY (ambiente ou .env) troca o destino do /api em dev; padrão: a API local na 8000
const proxy = loadEnv("development", "..", "QC_").QC_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  // versão do site (package.json) na barra de status; a da metodologia vem de cada rede
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  // um único .env na raiz do monorepo (ver .env.example)
  envDir: "..",
  // o MapLibre sozinho tem ~1 MB minificado; o aviso padrão de 500 kB não ajuda aqui
  build: { chunkSizeWarningLimit: 1500 },
  // em dev, /api vai para a API local (`uv run quantumco serve`); QC_API_PROXY troca o destino
  server: { proxy: { "/api": proxy } },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
