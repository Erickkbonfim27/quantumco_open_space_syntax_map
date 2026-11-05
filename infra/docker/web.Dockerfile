# Frontend estático servido pelo Caddy.
# Build context: raiz do repositório.
#   docker build -f infra/docker/web.Dockerfile -t quantumco-web .
# Os dados vêm da API: o Caddy repassa /api/* para o serviço da API (variável API_UPSTREAM).

FROM node:24-alpine AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.28.9 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# variáveis VITE_* são lidas no build
ARG VITE_BASEMAP_STYLE_URL=
ARG VITE_API_URL=
ARG VITE_TURNSTILE_SITE_KEY=
ENV VITE_BASEMAP_STYLE_URL=$VITE_BASEMAP_STYLE_URL \
    VITE_API_URL=$VITE_API_URL \
    VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
RUN pnpm build

FROM caddy:2-alpine
COPY infra/docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv/site
EXPOSE 80
