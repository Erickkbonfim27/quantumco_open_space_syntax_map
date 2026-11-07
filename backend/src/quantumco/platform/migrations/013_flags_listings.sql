-- Feature flags e imóveis à venda (docs/adr/0003-imoveis-a-venda.md).
--
-- Idempotente de propósito: o `sync-homolog` só recria os schemas que a produção tem, então a
-- homologação pode já ter estas tabelas de um teste anterior sem a linha em schema_migrations.

-- ---------------------------------------------------------------- feature flags
-- Nome ausente = desligada. Ligar/desligar: `quantumco flags ligar|desligar <nome>`.
create table if not exists public.feature_flags (
    name         text primary key check (name ~ '^[a-z0-9_]+$'),
    enabled      boolean not null default false,
    description  text not null default '',
    updated_at   timestamptz not null default now()
);

insert into public.feature_flags (name, enabled, description)
values (
    'listings_glue_api',
    false,
    'Imóveis à venda pela glue-api do Grupo OLX (ZAP/Viva Real). API interna, não documentada: em validação.'
)
on conflict (name) do nothing;

-- ---------------------------------------------------------------- imóveis à venda
create schema if not exists listings;

-- Estado ATUAL: uma linha por anúncio (chave natural). O mapa lê só daqui.
-- Sem contato, nome de anunciante, texto ou foto (LGPD e direito autoral).
-- fillfactor 85: last_seen_at/last_run_id mudam a cada carga e não têm índice, então a
-- atualização cabe no mesmo bloco (HOT) e não mexe nos índices.
create table if not exists listings.sale_listings (
    source             text not null,               -- provedor: 'grupo-olx'
    listing_id         text not null,               -- id do anúncio no provedor
    ibge_code          text not null check (ibge_code ~ '^[0-9]{7}$'),
    portal             text,                        -- onde foi visto por último: zap | vivareal
    property_type      text,                        -- APARTMENT, HOME, ...
    usage_type         text,                        -- RESIDENTIAL, COMMERCIAL
    usable_area_m2     double precision,
    total_area_m2      double precision,
    bedrooms           smallint,
    bathrooms          smallint,
    suites             smallint,
    parking_spaces     smallint,
    price_brl          numeric(14, 2),
    condo_fee_brl      numeric(12, 2),
    iptu_brl           numeric(12, 2),
    neighborhood       text,
    street             text,
    address_precision  text,                        -- ALL | STREET | NEIGHBORHOOD
    geom               geometry(Point, 4326),       -- só com o endereço completo à mostra
    url                text,
    content_hash       text not null,               -- impressão digital dos fatos
    first_seen_at      timestamptz not null default now(),
    last_seen_at       timestamptz not null default now(),
    last_changed_at    timestamptz not null default now(),
    last_run_id        bigint not null,
    removed_at         timestamptz,                 -- sumiu de uma carga COMPLETA; nada é apagado
    primary key (source, listing_id)
) with (fillfactor = 85);

-- mapa: só os ativos com ponto, por caixa (bbox ou tile)
create index if not exists sale_listings_active_geom on listings.sale_listings
    using gist (geom) where removed_at is null and geom is not null;
-- painel: filtros por cidade e tipo, só os ativos
create index if not exists sale_listings_active_city on listings.sale_listings
    (ibge_code, property_type) where removed_at is null;

-- HISTÓRICO (só insere): uma versão a cada mudança real da impressão digital.
create table if not exists listings.sale_listing_versions (
    source        text not null,
    listing_id    text not null,
    valid_from    timestamptz not null,
    run_id        bigint not null,
    content_hash  text not null,
    facts         jsonb not null,
    primary key (source, listing_id, valid_from)
);
create index if not exists sale_listing_versions_when on listings.sale_listing_versions
    using brin (valid_from);

-- QUARENTENA: o que veio com dado inválido não sobrescreve a última versão boa.
create table if not exists listings.rejected (
    run_id       bigint not null,
    source       text not null,
    listing_id   text not null,
    reasons      text[] not null,
    facts        jsonb not null,
    rejected_at  timestamptz not null default now(),
    primary key (run_id, source, listing_id)
);

-- CARGAS: etapas, tempos e tentativas desde a primeira versão.
create table if not exists listings.import_runs (
    run_id       bigserial primary key,
    ibge_code    text not null check (ibge_code ~ '^[0-9]{7}$'),
    source       text not null,
    started_at   timestamptz not null default now(),
    finished_at  timestamptz,
    status       text not null default 'rodando'
                 check (status in ('rodando', 'ok', 'bloqueado', 'erro')),
    complete     boolean not null default false,    -- percorreu tudo o que a fonte disse ter
    pages        integer not null default 0,
    received     integer not null default 0,
    new          integer not null default 0,
    changed      integer not null default 0,
    unchanged    integer not null default 0,
    rejected     integer not null default 0,
    removed      integer not null default 0,
    located      integer not null default 0,
    attempts     integer not null default 0,
    total        integer,                           -- quantos a fonte diz ter para a busca
    detail       text not null default ''
);
-- uma carga por vez por fonte e cidade
create unique index if not exists import_runs_one_active on listings.import_runs
    (source, ibge_code) where status = 'rodando';
