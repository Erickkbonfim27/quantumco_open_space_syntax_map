-- Várias cidades (docs/adr/0002-multi-cidade.md). Cada município entra pelo cadastro
-- road_network.study_areas (código IBGE + relação OSM, nunca pelo nome, Q14) e todo dado servido
-- passa a carregar o código IBGE: "atual" vale por cidade e importar uma cidade não toca nas outras.
-- Os dados que já existiam são de Brusque (4202909).
--
-- Ordem segura na produção: migrar ANTES do deploy. Por isso cenários, cálculos e cenários do
-- laboratório mantêm o padrão '4202909' enquanto o código antigo (que não manda a cidade) estiver
-- no ar; uma migração futura tira esses padrões.

-- ---------------------------------------------------------------- cadastro
create table road_network.study_areas (
    ibge_code        text primary key check (ibge_code ~ '^[0-9]{7}$'),
    name             text not null,
    uf               text not null check (uf ~ '^[A-Z]{2}$'),
    slug             text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    osm_relation_id  bigint not null check (osm_relation_id > 0),
    buffer_m         double precision not null check (buffer_m >= 0),
    crs_epsg         integer not null,
    status           text not null default 'preparando'
                     check (status in ('preparando', 'publicada')),
    created_at       timestamptz not null default now(),
    unique (uf, slug)
);

insert into road_network.study_areas
    (ibge_code, name, uf, slug, osm_relation_id, buffer_m, crs_epsg, status)
values ('4202909', 'Brusque', 'SC', 'brusque', 296588, 7000, 31982, 'publicada');

-- ---------------------------------------------------------------- Rede Viária
alter table road_network.snapshots add column ibge_code text;
update road_network.snapshots
   set ibge_code = coalesce(manifest -> 'study_area' ->> 'ibge_code', '4202909');
alter table road_network.snapshots
    alter column ibge_code set not null,
    add foreign key (ibge_code) references road_network.study_areas;
drop index road_network.snapshots_one_current;
-- no máximo um snapshot publicado POR CIDADE
create unique index snapshots_one_current on road_network.snapshots (ibge_code) where is_current;

-- ---------------------------------------------------------------- Análise Sintática
alter table syntax_analysis.analyses add column ibge_code text;
update syntax_analysis.analyses a
   set ibge_code = s.ibge_code
  from road_network.snapshots s
 where s.snapshot_id = a.snapshot_id;
update syntax_analysis.analyses set ibge_code = '4202909' where ibge_code is null;
alter table syntax_analysis.analyses
    alter column ibge_code set not null,
    add check (ibge_code ~ '^[0-9]{7}$');
drop index syntax_analysis.analyses_one_current;
create unique index analyses_one_current on syntax_analysis.analyses (ibge_code) where is_current;

alter table syntax_analysis.scenarios add column ibge_code text not null default '4202909';
update syntax_analysis.scenarios c
   set ibge_code = a.ibge_code
  from syntax_analysis.analyses a
 where a.analysis_id = c.base_analysis_id;

-- ---------------------------------------------------------------- Cenários do usuário
alter table scenarios.workspaces add column ibge_code text not null default '4202909'
    check (ibge_code ~ '^[0-9]{7}$');

alter table scenarios.runs add column ibge_code text not null default '4202909';
update scenarios.runs r
   set ibge_code = w.ibge_code
  from scenarios.workspaces w
 where w.workspace_id = r.workspace_id;

-- ---------------------------------------------------------------- Território
alter table territory.layers add column ibge_code text not null default '4202909';
alter table territory.layers
    alter column ibge_code drop default,
    drop constraint layers_pkey,
    add primary key (ibge_code, layer);

-- CD_SETOR já é único no país e começa pelo código do município
alter table territory.tracts add column ibge_code text generated always as (left(code, 7)) stored;
create index tracts_city on territory.tracts (ibge_code);

alter table territory.zones add column ibge_code text not null default '4202909';
alter table territory.zones alter column ibge_code drop default;
create index zones_city_layer on territory.zones (ibge_code, layer);

alter table territory.places add column ibge_code text not null default '4202909';
alter table territory.places alter column ibge_code drop default;
create index places_city_layer on territory.places (ibge_code, layer, kind);

alter table territory.addresses add column ibge_code text not null default '4202909';
alter table territory.addresses alter column ibge_code drop default;
create index addresses_city on territory.addresses (ibge_code);

-- a mesma edificação pode estar no recorte de duas cidades vizinhas
alter table territory.buildings add column ibge_code text not null default '4202909';
alter table territory.buildings
    alter column ibge_code drop default,
    drop constraint buildings_pkey,
    add primary key (ibge_code, building_id);
create index buildings_city on territory.buildings (ibge_code);

-- grade de 30 m: uma por cidade; a de Brusque é a de territory/domain/grid.py (BRUSQUE_GRID)
create table territory.grids (
    ibge_code  text primary key check (ibge_code ~ '^[0-9]{7}$'),
    west       double precision not null,
    north      double precision not null,
    size       double precision not null check (size > 0),
    ncols      integer not null check (ncols > 0),
    nrows      integer not null check (nrows > 0)
);
insert into territory.grids (ibge_code, west, north, size, ncols, nrows)
values ('4202909', 694590, 7013010, 30, 854, 1012);

alter table territory.grid_values drop constraint grid_values_cell_fkey;
alter table territory.grid add column ibge_code text not null default '4202909';
alter table territory.grid
    alter column ibge_code drop default,
    drop constraint grid_pkey,
    add primary key (ibge_code, cell);
alter table territory.grid_values add column ibge_code text not null default '4202909';
alter table territory.grid_values
    alter column ibge_code drop default,
    drop constraint grid_values_pkey,
    add primary key (ibge_code, layer, cell),
    add foreign key (ibge_code, cell) references territory.grid (ibge_code, cell);

alter table territory.images add column ibge_code text not null default '4202909';
alter table territory.images
    alter column ibge_code drop default,
    drop constraint images_pkey,
    add primary key (ibge_code, layer);
