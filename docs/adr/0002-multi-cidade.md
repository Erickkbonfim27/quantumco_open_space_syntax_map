# ADR 0002 — Várias cidades: cada uma é um contexto separado

Data: 2026-11-06 · Status: **aceito**

## Contexto

O quantumco nasceu como o mapa sintático de Brusque, mas o objetivo é o Brasil; Itapema-SC é a
segunda cidade. Até aqui tudo supunha uma cidade só: o município ficava em
`methodology/v1/study_area.yaml`, o banco tinha **um** snapshot e **uma** análise "atuais" (índice
único global em `is_current`), toda importação do território apagava a tabela inteira, os
cenários tinham limites fixos de Brusque e o site chamava rotas sem cidade.

Pedido do dono: escolho Brusque e vejo, consulto e faço cenários sobre Brusque; escolho Itapema e
faço o mesmo sobre Itapema. As cidades não se misturam.

## Decisão

1. **Cidade = município pelo código IBGE** (7 dígitos; `shared_kernel/city.py`). O cadastro é
   `road_network.study_areas`: código, nome, UF, slug, relação OSM, faixa externa, EPSG e status
   (`preparando` → `publicada`). A relação OSM é achada pelo `IBGE:GEOCODIGO` e conferida no
   download (nunca pelo nome, Q14). A faixa (7 km) é regra da metodologia, gravada na cidade no
   cadastro para o cálculo ser reproduzível.
2. **"Atual" por cidade**: `ibge_code` em snapshots e análises, índice único
   `(ibge_code) where is_current`, troca atômica só dentro da cidade. Publicar Itapema não toca
   em Brusque.
3. **Todo dado carrega a cidade**: cenários do laboratório, cenários do usuário, cálculos e as
   tabelas do território (`layers` com chave `(ibge_code, layer)`, prédios com
   `(ibge_code, building_id)`: a mesma edificação pode estar no recorte de duas vizinhas). A grade
   de 30 m é uma por cidade (`territory.grids`); a de Brusque ficou idêntica.
4. **Sem RLS por cidade.** Não há segredo entre cidades (tudo é dado aberto); o risco é de
   correção, não de segurança. A proteção é: a cidade é argumento obrigatório de toda leitura e
   gravação (o mypy cobra), chaves e índices com `ibge_code`, testes de isolamento e um teste que
   reprova consulta às tabelas por cidade sem `ibge_code` (`tests/unit/test_city_scoped_sql.py`).
   A fronteira de privacidade real é por dono (cenários do usuário); RLS por `owner_id` fica como
   possível reforço futuro.
5. **API por cidade**: `GET /api/v1/cities` (publicadas) e `/api/v1/cities/{ibge}/network|syntax|
   territory/…`. As rotas antigas, sem cidade, respondem Brusque enquanto o site antigo existir.
6. **Site**: a cidade vai na URL (`/map/sc/itapema`); `/map` abre a última escolhida. Um cenário
   nasce numa cidade e não troca.
7. **Processar uma cidade**: `quantumco cidade adicionar <código>` e
   `quantumco cidade processar <código> [--enfileirar]` (rede do OSM → análise → território →
   publica). Com `--enfileirar`, roda na fila `dados` da VPS (ADR 0001).

## CRS: por enquanto, só UTM 22S

O Python usa o EPSG da cidade (do cadastro e do snapshot) no lugar das constantes, mas as colunas
de geometria seguem tipadas em `31982` (SIRGAS 2000 / UTM 22S, 54°W–48°W: Santa Catarina inteira e
quase todo o PR e o RS). O cadastro recusa cidade fora dessa zona com mensagem clara. Abrir outras
zonas (18 a 25) exige uma migração que solte o SRID das colunas (`geometry(LineString)` sem SRID),
refazendo as views que dependem delas, e trocar as constantes de SRID que restam no território.

## Consequências

- Ordem segura na produção: **migrar antes do deploy**. A migração 012 mantém o padrão
  `'4202909'` em cenários e cálculos enquanto o código antigo (que não manda a cidade) estiver no
  ar; uma migração futura tira esses padrões.
- O frontend publica sozinho no push; o backend é manual. Por isso o backend (com as rotas antigas)
  vai antes, e o frontend só depois da cidade nova publicada.
- Cada cidade é calculada sozinha, com a sua faixa; regiões metropolitanas (cidades vizinhas no
  mesmo grafo) ficam para depois.
- Textos de exemplo das páginas de dados e metodologia ainda usam números de Brusque.
