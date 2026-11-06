-- Cenários do usuário: edições da rede ("e se…") e a fila de cálculo (pedidos e etapas).
alter table scenarios.workspaces add column edits jsonb not null default '[]'::jsonb;

create table scenarios.runs (
    run_id        uuid primary key,
    workspace_id  uuid not null references scenarios.workspaces on delete cascade,
    owner_id      uuid not null,                  -- referência lógica a identity.users
    status        text not null check (status in ('queued', 'running', 'done', 'failed', 'canceled')),
    stage         text not null,
    stages        jsonb not null default '[]'::jsonb,  -- [{stage, at, seconds}]
    edits         jsonb not null,                 -- congeladas no pedido
    created_at    timestamptz not null,
    started_at    timestamptz,
    finished_at   timestamptz,
    heartbeat_at  timestamptz,
    attempts      integer not null default 0,
    worker        text,
    error         text,
    result        jsonb                           -- resumo (km que subiram/caíram, tempo do motor…)
);
create index runs_workspace on scenarios.runs (workspace_id, created_at desc);
create index runs_owner on scenarios.runs (owner_id, created_at desc);
create index runs_queued on scenarios.runs (created_at) where status = 'queued';
