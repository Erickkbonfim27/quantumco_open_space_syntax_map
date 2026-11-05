-- Cenários "e se…" (laboratório): edições sobre uma análise publicada e o resultado comparado.
create table syntax_analysis.scenarios (
    scenario_id       uuid primary key,
    name              text not null unique,
    base_analysis_id  uuid not null references syntax_analysis.analyses on delete cascade,
    snapshot_id       uuid not null,
    edits             jsonb not null,
    created_at        timestamptz not null,
    manifest          jsonb not null
);

create table syntax_analysis.scenario_link_measures (
    scenario_id  uuid not null references syntax_analysis.scenarios on delete cascade,
    link_id      text not null,
    measures     jsonb not null,   -- valores, classes (cortes da base) e deltas d_<medida>
    primary key (scenario_id, link_id)
);

create table syntax_analysis.scenario_new_links (
    scenario_id  uuid not null references syntax_analysis.scenarios on delete cascade,
    link_id      text not null,
    geom         geometry(LineString, 31982) not null,
    primary key (scenario_id, link_id)
);
