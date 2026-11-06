-- Fase B das camadas territoriais (docs/specs/camadas-fase-b.md, §4).
--
-- 1. Grade fixa de 30 m (SIRGAS 2000 / UTM 22S) para dados raster: MDT, MapBiomas, Sentinel, Landsat.
--    O id da célula vem da grade definida em territory/domain/grid.py (linha * colunas + coluna);
--    só existem as células a até 1 km do município, criadas na primeira gravação de uma camada.
-- 2. Imagens prontas para o mapa (PNG colorido, gerado na importação).
-- 3. Edificações (Overture buildings), em tabela própria.

create table territory.grid (
    cell  bigint primary key,
    geom  geometry(Point, 31982) not null       -- centro da célula
);
create index grid_geom on territory.grid using gist (geom);

create table territory.grid_values (
    layer  text   not null,                     -- declividade, ndvi, lst, mb_classe, mb_ano_urbano…
    cell   bigint not null references territory.grid (cell),
    value  real   not null,
    primary key (layer, cell)
);

create table territory.images (
    layer   text primary key,
    png     bytea not null,
    bounds  double precision[] not null,        -- oeste, sul, leste, norte (WGS84)
    legend  jsonb not null default '[]',
    check (cardinality(bounds) = 4)
);

create table territory.buildings (
    building_id  text primary key,              -- id do Overture
    source       text not null,                 -- OpenStreetMap, Microsoft ML Buildings, Google Open Buildings…
    height_m     real,
    floors       smallint,
    class        text,
    area_m2      real not null,
    geom         geometry(MultiPolygon, 31982) not null
);
create index buildings_geom on territory.buildings using gist (geom);
