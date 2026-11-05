-- Camadas territoriais (dados abertos): setores do IBGE, zonas do SGB, pontos do CNEFE e do CNES.
-- Geometria no CRS métrico da análise (SIRGAS 2000 / UTM 22S), para área e recorte exatos.
create schema if not exists territory;

create table territory.layers (
    layer       text primary key,              -- setores, cnefe, cnes, risco, suscet_*
    source      text not null,
    source_url  text not null,
    license     text not null,
    rows        integer not null,
    fetched_at  timestamptz not null,
    meta        jsonb not null default '{}'
);

create table territory.tracts (
    code     text primary key,                 -- CD_SETOR (15 dígitos)
    attrs    jsonb not null,
    area_m2  double precision not null,
    geom     geometry(MultiPolygon, 31982) not null
);
create index tracts_geom on territory.tracts using gist (geom);

create table territory.zones (
    zone_id   bigserial primary key,
    layer     text not null,
    category  text not null,                   -- grau de risco ou classe de suscetibilidade
    process   text not null,
    attrs     jsonb not null default '{}',
    area_m2   double precision not null,
    geom      geometry(MultiPolygon, 31982) not null
);
create index zones_layer on territory.zones (layer);
create index zones_geom on territory.zones using gist (geom);

create table territory.places (
    place_id    bigserial primary key,
    layer       text not null,
    kind        text not null,
    name        text,
    tract_code  text,
    attrs       jsonb not null default '{}',
    geom        geometry(Point, 31982) not null
);
create index places_layer_kind on territory.places (layer, kind);
create index places_tract on territory.places (tract_code) where layer = 'cnefe' and kind = 'domicilio';
create index places_geom on territory.places using gist (geom);
