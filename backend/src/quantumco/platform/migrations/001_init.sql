-- quantumco: um schema por contexto delimitado (DDD). Coordenadas em SIRGAS 2000 / UTM 22S.
create extension if not exists postgis;

create schema if not exists road_network;
create schema if not exists syntax_analysis;

-- ---------------------------------------------------------------- Rede Viária
create table road_network.snapshots (
    snapshot_id          uuid primary key,
    name                 text not null unique,
    osm_base_timestamp   timestamptz not null,
    created_at           timestamptz not null,
    methodology_version  text not null,
    filter_version       text not null,
    manifest             jsonb not null,
    municipality         geometry(Geometry, 31982) not null,
    is_current           boolean not null default false
);
-- no máximo um snapshot publicado
create unique index snapshots_one_current on road_network.snapshots (is_current) where is_current;

create table road_network.links (
    snapshot_id  uuid not null references road_network.snapshots on delete cascade,
    link_id      text not null,
    osm_way_id   bigint not null,
    from_node    bigint not null,
    to_node      bigint not null,
    highway      text not null,
    zone         text not null check (zone in ('result', 'buffer')),
    is_bridge    boolean not null,
    is_tunnel    boolean not null,
    excluded     boolean not null,       -- fora do maior componente conectado (Q44)
    length_m     double precision not null,
    geom         geometry(LineString, 31982) not null,
    primary key (snapshot_id, link_id)
);
create index links_geom_gist on road_network.links using gist (geom);

-- Contrato publicado para os outros contextos: só os trechos analisáveis.
create view road_network.published_links as
    select snapshot_id, link_id, osm_way_id, highway, zone, is_bridge, is_tunnel, length_m, geom
    from road_network.links
    where not excluded;

-- ---------------------------------------------------------------- Análise Sintática
create table syntax_analysis.analyses (
    analysis_id  uuid primary key,
    snapshot_id  uuid not null,          -- referência lógica a road_network (outro contexto)
    name         text not null unique,
    created_at   timestamptz not null,
    manifest     jsonb not null,
    is_current   boolean not null default false
);
create unique index analyses_one_current on syntax_analysis.analyses (is_current) where is_current;

create table syntax_analysis.link_measures (
    analysis_id  uuid not null references syntax_analysis.analyses on delete cascade,
    link_id      text not null,
    measures     jsonb not null,         -- {"nain_n": 0.21, "c_nain_n": 6, ...}
    primary key (analysis_id, link_id)
);
