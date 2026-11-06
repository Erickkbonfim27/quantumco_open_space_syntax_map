-- Conta: foto no RustFS (o banco guarda só a chave), troca de e-mail pendente e links por e-mail.
alter table identity.users
    drop column if exists avatar,
    add column avatar_key     text,
    add column pending_email  text;

create table identity.email_tokens (
    token_hash  text primary key,                 -- sha256 do token do link (o token não é gravado)
    user_id     uuid not null references identity.users on delete cascade,
    purpose     text not null check (purpose in ('verify_email', 'change_email', 'reset_password')),
    new_email   text,                             -- só na troca de e-mail
    created_at  timestamptz not null,
    expires_at  timestamptz not null,
    used_at     timestamptz
);
create index email_tokens_user on identity.email_tokens (user_id, purpose, created_at desc);
