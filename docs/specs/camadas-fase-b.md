# Spec — Camadas territoriais, fase B (10 fontes abertas + 3 análises)

Versão 0.3 · 2026-11-06 · status: **em implementação**. Etapa 0 pronta. Etapa 1: prédios (F1) na
produção; lugares (F2b) e Censo (F10) na homologação; CNPJ (F2a) a fazer.

Origem: análise do acervo `erickkbonfim-portifolio/documentos/search` (fontes, lacunas e concorrência)
cruzado com o que o mapa já tem (`docs/data-sources.md`). Esta spec junta numa só as fases B e C
que estavam em aberto e acrescenta o que a pesquisa trouxe.

---

## 1. Objetivo

Enriquecer o perfil do polígono e o mapa público de Brusque com dados **gratuitos, abertos e com
detalhe abaixo do município**, e usar esses dados em três análises que conversam com a sintaxe:

1. **A cidade na cheia**: o cenário "e se…" com as vias inundáveis fora da rede.
2. **Cidade de 15 minutos**: quanto da população chega a pé aos serviços do dia a dia.
3. **Sintaxe × crescimento**: se a cidade cresceu ao longo dos eixos mais integrados.

### Fora do escopo

- Qualquer dado ou texto de **preço** (ITBI, CUB, anúncios, FipeZAP). A regra "não mede preço" continua
  valendo (decisões, Q27). O ITBI só entra como validação, por LAI.
- Análise Turner/VGA e morfometria com momepy. Esta spec só deixa os prédios prontos para elas; cada
  uma terá a sua spec.
- Zoneamento da LC 419/2024. Ele não existe aberto: segue o pedido por LAI (ver §9).
- Fontes pagas, footfall e dados por pessoa (Serasa, operadoras).

## 2. Regras herdadas (valem para todas as fontes)

| Regra | Como aplicar aqui |
|---|---|
| Fonte, data e licença em cada número | Toda camada grava `source`, `source_url`, `license`, `fetched_at` e a **versão ou data do dado** em `territory.layers.meta`. O painel mostra isso em cada bloco. |
| Sem dado pessoal | Telefone, e-mail, site, nome de pessoa e CPF são descartados **na importação**, como já é feito com o CNES. O MEI nunca aparece como ponto. |
| Licença sem redistribuição → só derivado | O MDT do SIGSC (e a hidrografia do SIGSC) entram só como estatística ou classe agregada a 30 m, nunca como valor bruto. |
| Rigor | Métrica e limiar de cada análise são **pré-registrados** nesta spec antes de olhar o resultado. Mudou o limiar → atualiza a spec e o semver da metodologia. |
| Importação reproduzível | `quantumco territory import --only <fonte>`, com cache de download, novas tentativas e log de etapas, tempos e tentativas desde a primeira versão (combinado de trabalho). |
| Contratos do import-linter | O domínio e a aplicação continuam sem I/O. As libs novas (rasterio, pystac, overturemaps) entram na lista de proibidas para `domain`/`application`. |
| Recorte por código, nunca por nome | Município IBGE 4202909; na Receita, município 8055; nas fontes por bbox, a bbox do município com 1 km de folga. |

## 3. Fontes e licenças

| # | Fonte | Licença | Uso permitido |
|---|---|---|---|
| F1 | Overture Maps, tema *buildings* (já junta OSM, Microsoft e Google Open Buildings) | ODbL (mista, por fonte) | mostrar e redistribuir, com atribuição; derivados em ODbL |
| F2a | Receita Federal, CNPJ (Estabelecimentos) | dados abertos; licença formal não confirmada | **só agregado**; MEI à parte |
| F2b | Overture Maps, tema *places* | CDLA Permissive 2.0 | mostrar e redistribuir, com atribuição |
| F3a | Atlas Digital de Desastres / S2iD (MIDR, CEPED-UFSC) | dado público | histórico do município, citando |
| F3b | ANA, telemetria (nível do Itajaí-Mirim em Brusque); CIRAM como alternativa | dado público | leitura atual, citando; sem republicar a série |
| F4 | SIGSC, MDT 1 m (2010–12) | acesso livre, sem licença de redistribuição | **só derivado** (declividade e altitude por célula de 30 m) |
| F5 | INEP: Catálogo de Escolas + IDEB por escola | dados abertos | mostrar, citando |
| F6 | MapBiomas Coleção 10 (1985–2024), download direto | CC BY 4.0 | mostrar, citando a coleção |
| F7a | Sentinel-2 L2A (Copernicus), via Planetary Computer ou Earth Search | livre e aberta (aviso Copernicus) | mostrar, com aviso |
| F7b | Landsat 8/9 C2 L2 (USGS), via Planetary Computer | domínio público | mostrar |
| F8 | Obrasgov.br (API de projetos de investimento) | dados abertos | mostrar, citando |
| F9 | SICAR/CAR (APP e reserva legal declaradas) | dado público | mostrar com aviso de "autodeclarado" |
| F10 | IBGE Censo 2022, agregados por setor (já importados; novas variáveis) | "Fonte: IBGE" | mostrar |

**Sem Google Earth Engine.** O GEE só é gratuito para uso não comercial. Todas as fontes de satélite
vêm por download direto ou STAC aberto.

## 4. Peças comuns (fazer primeiro)

### 4.1 Grade de 30 m para dados raster

MDT, MapBiomas, Sentinel e Landsat viram valores numa **grade fixa de 30 m** em EPSG:31982, alinhada a
múltiplos de 30 e cobrindo a bbox do município com 1 km de folga (429.516 células, medido). Motivos:

- é um só padrão de consulta no polígono (pontos de centro dentro do polígono), sem depender da
  extensão `postgis_raster`;
- 30 m é a resolução nativa do Landsat e do MapBiomas; Sentinel (10 m) e MDT (1 m) são **agregados**, e
  isso resolve de quebra a licença do MDT;
- a importação de uma camada substitui só as linhas dela, como já acontece hoje.

Tabelas `territory.grid`, `territory.grid_values` e `territory.images` na migração
`009_territory_grid_buildings.sql` (as 005–008 já estavam ocupadas). A grade em si está em
`territory/domain/grid.py` (`BRUSQUE_GRID`):

- origem 694.590 E / 7.013.010 N, 854 × 1.012 células (864.248 no retângulo);
- linha 0 no norte e id = linha × colunas + coluna;
- só as células a até 1 km da união dos setores do IBGE são gravadas, na primeira importação de uma
  camada raster.

**Mudar a grade exige migração.**

- Domínio: `territory/domain/records.py` ganha `GridLayer(layer, values: Mapping[int, float], image)`.
  `LayerData` ganha o campo `grid: GridLayer | None`.
- Infraestrutura: `territory/infrastructure/raster.py`, com leitura por janela (`rasterio` +
  `/vsicurl/`, porque os COG suportam leitura parcial), reamostragem para a grade e geração do PNG.
- Dependências novas: `rasterio`, `numpy` (já vem com o shapely), `pystac-client`, `planetary-computer`.

### 4.2 Pontos e áreas novas

- Prédios em tabela própria (são muitos e têm atributos fixos):

```sql
create table territory.buildings (
    building_id  text primary key,              -- id do Overture
    source       text not null,                 -- OpenStreetMap | Microsoft ML Buildings | Google Open Buildings | …
    height_m     real,
    floors       smallint,
    class        text,
    area_m2      real not null,
    geom         geometry(MultiPolygon, 31982) not null
);
create index buildings_geom on territory.buildings using gist (geom);
```

- Empresas, Places, escolas do INEP e obras usam `territory.places`, como o CNEFE e o CNES.
- CAR e cheias usam `territory.zones`, como o SGB.

### 4.3 API e mapa

| Rota | Novo | Para quê |
|---|---|---|
| `GET /territory/images` | sim | lista das imagens (camada, limites, legenda) |
| `GET /territory/images/{layer}.png` | sim | PNG da camada; cache de 1 h, como o `map/{name}` |
| `GET /territory/tiles/buildings/{z}/{x}/{y}.mvt` | sim | prédios em vetor (`ST_AsMVT`); a partir do z13 |
| `GET /territory/map/{name}` | amplia `MAP_LAYERS` | `obras`, `car_app`, `cheia_*`, `escolas` (agora do INEP) |
| `POST /territory/polygon-profile` | amplia a resposta | blocos novos (§5) |

No frontend:

- `OVERLAYS` ganha `predios`, `declividade`, `verde`, `calor`, `urbanizacao`, `obras` e `car`.
- As imagens entram como `image` source do MapLibre.
- Cores ficam fora da paleta sintática, como hoje.

### 4.4 Pilha de camadas do painel

| Nível | Hoje | Entra |
|---|---|---|
| N7 (novo) | — | **FORMA CONSTRUÍDA**: prédios, ocupação, idade da urbanização |
| N6 Risco | risco, suscetibilidade | histórico de desastres, nível do rio agora, "a rede na cheia" |
| N5 Equipamentos e uso | CNEFE, CNES | empresas por grupo de CNAE, Places, escolas com IDEB, obras federais, **15 minutos** |
| N4 Entorno urbano | entorno do Censo | verde (NDVI), calor de superfície |
| N3 População e renda | pessoas, renda | faixas de idade, alfabetização, saneamento |
| N2 Rede viária | sintaxe | — |
| N1 Território | área, perímetro | declividade e altitude, APP e reserva legal (CAR) |

## 5. Fonte por fonte

Cada item lista: **acesso** · **o que guardar** · **recorte no polígono** · **mapa** · **testes** ·
**verificar antes**.

### F1. Edificações (Overture *buildings*)

- **Acesso:** pacote `overturemaps` (`overturemaps download --bbox=… --type=building -f geoparquet`).
  Release fixo, registrado em `meta.release`.
- **Guardar:** id, fonte, altura, andares, classe, área e geometria. Prédios com menos de 10 m² são
  descartados (ruído do ML); a contagem de descartados vai no `meta`.
- **Polígono:** contagem; área projetada total; **taxa de ocupação** (projeção ÷ área do polígono);
  altura média e % com altura conhecida; divisão por fonte (OSM × ML).
- **Mapa:** vetor MVT a partir do z13, com cor por fonte opcional (para mostrar a origem do dado).
- **Testes:**
  - unitário: normalização (descarte < 10 m², reprojeção, MultiPolygon válido);
  - db: a taxa de ocupação de um polígono sintético com 2 prédios conhecidos dá o valor exato.
- **Verificar:** quantos prédios o Overture tem em Brusque contra os 510 do OSM; quais fontes aparecem.

### F2. Empresas (CNPJ) e lugares (Overture *places*)

**CNPJ**

- **Acesso:** arquivos mensais `Estabelecimentos0..9.zip` da Receita. Leitura em fluxo (são vários
  GB), filtrando `municipio == 8055` e `situacao == 02` (ativa).
- **Guardar:** CNAE principal, porte, opção pelo MEI, data de início, **nível de geocódigo** e
  coordenada.
  - Não guardar razão social, nome fantasia, telefone, e-mail nem o CNPJ em claro (só um hash, para
    não duplicar).
- **Geocódigo pelo CNEFE**, em cascata. O nível usado fica em `attrs.geo`:
  1. CEP + número exatos → coordenada do endereço;
  2. logradouro normalizado + número → endereço mais próximo do número;
  3. CEP → centroide dos endereços do CEP;
  4. sem acerto → fica fora, e a contagem vai no `meta`.
- **Grupos de CNAE** (tabela versionada em `backend/methodology/v1/cnae_groups.csv`):
  - comércio do dia a dia;
  - comércio e serviço dependente de passagem (lista pré-registrada para a validação, Q11);
  - indústria (seção C; o têxtil em destaque);
  - serviços;
  - associações, igrejas e ONGs (divisão 94).
- **Polígono:** contagem por grupo, **sem MEI**, e o MEI como um número separado. Nunca lista nomes.
- **Mapa:** densidade numa grade de 200 m (célula com menos de 3 empresas não aparece). **Sem pontos.**

**Overture Places**

- **Acesso:** `overturemaps download --type=place`.
- **Guardar:** nome, categoria principal e confiança. Só `confidence ≥ 0.5`. Telefone, site e e-mail
  são descartados.
- **Uso:** mostrar comércio e serviços com nome no mapa e conferir o geocódigo do CNPJ. Uma métrica de
  qualidade vai no `meta`: % das empresas do grupo "comércio do dia a dia" com um Place da mesma
  categoria a menos de 50 m.

**Testes:** unitário do geocódigo em cascata, com casos de CEP genérico, número fora da faixa e
logradouro com abreviação; unitário da tabela de CNAE (todo código cai em um único grupo).

**Verificar:** a licença dos arquivos da Receita; a taxa de acerto do geocódigo (meta: ≥ 80% nos
níveis 1 e 2); a cobertura do Places em Brusque.

### F3. Cheias do Itajaí-Mirim

- **F3a, histórico.** Eventos de Brusque no Atlas Digital de Desastres (1991 em diante) ou no S2iD:
  data, tipo (inundação, enxurrada, deslizamento), pessoas afetadas e se houve decreto. Guardar em
  `territory.layers.meta` da camada `desastres`, porque é dado do município, não do polígono.
  Aparece no N6 como uma linha do tempo.
- **F3b, nível do rio agora** (opcional, depois). Estação da ANA no Itajaí-Mirim em Brusque, com a
  leitura mais recente, cache de 15 min e link para a Defesa Civil. **Não guardar a série.** Só entra
  se a API da ANA for estável e aberta. Senão, fica de fora (o CIRAM tem licença menos clara).
- **Zonas de cheia.** Ver a análise A1 (§6).
- **Verificar:** o arquivo de download do Atlas (CSV ou XLSX, e a última atualização); o código da
  estação da ANA em Brusque e se a API precisa de cadastro.

### F4. Declividade e altitude (MDT SIGSC)

- **Acesso:** o WCS `sigsc.sc.gov.br/sigserver/SIGSC/wcs`, cobertura `SIGSC__MDT-2012`, baixado em
  blocos de 2 × 2 km (com cache).
- **Derivar:**
  - altitude média por célula de 30 m;
  - declividade (%) calculada a 5 m e resumida por célula como **média** e **% da célula acima de
    30%**. Acima de 30% é o limite da Lei 6.766/79 para parcelamento: limiar legal, não escolhido por
    nós.
- **Guardar:** `grid_values` com as camadas `altitude`, `declividade`, `declividade_30`. O valor bruto de
  1 m **não** é guardado.
- **Polígono:** altitude mínima, média e máxima; declividade média; **% da área acima de 30%**.
- **Mapa:** imagem em 4 classes (0–8%, 8–20%, 20–30%, > 30%).
- **Também alimenta:** a variante com declividade dos 15 minutos (A2) e as zonas de cheia v2 (A1).
- **Verificar:** o limite de tamanho por pedido do WCS e o tempo total; se a imagem em classes a 30 m
  está dentro do "acesso livre" (é derivada e agregada; anotar a decisão).

### F5. Escolas e IDEB (INEP)

- **Acesso:** Catálogo de Escolas do INEP (código, nome, rede, etapas e coordenada) + planilhas do
  IDEB por escola (anos iniciais, anos finais e ensino médio; última edição publicada).
- **Guardar:** a camada `inep` em `places`, com `kind` igual a creche, fundamental ou médio. `attrs`:
  rede, etapas, IDEB por etapa e ano. Só escolas em atividade.
- **Polígono:** escolas por rede e etapa; IDEB das escolas dentro do polígono (lista, **sem média**:
  média de IDEB de escolas diferentes não tem sentido).
- **Mapa:** a camada `escolas` passa a vir do INEP; a do CNEFE fica só para contagem.
- **Verificar:** se o Catálogo traz coordenada para todas as escolas de Brusque; se não, completar
  pelo endereço no CNEFE (mesma cascata do F2).

### F6. Expansão urbana (MapBiomas)

- **Acesso:** os COG anuais da Coleção 10 (`brazil_coverage_{ano}.tif`), lidos por janela.
- **Derivar, por célula:**
  - `mb_classe` = classe de 2024;
  - `mb_ano_urbano` = **primeiro ano** em que a célula foi classe 24 (área urbanizada) e **continuou**
    urbana pelos 3 anos seguintes (filtro pré-registrado contra ruído de classificação).
- **Polígono:** % urbanizado em 2024; % de vegetação nativa; ano mediano de urbanização; área
  urbanizada por década (1985–94, 95–04, 05–14, 15–24).
- **Mapa:** imagem "idade da urbanização" (rampa por década).
- **Verificar:** a URL e a data da Coleção 10; o código da classe urbana nessa coleção.

### F7. Verde e calor

- **NDVI (Sentinel-2 L2A):** mediana dos verões (dez–fev) de 2023/24, 2024/25 e 2025/26, com máscara de
  nuvem pela banda SCL. Média dos pixels de 10 m dentro da célula de 30 m.
- **Calor (Landsat 8/9 C2 L2, banda ST_B10):** mediana das cenas diurnas de verão no mesmo período,
  com máscara pelo `QA_PIXEL`, em °C.
  - Guardar como **anomalia**: célula menos a mediana das células urbanizadas (MapBiomas classe 24).
  - O texto do painel diz "temperatura da **superfície**, não do ar".
- **Polígono:** NDVI médio; % da área com NDVI > 0,5; anomalia de calor média.
- **Mapa:** duas imagens (`verde` e `calor`).
- **Testes:** unitário da máscara de nuvem e da agregação 10 m → 30 m com um raster sintético.
- **Verificar:** o número de cenas sem nuvem por verão em Brusque (o vale tem muita nuvem). Se ficar
  abaixo de 3 cenas por verão, ampliar a janela para nov–mar.

### F8. Obras públicas (Obrasgov.br)

- **Acesso:** a API de projetos de investimento, filtrada por UF = SC e município = Brusque, mais a
  rota de geometria.
- **Guardar:** a camada `obras` em `places` (ponto; linha ou polígono vira centroide, com o traçado em
  `attrs.shape`): nome, situação, órgão, valor previsto e datas.
- **Polígono:** a lista de obras dentro do polígono.
- **Mapa:** os pontos por situação. No laboratório, a obra com traçado de linha pode virar "nova via"
  com um clique (fase 2 deste item).
- **Verificar:** se as obras de Brusque têm geometria preenchida; se não, a camada é só lista.

### F9. Restrição ambiental (CAR)

- **Acesso:** o download por município da consulta pública do SICAR **tem captcha**. Então a
  importação lê um arquivo baixado à mão: `quantumco territory import --only car --file <zip>`.
- **Guardar:** a APP e a reserva legal em `zones` (`car_app`, `car_reserva_legal`). Não guardar o
  polígono do imóvel nem o código do imóvel.
- **Polígono:** área em APP e em reserva legal declaradas.
- **Mapa:** camada `car`, com o aviso "declarado pelo dono do imóvel; não é a APP legal oficial".
- **Verificar:** a data do arquivo e se ele cobre a parte urbana (o CAR é rural; na cidade quase não
  haverá polígonos).

### F10. Mais variáveis do Censo 2022 (por setor)

- **Acesso:** os mesmos arquivos de agregados por setor já usados, mais os temas de demografia,
  alfabetização e características dos domicílios.
- **Novos atributos em `TRACT_ATTRS`:**
  - faixas de idade 0–14, 15–29, 30–59 e 60+;
  - pessoas de 15 anos ou mais e as alfabetizadas;
  - domicílios com água da rede geral, com esgoto na rede geral (ou fossa ligada à rede) e com coleta
    de lixo.
  - Os códigos `V…` saem do dicionário do IBGE e ficam documentados no adaptador.
- **Polígono:** com o mesmo peso dasimétrico de hoje: pirâmide em 4 faixas, taxa de alfabetização e
  % de saneamento. Setor com dado suprimido conta à parte, como já acontece com a renda.
- **Testes:** a soma das faixas de idade da cidade = 141.385 pessoas (± supressão declarada).

## 6. Análises

### A1. A cidade na cheia

**Pergunta:** quais trechos da rede ficam fora numa cheia, e como muda a integração do resto da
cidade.

- **v1, zonas oficiais (sem modelo nosso).** A zona de cheia é a suscetibilidade a inundação do SGB, nas
  classes Alta ou Alta + Média. Já está importada.
- **v2, altura acima do rio (HAND).** Com o MDT (F4) a 5 m, direção de fluxo D8 e uma rede de drenagem
  calibrada para coincidir com a hidrografia do SIGSC, cada célula ganha a altura acima do ponto de
  drenagem para onde escoa.
  - Zonas "até 2, 4, 6 e 8 m" em `zones` (camada `cheia_hand`).
  - É um modelo **simplificado**: o painel diz isso, e a v2 só é publicada se cobrir ≥ 80% da área de
    suscetibilidade Alta do SGB (critério pré-registrado).

**Mudança nos cenários:**

- O cenário hoje aceita até `MAX_EDITS = 200` edições por via, e uma cheia fecha centenas de trechos.
  Entra um tipo novo de edição, **interdição por zona**:
  `{"type": "close_zone", "layer": "suscet_inundacao", "categories": ["Alta"]}`.
  - Ela conta como **uma** edição.
  - O domínio de `scenarios` só valida camada e categorias contra uma lista permitida.
- **Quem descobre os trechos:** uma porta nova, `ZoneClosureResolver.links(snapshot_id, layer,
  categories) -> set[link_id]`.
  - A implementação fica no bootstrap, com um `ST_Intersects` entre `road_network.links` e
    `territory.zones`, e respeita o contrato "contextos não importam uns aos outros".
  - Um trecho sai se **mais de 50% do comprimento** estiver na zona (limiar pré-registrado; ponte com
    `is_bridge` não sai).
- **Resultado:** igual ao de qualquer cenário. Mais duas contagens:
  - km interditados;
  - domicílios do CNEFE que ficam em **componentes desconectados** do maior componente.
- **Texto:** "configuração da malha sem os trechos na zona X", nunca "previsão de cheia" (Q23, Q31).
- **Atalho na tela:** em "Novo cenário", um modelo pronto chamado "A cidade na cheia".
- **Testes:**
  - unitário: validação do `close_zone`;
  - db: o resolvedor numa malha de 3 trechos com uma zona conhecida;
  - api: o cenário roda e devolve as contagens.

### A2. Cidade de 15 minutos

**Pergunta:** que parte dos domicílios chega a pé, em até 15 min, a cada serviço básico.

- **Novo contexto `accessibility`** (hexagonal, com o seu contrato no import-linter). O bootstrap entrega
  a ele o grafo da rede (de `road_network`) e os pontos de destino (de `territory`).
- **Rede a pé:** a malha base + footway, path e steps (a variante pedonal que já existe).
- **Distância:** pela rede, até o destino mais próximo de cada categoria, saindo de cada domicílio do
  CNEFE (65 mil), com Dijkstra a partir de várias origens por categoria.
- **Categorias** (pré-registradas):
  - escola de ensino fundamental (INEP);
  - creche (INEP);
  - unidade básica de saúde (CNES, atenção básica);
  - comércio do dia a dia (grupo de CNAE do F2);
  - parada de ônibus (OSM `highway=bus_stop`);
  - praça ou parque (OSM `leisure=park|playground`).
- **Limiar:** 1.250 m (15 min a 5 km/h). É o mesmo raciocínio do raio de 1.200 m já usado.
- **Variante com declividade:** tempo pela função de Tobler, com a altitude de cada nó vinda do F4. Entra
  como **variante de sensibilidade** e não substitui a principal.
- **Guardar:** `accessibility.household_access(snapshot_id, place_id, category, distance_m,
  minutes_tobler)`.
- **Polígono:**
  - % dos domicílios dentro dos 15 min, por categoria e para **todas** ao mesmo tempo;
  - a diferença entre o plano e a variante com declividade.
- **Mapa:** a cor de cada domicílio agregada em grade de 100 m ("quantas das 6 categorias a 15 min").
- **CLI:** `quantumco accessibility build`, que roda depois de cada snapshot novo da rede.
- **Testes:** unitário do Dijkstra multiorigem e da função de Tobler; unitário num grafo de 5 nós com
  as distâncias conhecidas.

### A3. Sintaxe × crescimento

**Pergunta:** os eixos mais integrados hoje foram urbanizados antes?

- Cada trecho ganha o **ano de urbanização** (mediana do `mb_ano_urbano` das células a até 50 m).
- **Relatório offline** (`quantumco report growth`): Spearman ponderado por extensão entre NAIN (raio n
  e 2.000 m) e o ano de urbanização, mais um gráfico por década.
  - É exploratório: **não** é selo de validação.
  - Sai em `docs/reports/` com a release da análise e a coleção do MapBiomas.
- No mapa: a camada "idade da urbanização" (F6) ao lado da sintaxe já mostra a mesma coisa visualmente.

### A4. Validação comércio × sintaxe (já decidida, Q11/Q19/Q27)

Fica registrada aqui porque depende do F2.

- **CLI:** `quantumco report commerce`, com a densidade de empresas do grupo "dependente de passagem"
  (sem MEI) a até 30 m de cada trecho, por km, contra o NACH em 400 e 800 m.
- **Métrica pré-registrada:** Spearman ponderado por extensão.
- Sem zoneamento, sai como **exploratório**. A versão final compara dentro da mesma zona do Plano
  Diretor, quando o zoneamento chegar (§9).

## 7. Ordem e critérios de pronto

| Etapa | Entrega | Pronto quando |
|---|---|---|
| **0. Base** | grade de 30 m, `images`, `buildings`, rotas novas (o N7 do painel entra na etapa 1, com dado: não mostramos nível vazio) | migração aplicada na VPS; testes de db verdes; import-linter verde |
| **1. Forma e uso** | F1 prédios, F2 CNPJ + Places, F10 Censo | perfil do polígono com N7 e empresas; geocódigo ≥ 80%; mapa de prédios e densidade |
| **2. Cheia** | F3a histórico, A1 v1 (zonas do SGB) | o cenário "A cidade na cheia" roda pela fila e devolve as contagens |
| **3. Relevo e 15 min** | F4 MDT, F5 INEP, A2 | bloco "15 minutos" no N5, com a variante de declividade |
| **4. Satélite** | F6 MapBiomas, F7 verde e calor, A3 | imagens no mapa; relatório de crescimento em `docs/reports/` |
| **5. Resto** | F8 obras, F9 CAR, A1 v2 (HAND), F3b nível do rio | cada um com o seu critério acima |

Cada etapa:

- atualiza `docs/data-sources.md` (fonte, licença com o texto exato, data e registros);
- grava as decisões tomadas em `docs/decisions.md`;
- **precisa de Deploy manual do backend no Easypanel**.

## 8. Custos de operação (estimativa)

| Item | Tamanho | Observação |
|---|---|---|
| Grade (429.516 células) | 62 MB (tabela + índice); criada em ~16 s na 1ª camada raster | medido em 2026-11-06 com os 206 setores reais |
| Valores da grade × ~9 camadas | ~51 MB por camada → ~460 MB | medido; se apertar, guardar a camada como `smallint` ou em tabela larga |
| Prédios | dezenas de milhares | depende do F1 |
| Download do CNPJ | ~5 GB por mês, lido em fluxo | só na máquina que importa, não no servidor da API |
| MDT do SIGSC | ~280 km² a 1 m | processado em blocos; só o derivado sobe |
| A2 (15 min) | 65 mil domicílios × 6 categorias | Dijkstra multiorigem leva segundos; ~400 mil linhas |

## 9. Pendências fora do código

1. **LAI à prefeitura (GeoBrusque/SEPLAN):** zoneamento da LC 419/2024 em formato geográfico, lotes e
   ITBI (só para validação). Plano B para o zoneamento: georreferenciar os mapas em PDF anexos à lei
   (decidir à parte, porque é trabalho manual e precisa de conferência).
2. Confirmar a licença do CNPJ da Receita.
3. Confirmar com a SDE/SC que imagens em classes a 30 m derivadas do MDT estão dentro do "acesso livre".

## 10. Checklist do que verificar antes de codar cada fonte

- [ ] F1: a cobertura do Overture em Brusque e o release.
- [ ] F2: a licença da Receita; a taxa de acerto do geocódigo numa amostra de 200; a cobertura do Places.
- [ ] F3: o arquivo do Atlas de Desastres; a estação e a API da ANA.
- [ ] F4: limites e tempo do WCS do SIGSC.
- [ ] F5: a coordenada no Catálogo do INEP; a edição mais recente do IDEB.
- [ ] F6: a URL da Coleção 10 e o código da classe urbana.
- [ ] F7: o número de cenas sem nuvem por verão.
- [ ] F8: se há geometria nas obras de Brusque.
- [ ] F9: a data e a cobertura do arquivo do CAR.
- [ ] F10: os códigos `V…` no dicionário do IBGE.
