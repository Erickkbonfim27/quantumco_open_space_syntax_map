# quantumco

Mapa sintático (sintaxe espacial) aberto e gratuito de **Brusque-SC**, construído sobre o
OpenStreetMap. Para arquitetura e urbanismo, construtoras e incorporadoras.

- Decisões de produto, metodologia e arquitetura: [`docs/decisions.md`](docs/decisions.md)
- Metodologia versionada (filtros, larguras, limiares pré-registrados): [`methodology/v1/`](methodology/v1/)
- Glossário PT↔EN: [`docs/glossary.md`](docs/glossary.md)

## Estado

Passo 1 de 7 (ver `docs/decisions.md`): contexto **Rede Viária** (OSM → filtro → topologia →
maior componente → snapshot), **API** servindo a rede e **frontend** que a exibe em cinza neutro.
Análise angular **preliminar** (cityseer; juiz depthmapX no CI pendente) com NAIN e NACH em
400 m, 800 m, 1,2 km, 2 km e n, nas cores da sintaxe espacial (`methodology/v1/symbology.yaml`).
Fontes da view de polígonos: [`docs/data-sources.md`](docs/data-sources.md).

## Rodar localmente

```bash
cp .env.example .env

# 1. cold start (só na primeira vez ou para reprocessar): snapshot do OSM + análise sintática
cd backend
uv sync
uv run quantumco coldstart             # ~10 min: Overpass (1–3 min) + cityseer (~8 min)
# ou em partes: uv run quantumco snapshot build && uv run quantumco analysis run

# 2. API  →  http://localhost:8000  (docs em /docs)
uv run quantumco serve --reload

# 3. frontend (outro terminal)  →  http://localhost:5173  (repassa /api para a 8000)
cd frontend
corepack pnpm install
corepack pnpm dev
```

| Endpoint | Conteúdo |
|---|---|
| `GET /health` | status + id do snapshot carregado |
| `GET /api/v1/network/manifest` | manifesto (data do OSM, contagens, metodologia) |
| `GET /api/v1/network/links` | trechos em GeoJSON (WGS84), gzip + ETag |
| `GET /api/v1/network/municipality` | limite de Brusque em GeoJSON |
| `GET /api/v1/syntax/manifest` | manifesto da análise (motor, raios, preliminar ou não) |
| `GET /api/v1/syntax/links` | trechos com NAIN/NACH e classe (0–6) por raio |

Qualidade:

```bash
cd backend  && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest
cd frontend && corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test
```

## Deploy (Easypanel, Nixpacks)

Dois serviços "App" apontando para este repositório no GitHub:

| Serviço | Build path | Config | Porta | Observações |
|---|---|---|---|---|
| `api` | `/` | `nixpacks.toml` | 8000 | volume em `/data`; variáveis do `.env` (seção 1 + e-mail); health em `/health` |
| `web` | `/frontend` | `frontend/nixpacks.toml` + `frontend/Caddyfile` | 80 | variável `API_UPSTREAM` = endereço interno da API (ex.: `projeto_api:8000`) |

Depois do primeiro deploy da API, no console do serviço: `quantumco coldstart` (snapshot do
OSM + análise; cerca de 15 min em 2 vCPU). Alternativa aos Nixpacks: `infra/docker/*.Dockerfile`.

## Licenças

Código: AGPL-3.0-or-later. Dados: ODbL 1.0 (© OpenStreetMap contributors).
Relatório metodológico: CC BY 4.0.
