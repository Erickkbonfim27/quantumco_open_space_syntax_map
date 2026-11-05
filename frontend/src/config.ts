export const config = {
  // vazio = mapa de fundo escuro da marca (features/map/basemapStyle.ts)
  basemapStyleUrl: import.meta.env.VITE_BASEMAP_STYLE_URL || null,
  // vazio = mesma origem (em dev o Vite repassa /api para a API; em produção, o Caddy)
  apiUrl: (import.meta.env.VITE_API_URL || "").replace(/\/+$/, ""),
} as const;
