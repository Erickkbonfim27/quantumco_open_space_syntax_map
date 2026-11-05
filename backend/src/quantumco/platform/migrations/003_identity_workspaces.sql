-- Identidade (usuários e sessões) e Cenários do usuário (espaços de trabalho com polígonos).
create schema if not exists identity;
create schema if not exists scenarios;

create table identity.users (
    user_id        uuid primary key,
    name           text not null,
    email          text not null unique,          -- normalizado em minúsculas
    organization   text,
    password_hash  text not null,                 -- Argon2id
    created_at     timestamptz not null,
    email_verified_at timestamptz
);

create table identity.sessions (
    token_hash  text primary key,                 -- sha256 do token do cookie (o token nunca é gravado)
    user_id     uuid not null references identity.users on delete cascade,
    created_at  timestamptz not null,
    expires_at  timestamptz not null
);
create index sessions_user on identity.sessions (user_id);

create table scenarios.workspaces (
    workspace_id  uuid primary key,
    owner_id      uuid not null,                  -- referência lógica a identity.users
    name          text not null,
    measure       text not null check (measure in ('nain', 'nach')),
    status        text not null check (status in ('rascunho', 'em_analise', 'publicado')),
    created_at    timestamptz not null,
    updated_at    timestamptz not null
);
create index workspaces_owner on scenarios.workspaces (owner_id, updated_at desc);

create table scenarios.polygons (
    polygon_id    uuid primary key,
    workspace_id  uuid not null references scenarios.workspaces on delete cascade,
    code          text not null,                  -- P-01, P-02… dentro do cenário
    name          text not null,
    geom          geometry(Polygon, 4326) not null,
    created_at    timestamptz not null,
    unique (workspace_id, code)
);
