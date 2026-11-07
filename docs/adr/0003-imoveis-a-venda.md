# ADR 0003: Imóveis à venda no nosso banco, com carga idempotente

Data: 2026-11-06 · Status: **aceito, em validação** (atrás da flag `listings_glue_api`)

## Contexto

O dono quer os imóveis à venda como pontos no mapa, cruzados com a sintaxe e o perfil do
polígono. Os portais não servem o mapa direto: cada carga traz o retrato do momento, e o mapa
precisa de um estado estável, rápido de consultar e com histórico. A tabela vai crescer muito:
milhares de anúncios por cidade, cargas frequentes e, com mais cidades, milhões de linhas.

A primeira fonte é a glue-api do Grupo OLX (a API que os sites ZAP Imóveis e Viva Real usam).
Ela **não é pública nem documentada**. Em 06/11/2026, um pedido identificado como quantumco
recebeu **HTTP 403 do Cloudflare**. Por isso a fonte fica atrás de uma feature flag, desligada
por padrão, e serve só a uma **prova de conceito pessoal, sem redistribuir os dados**.

O User-Agent padrão identifica a quantumco. Por decisão do dono, `QC_LISTINGS_USER_AGENT` (no
`.env`, fora do repositório) troca esse valor. Os pedidos saem como o data_imob fazia: biblioteca
`requests` e os mesmos cabeçalhos. Teste de 06/11/2026, com os mesmos cabeçalhos e a mesma busca
(Brusque): `requests` recebeu 200 (2.831 anúncios) e `httpx` recebeu 403 do Cloudflare. O
adaptador não vai além disso: não imita a conexão de um navegador, não usa navegador automatizado
nem proxies, não resolve desafios e não insiste depois de um 403. Outras fontes entram depois pela
mesma porta (`ListingSource`).

Esta decisão muda a regra "anúncios fora do escopo" da spec da fase B. O preço passa a ser
guardado e, por decisão do dono (07/11/2026), **aparece na janela do pino** nesta prova de
conceito, só para quem está logado (a regra "não mede preço", Q27, segue valendo para o resto do site).

## Decisão

### 1. Quatro tabelas no schema `listings` (migração 013)

| Tabela | Papel | Cresce |
|---|---|---|
| `sale_listings` | **Estado atual**: uma linha por anúncio. O mapa lê só daqui. | com o nº de anúncios |
| `sale_listing_versions` | **Histórico** (só insere): uma linha a cada mudança real do anúncio | com as mudanças |
| `rejected` | **Quarentena**: o que veio com dado inválido, com o motivo | com os erros da fonte |
| `import_runs` | Uma linha por carga: páginas, tentativas, novos, mudados, removidos, tempo | 1 por carga |

E `public.feature_flags` (nome, ligada, descrição), lida a cada carga, sem cache.

### 2. Chave e impressão digital

- **Chave natural** `(source, listing_id)`: o provedor (`grupo-olx`) e o id do anúncio nele. É a
  chave primária, então duplicar é impossível. O portal (ZAP ou Viva Real) e o link ficam como
  atributos, não na chave.
- **Impressão digital** (`content_hash`): sha256 dos fatos do anúncio em JSON canônico (chaves
  ordenadas, números arredondados). Portal e link ficam de fora, porque mudam sem o imóvel mudar.
  É calculada no domínio (`SaleListing.fingerprint()`), sem I/O.

### 3. Upsert idempotente, página por página

Cada página é uma transação:

1. **Validar no domínio** (`problems()`): cidade diferente da busca, preço ou área fora da faixa,
   cômodos impossíveis, coordenada fora do Brasil ou pela metade. O que falha vai para a
   **quarentena** e **não toca** a linha boa que já temos. Só atualiza "visto agora".
2. **Staging**: `COPY` para uma tabela temporária; repetidos dentro da página ficam só uma vez.
3. **Contar** novos, mudados e iguais comparando a impressão digital com o estado atual.
4. **Histórico**: insere uma versão só para quem é novo ou mudou de impressão digital.
5. **Estado atual**: `INSERT … ON CONFLICT (source, listing_id) DO UPDATE`. Atualiza os fatos,
   `last_seen_at` e `last_run_id`. `last_changed_at` só muda se a impressão digital mudou.
   Quem reaparece volta a ficar ativo (`removed_at = null`).

**Remoção só depois de uma carga completa.** Ao fim de uma carga que percorreu tudo o que a fonte
disse ter, quem não foi visto ganha `removed_at`. Nada é apagado. Carga bloqueada, com erro ou
cortada pelo limite de páginas **não remove ninguém**.

Rodar a mesma carga duas vezes dá o mesmo estado: zero novos, zero mudados, zero versões novas.

**Uma carga por vez** por fonte e cidade, garantido por um índice único parcial em `import_runs`
(`where status = 'rodando'`). Uma carga presa há mais de 6 h é dada como abandonada.

### 4. Índices estratégicos

| Índice | Para quê |
|---|---|
| PK `(source, listing_id)` | o upsert (conflito) e a busca de um anúncio |
| GiST parcial em `geom`, `where removed_at is null and geom is not null` | o mapa: só os ativos com ponto, por caixa (bbox ou tile) |
| B-tree parcial `(ibge_code, property_type)`, `where removed_at is null` | filtros do painel por cidade e tipo |
| PK `(source, listing_id, valid_from)` em `sale_listing_versions` | a linha do tempo de um anúncio |
| BRIN em `sale_listing_versions.valid_from` | análises por período sem índice grande (a tabela só cresce no tempo) |

`last_seen_at` e `last_run_id` mudam em toda carga e **não têm índice**. Com `fillfactor = 85`,
o Postgres consegue fazer essas atualizações no mesmo bloco (HOT), sem mexer nos índices. É isso
que deixa a carga barata quando quase nada mudou.

### 5. Servir o mapa

O mapa lê só de `sale_listings`, só ativos (`removed_at is null`), pelo índice GiST parcial. Por
enquanto, GeoJSON por caixa visível, com limite. Quando passar de dezenas de milhares de pontos
por cidade, o mesmo índice serve tiles vetoriais (`ST_AsMVT`) sem mudar a tabela.

### 6. Várias cidades (ADR 0002)

A cidade é sempre o **código IBGE** do cadastro (`road_network.study_areas`). O comando
`quantumco imoveis importar --cidade 4208302` pega no cadastro o nome, a UF e o retângulo do
município, que serve para recusar ponto fora da cidade (com 1 km de folga). Cidade fora do
cadastro não importa. `ibge_code` está em todas as linhas, e as cargas são por fonte e cidade.

### 7. Privacidade e direitos

Só fatos do imóvel. Contato, nome do anunciante, telefone, WhatsApp e texto **não são lidos nem
guardados** (LGPD e direito autoral). Das fotos, guarda-se só o **link da capa** (`photo_url`,
migração 014), para a janela do mapa: a imagem não é copiada e continua no servidor do portal. O
link fica fora da impressão digital. O ponto só é guardado quando o anunciante mostra
o endereço completo (`displayAddressType = ALL`). Com "só a rua", fica a rua; com "só o bairro",
fica o bairro.

### 8. PostGIS ou ClickHouse

| Parte | Onde | Por quê |
|---|---|---|
| Estado atual (`sale_listings`) | **PostGIS** | O mapa precisa de índice espacial (GiST), tiles (`ST_AsMVT`) e upsert linha a linha com `ON CONFLICT`. No ClickHouse, a deduplicação (`ReplacingMergeTree`) só acontece depois, em segundo plano, e cada consulta teria de usar `FINAL` ou `argMax`. Marcar removido vira uma mutação pesada. |
| Histórico e análises de preço e estoque | **PostGIS agora, ClickHouse depois** | Para Brusque são milhares de linhas, e o PostGIS dá conta. Quando houver várias cidades, as versões vão para o ClickHouse que já existe (ADR 0001), numa `ReplacingMergeTree` com chave `(source, listing_id, content_hash)`: inserir a mesma versão de novo não duplica. O caminho é o mesmo do CNPJ: tratado no ClickHouse, recorte para o mapa no PostGIS. |

Gatilho para mover o histórico: passar de ~5 milhões de versões, ou as consultas de série de
preço por cidade ficarem lentas.

## Consequências

- O mapa fica independente da fonte: se a fonte cair, o mapa continua com o último estado.
- A tabela de versões guarda a evolução do preço e do estoque, base para análises futuras.
- A quarentena mostra a qualidade da fonte, e um dado ruim nunca apaga um dado bom.
- Particionar `sale_listings` por UF fica para quando passar de ~10 milhões de linhas.

## Pendências

1. **Acesso à fonte**: com cliente identificado, a glue-api respondeu 403. Sem acesso autorizado,
   a flag fica desligada.
2. Confirmar se o mesmo anúncio tem o mesmo id no ZAP e no Viva Real. Se tiver, a chave já evita
   o ponto duplicado. Se não tiver, falta deduplicar por endereço, área e tipo.
3. Pinos só para anúncios com o endereço completo (1.228 de 2.830 em Brusque). Os que mostram só o
   bairro poderiam ir para o centro do bairro, marcados como aproximados.
4. Feito em 07/11: rota `/cities/{ibge}/listings` (login + flag) e camada de pinos (casa ou prédio)
   com janela de foto, dados, valores e link, só no mapa do cenário.
