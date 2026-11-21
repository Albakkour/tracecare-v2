-- Rate-limit hits (serverless-safe rate limiting). `key` is a salted HMAC hash, never a raw IP address.
-- The backend also creates this table automatically on startup (CREATE TABLE IF NOT EXISTS).
create table if not exists public.rate_limit_hits (
    id          bigserial primary key,
    key         varchar(80) not null,
    created_at  double precision not null   -- unix epoch seconds
);
create index if not exists rate_limit_hits_key_idx on public.rate_limit_hits (key);
create index if not exists rate_limit_hits_created_at_idx on public.rate_limit_hits (created_at);

alter table public.rate_limit_hits enable row level security;
revoke all on table public.rate_limit_hits from anon, authenticated;

-- Encounters older than ENCOUNTER_RETENTION_DAYS (default 7) are deleted by the backend on each save.
