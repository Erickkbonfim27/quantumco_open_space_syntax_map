import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // um único .env na raiz do monorepo (ver .env.example)
  envDir: "..",
  // o MapLibre sozinho tem ~1 MB minificado; o aviso padrão de 500 kB não ajuda aqui
  build: { chunkSizeWarningLimit: 1500 },
  // em dev, /api vai para a API local (`uv run quantumco serve`)
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
