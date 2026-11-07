# Comandos do CLI (`quantumco`)

Todas as cargas de dados do projeto, e os comandos de operação em volta delas, num lugar só.
Conferido com `quantumco --help` em 2026-11-06.

```bash
cd backend
uv run quantumco --help              # lista os grupos
uv run quantumco cidade processar --help
```

## Antes de rodar qualquer coisa

- **Qual banco.** O CLI lê o `.env` da raiz. Sem nada na frente, ele grava no banco do
  `QC_DATABASE_URL`, que é a **produção**. Para usar a homologação, ponha `QC_USE_HOMOLOG=1` na
  frente do comando: o banco vira a cópia de homologação, as filas viram `scenarios-homolog` e
  `dados-homolog` e os e-mails vão para o `OWNER_EMAIL`. Com a homologação ligada, todo comando
  avisa no log. Os de `cidade`, `db`, `flags` e `imoveis` também mostram `[produção]` ou
  `[HOMOLOGAÇÃO]` na saída.
- **Migrações automáticas.** Antes de gravar, estes comandos aplicam **todas** as migrações
  pendentes no banco de destino: `snapshot build`, `analysis run`, `coldstart`,
  `territory import`, `cidade adicionar`, `cidade processar` (também com `--enfileirar`),
  `scenario run` e `worker --fila cenarios`. Contra a produção, isso pode aplicar uma migração
  que ainda não foi liberada. Quando for preciso migrar só algumas, use
  `migrate(url, only={...})` em Python.
- **Cidade.** Os comandos que tratam de uma cidade só aceitam `--cidade <código IBGE>`, e o padrão
  é Brusque (`4202909`). Em `cidade adicionar` e `cidade processar`, o código vai como argumento.
  Antes de processar, a cidade precisa estar no cadastro (`cidade adicionar`).
- **Log.** `--log-level` vem antes do grupo: `uv run quantumco --log-level DEBUG cidade processar 4208302`.
  O padrão é `QC_LOG_LEVEL`, ou `INFO`.

## Mapa das alimentações

| Alimentação | Comando | Fonte | Onde grava | Onde roda |
|---|---|---|---|---|
| Cadastro da cidade | `cidade adicionar <ibge>` | API de localidades do IBGE (nome, UF) + Overpass (`IBGE:GEOCODIGO`) | `road_network.study_areas` | qualquer máquina |
| Cidade completa | `cidade processar <ibge>` | todas as linhas abaixo, menos CNPJ e imóveis | PostGIS | aqui, ou na VPS com `--enfileirar` |
| Rede viária | `snapshot build` | OpenStreetMap (Overpass) | `road_network.snapshots` e trechos | qualquer máquina |
| Sintaxe espacial | `analysis run` | o snapshot atual da cidade (motor cityseer) | `syntax_analysis.analyses` | qualquer máquina (CPU pesada) |
| Rede + sintaxe | `coldstart` | as duas linhas acima | idem | qualquer máquina |
| Território | `territory import` | IBGE, SGB, CNES, Overture (tabela abaixo) | schema `territory` | qualquer máquina |
| CNPJ (Receita) | `dados cnpj` | Receita Federal (WebDAV) | bruto no RustFS, tratado no ClickHouse | **só na VPS** |
| Imóveis à venda | `imoveis importar` | glue-api do Grupo OLX (ZAP, Viva Real) | schema `listings` | atrás da flag `listings_glue_api` |
| Cenário "e se…" | `scenario run` | edições suas na rede | `syntax_analysis.scenarios` | qualquer máquina |

## 1. Cidades

O caminho normal para pôr uma cidade nova no site é **adicionar** e depois **processar**.

### `cidade adicionar <código>`

Cadastra o município: busca nome e UF no IBGE, acha a relação do limite no OSM pela tag
`IBGE:GEOCODIGO` e confere se a cidade está na UTM 22S (EPSG:31982). Por enquanto o banco só
aceita essa zona (ADR 0002). Grava a cidade como `preparando`. Se ela já estiver no cadastro, não
faz nada.

```bash
uv run quantumco cidade adicionar 4208302
# [produção] Itapema-SC cadastrada: IBGE 4208302, relação OSM 296608, EPSG:31982, faixa 7 km, preparando, mapa em /map/sc/itapema
```

### `cidade processar <código>`

Faz rede do OSM → análise sintática → território → publica (`publicada`). Brusque e as outras
cidades não são tocadas.

| Opção | O que faz |
|---|---|
| `--territorio` / `--no-territorio` | importa ou não as camadas do território (padrão: importa) |
| `--only <fonte>` | só estas fontes do território (repetível; nomes na seção 4) |
| `--enfileirar` | manda o job para a fila `dados` (ou `dados-homolog`), que o `worker --fila dados` da VPS executa; timeout de 4 h |

```bash
QC_USE_HOMOLOG=1 uv run quantumco cidade processar 4208302     # homologação, rodando aqui
uv run quantumco cidade processar 4208302 --enfileirar         # produção, na VPS
```

Referência: Itapema levou 403 s na homologação (rede 91 s, análise 195 s, território 117 s).

### `cidade listar`

Lista as cidades do cadastro, com o status, o endereço no site e o snapshot atual.

```bash
uv run quantumco cidade listar
```

## 2. Rede viária (OpenStreetMap)

### `snapshot build`

Baixa as vias do OSM no limite da cidade mais a faixa de 7 km, filtra, monta a topologia e grava o
snapshot com o manifesto. O snapshot novo vira o atual **daquela cidade**.

| Opção | O que faz |
|---|---|
| `--cidade <ibge>` | município (padrão: Brusque) |
| `--variant base\|with_pedestrian` | filtro de vias; `with_pedestrian` é a variante de sensibilidade (Q13) |
| `--as-of AAAA-MM-DD` | extrato numa data passada (consulta *attic* do Overpass) |

```bash
uv run quantumco snapshot build --cidade 4208302
```

## 3. Análise sintática

### `analysis run`

Calcula integração (NAIN) e escolha (NACH) angulares nos raios 400, 800, 1200, 2000 m e n, sobre o
snapshot atual da cidade. É a etapa pesada: em Itapema, o motor levou 192 s.

```bash
uv run quantumco analysis run --cidade 4208302
```

### `coldstart`

Faz `snapshot build` e `analysis run` da cidade, sem o território. Não muda o status no cadastro.
Para uma cidade nova, prefira `cidade processar`.

```bash
uv run quantumco coldstart --cidade 4202909
```

## 4. Território (camadas para o perfil dos polígonos)

### `territory import`

Baixa as fontes abertas e substitui as camadas **só da cidade escolhida**.

| Opção | O que faz |
|---|---|
| `--cidade <ibge>` | município (padrão: Brusque) |
| `--only <fonte>` | só esta fonte (repetível) |

| Fonte (`--only`) | Dado | Camadas gravadas |
|---|---|---|
| `ibge-setores` | Censo 2022: malha de setores da UF + agregados (população, renda, entorno, idade, alfabetização, saneamento) | `setores` |
| `ibge-cnefe` | CNEFE 2022 do município (pasta da UF no FTP do IBGE) | `cnefe` (pontos por espécie) e `enderecos` (busca de endereço) |
| `sgb-risco` | SGB: setores de risco geológico e cartas de suscetibilidade | `risco`, `suscet_inundacao`, `suscet_movimento_de_massa`, `suscet_enxurrada`, `suscet_corrida_de_massa` |
| `cnes` | CNES (Ministério da Saúde), filtrado pelo código de 6 dígitos | `cnes` |
| `overture-edificacoes` | Overture Maps, tema buildings, release `2026-10-21.0` | `edificacoes` |
| `overture-lugares` | Overture Maps, tema places, mesmo release | `lugares` |

```bash
uv run quantumco territory import --cidade 4208302
uv run quantumco territory import --cidade 4208302 --only sgb-risco --only cnes
```

Os downloads ficam em cache em `QC_CACHE_DIR/territory`. O cache do Overture leva a cidade e o
release no nome do arquivo.

### `territory layers`

Mostra as camadas importadas da cidade, com a quantidade, a data e a fonte.

```bash
uv run quantumco territory layers --cidade 4208302
```

## 5. Dados nacionais (Receita → RustFS → ClickHouse)

Por decisão do dono, os arquivos da Receita (vários GB) **nunca passam pela máquina de
desenvolvimento**. Quem baixa é o serviço `worker-dados` da VPS, o único que tem
`QC_ALLOW_RECEITA_DOWNLOAD=1`.

### `dados migrate`

Cria ou atualiza as tabelas do ClickHouse (`QC_CLICKHOUSE_URL`).

```bash
uv run quantumco dados migrate
```

### `dados cnpj`

Carga do CNPJ: guarda o bruto no RustFS e o tratado no ClickHouse.

| Opção | O que faz |
|---|---|
| `--competencia AAAA-MM` | mês da publicação (padrão: o mais recente) |
| `--enfileirar` | manda para a fila `dados` (é o jeito certo fora da VPS); timeout de 6 h |

```bash
uv run quantumco dados cnpj --enfileirar
uv run quantumco dados cnpj --competencia 2026-10 --enfileirar
```

## 6. Imóveis à venda (em validação, ADR 0003)

A fonte não é pública. A carga só roda com a flag `listings_glue_api` ligada e serve a uma prova de
conceito pessoal, sem redistribuir os dados.

### `imoveis importar`

Busca os anúncios da cidade e faz upsert idempotente: estado atual, histórico de mudanças e
quarentena dos registros inválidos.

| Opção | O que faz |
|---|---|
| `--cidade <ibge>` | município do cadastro (padrão: Brusque) |
| `--portal zap\|vivareal` | portal (padrão: `zap`) |
| `--max-paginas N` | limite de páginas, 50 anúncios cada (padrão: 200) |
| `--intervalo S` | segundos entre páginas (padrão: 3) |

Códigos de saída: `1` cidade não publicada, `2` flag desligada, `3` fonte bloqueou (403),
`4` já existe uma carga rodando.

```bash
uv run quantumco imoveis importar --cidade 4202909 --portal zap
```

### `flags listar | ligar <nome> | desligar <nome>`

Feature flags da tabela `public.feature_flags`. Cada carga lê a flag na hora, sem cache.

```bash
uv run quantumco flags listar
uv run quantumco flags ligar listings_glue_api
uv run quantumco flags desligar listings_glue_api
```

## 7. Cenários "e se…" (laboratório)

### `scenario run`

Aplica as edições na rede, recalcula a cidade inteira e compara com a análise publicada.

| Opção | O que faz |
|---|---|
| `--name <nome>` | nome do cenário (obrigatório) |
| `--remove <id do trecho>` | remove um trecho (repetível) |
| `--add "lon,lat;lon,lat;…"` | rua nova em WGS84 (repetível); as pontas encaixam na rede |
| `--snap <m>` | distância máxima de encaixe (padrão: 30 m) |
| `--cidade <ibge>` | município (padrão: Brusque) |

```bash
uv run quantumco scenario run --name ponte-centro --cidade 4202909 \
  --add "-48.918,-27.098;-48.915,-27.096"
```

### `scenario list`

Lista os cenários gravados.

Os cenários que os usuários criam no site não passam por aqui: vão para a fila `scenarios` e são
calculados pelo worker (seção 8).

## 8. Filas e workers (Redis + RQ)

### `worker`

| Opção | O que faz |
|---|---|
| `--fila cenarios` | cálculos dos cenários do site (padrão) |
| `--fila dados` | cargas pesadas: `cidade processar --enfileirar` e `dados cnpj --enfileirar` |
| `--workers N` | processos em paralelo, de 1 a 8 (padrão: `QC_WORKERS`, ou 2); no macOS roda 1 sem fork |
| `--burst` | esvazia a fila e sai |

| Fila | Produção | Homologação (`QC_USE_HOMOLOG=1`) |
|---|---|---|
| cenários | `scenarios` | `scenarios-homolog` |
| dados | `dados` | `dados-homolog` |

```bash
uv run quantumco worker --workers 2              # cenários
uv run quantumco worker --fila dados             # cargas (na VPS: serviço worker-dados)
```

## 9. Banco (PostGIS)

### `db migrate`

Aplica todas as migrações pendentes (`platform/migrations/*.sql`) no banco de destino.

```bash
QC_USE_HOMOLOG=1 uv run quantumco db migrate     # teste na homologação primeiro
uv run quantumco db migrate                      # produção: antes do deploy do backend
```

### `db sync-homolog`

Copia a produção para a homologação, no mesmo servidor. **Apaga o que havia na homologação.** A
cópia sai com as migrações que a produção já tem; para testar uma nova, rode depois
`QC_USE_HOMOLOG=1 uv run quantumco db migrate`.

```bash
uv run quantumco db sync-homolog
```

## 10. API e e-mail

| Comando | O que faz |
|---|---|
| `serve [--host 127.0.0.1] [--port 8000] [--reload]` | sobe a API (docs em `/docs`) |
| `mail check` | confere a chave do Resend e o domínio do remetente, sem enviar nada |
| `mail test [--to <e-mail>]` | envia um e-mail de teste (padrão: `OWNER_EMAIL`) |

## Receitas

**Cidade nova, testando na homologação:**

```bash
uv run quantumco db sync-homolog
QC_USE_HOMOLOG=1 uv run quantumco db migrate
QC_USE_HOMOLOG=1 uv run quantumco cidade adicionar 4208302
QC_USE_HOMOLOG=1 uv run quantumco cidade processar 4208302
QC_USE_HOMOLOG=1 uv run quantumco cidade listar
```

**Cidade nova na produção** (ordem do ADR 0002):

1. Migrar a produção, antes do deploy do backend.
2. Deploy do backend no Easypanel.
3. `uv run quantumco cidade adicionar <ibge>` e
   `uv run quantumco cidade processar <ibge> --enfileirar`.
4. Push do frontend, que publica sozinho.

**Atualizar só uma camada do território:**

```bash
uv run quantumco territory import --cidade 4202909 --only overture-edificacoes
```

**OSM novo, recalcular a sintaxe de uma cidade:**

```bash
uv run quantumco snapshot build --cidade 4202909
uv run quantumco analysis run --cidade 4202909
```

## Checagens de desenvolvimento (fora do CLI)

```bash
cd backend  && uv run ruff check . && uv run mypy && uv run lint-imports && uv run pytest
cd frontend && corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build
```
