-- Perfil do usuário: foto (pequena, já reduzida no navegador) e preferências (tema, fundo do mapa).
alter table identity.users
    add column avatar             bytea,
    add column avatar_type        text check (avatar_type in ('image/webp', 'image/jpeg', 'image/png')),
    add column avatar_updated_at  timestamptz,
    add column preferences        jsonb not null default '{}'::jsonb,
    add column updated_at         timestamptz;
