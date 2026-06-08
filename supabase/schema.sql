-- GitMine Pool — Supabase Schema
-- Run this in your Supabase SQL editor (Database → SQL Editor → New query)

-- ─── Users ────────────────────────────────────────────────────────────────────
-- Mirrors GitHub identity. Created/upserted on first dashboard login.
create table if not exists users (
  id           uuid primary key default gen_random_uuid(),
  github_id    bigint unique not null,
  github_login text unique not null,   -- e.g. "5mil"
  avatar_url   text,
  created_at   timestamptz default now(),
  last_seen_at timestamptz default now()
);

-- ─── Workers ──────────────────────────────────────────────────────────────────
-- One row per username.suffix the miner uses as their Stratum username.
-- worker_name must start with the owner's github_login.
create table if not exists workers (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references users(id) on delete cascade,
  worker_name text unique not null,   -- e.g. "5mil.gitmine", "5mil.asic01"
  coin        text not null default 'FNNC', -- 'FNNC' | 'TTY'
  enabled     boolean not null default true,
  created_at  timestamptz default now(),

  -- Enforce format: worker_name must start with github_login + '.'
  constraint worker_name_prefix check (worker_name like '%' || '.' || '%')
);

create index if not exists workers_user_id_idx on workers(user_id);
create index if not exists workers_name_idx    on workers(worker_name);

-- ─── Shares ───────────────────────────────────────────────────────────────────
create table if not exists shares (
  id          bigserial primary key,
  worker_id   uuid not null references workers(id) on delete cascade,
  worker_name text not null,  -- denormalized for fast pool-side inserts
  coin        text not null,
  algo        text not null,  -- 'yescryptr16' | 'sha256d'
  difficulty  numeric not null,
  accepted    boolean not null default true,
  block_height bigint,
  submitted_at timestamptz default now()
);

create index if not exists shares_worker_id_idx  on shares(worker_id);
create index if not exists shares_submitted_idx  on shares(submitted_at desc);
create index if not exists shares_coin_idx       on shares(coin);

-- ─── Balances ─────────────────────────────────────────────────────────────────
create table if not exists balances (
  id       uuid primary key default gen_random_uuid(),
  user_id  uuid not null references users(id) on delete cascade,
  coin     text not null,
  amount   numeric(20, 8) not null default 0,
  unique(user_id, coin)
);

-- ─── Payouts ──────────────────────────────────────────────────────────────────
create table if not exists payouts (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references users(id) on delete cascade,
  coin       text not null,
  amount     numeric(20, 8) not null,
  address    text not null,   -- on-chain payout address
  txid       text,
  status     text not null default 'pending', -- 'pending' | 'broadcast' | 'confirmed'
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ─── Pool stats (materialised snapshot, updated by Actions cron) ──────────────
create table if not exists pool_stats (
  id             bigserial primary key,
  coin           text not null,
  total_shares   bigint not null default 0,
  hashrate_mhs   numeric(16,4) not null default 0,
  active_workers int not null default 0,
  block_height   bigint,
  template_algo  text,
  snapshot_at    timestamptz default now()
);

-- ─── Row Level Security ───────────────────────────────────────────────────────
-- Users can only read/update their own rows.
alter table users    enable row level security;
alter table workers  enable row level security;
alter table shares   enable row level security;
alter table balances enable row level security;
alter table payouts  enable row level security;
alter table pool_stats enable row level security;

-- pool_stats is public-read (anyone can see pool overview)
create policy "pool_stats public read"
  on pool_stats for select using (true);

-- users: only own row
create policy "users own row read"   on users for select using (auth.uid()::text = id::text);
create policy "users own row update" on users for update using (auth.uid()::text = id::text);

-- workers: own rows only
create policy "workers own read"   on workers for select using (
  user_id in (select id from users where id::text = auth.uid()::text)
);
create policy "workers own insert" on workers for insert with check (
  user_id in (select id from users where id::text = auth.uid()::text)
);
create policy "workers own update" on workers for update using (
  user_id in (select id from users where id::text = auth.uid()::text)
);
create policy "workers own delete" on workers for delete using (
  user_id in (select id from users where id::text = auth.uid()::text)
);

-- shares: own reads (pool server writes via service_role key)
create policy "shares own read" on shares for select using (
  worker_id in (select id from workers where user_id::text = auth.uid()::text)
);

-- balances/payouts: own rows
create policy "balances own read" on balances for select using (
  user_id::text = auth.uid()::text
);
create policy "payouts own read" on payouts for select using (
  user_id::text = auth.uid()::text
);

-- ─── Worker resolution helper function ───────────────────────────────────────
-- Called by the pool/relay with just the Stratum username.
-- Returns the resolved user + worker row, auto-creating them if needed.
-- Runs with SECURITY DEFINER so it bypasses RLS (pool uses service_role key anyway).
create or replace function resolve_worker(
  p_worker_name  text,
  p_github_login text default null,
  p_github_id    bigint default null,
  p_avatar_url   text default null,
  p_coin         text default 'FNNC'
)
returns table (
  user_id     uuid,
  worker_id   uuid,
  worker_name text,
  coin        text,
  enabled     boolean
)
language plpgsql security definer as $$
declare
  v_prefix      text;
  v_user_id     uuid;
  v_worker_id   uuid;
begin
  -- Extract prefix (everything before first '.')
  v_prefix := split_part(p_worker_name, '.', 1);

  -- Upsert user by github_login (prefix) if github info provided
  -- Otherwise look up by login = prefix
  if p_github_login is not null and p_github_id is not null then
    insert into users (github_id, github_login, avatar_url, last_seen_at)
    values (p_github_id, p_github_login, p_avatar_url, now())
    on conflict (github_login) do update
      set last_seen_at = now(),
          avatar_url   = coalesce(excluded.avatar_url, users.avatar_url)
    returning id into v_user_id;
  else
    select id into v_user_id from users where github_login = v_prefix;
  end if;

  if v_user_id is null then
    -- Unknown prefix — reject
    return;
  end if;

  -- Upsert worker
  insert into workers (user_id, worker_name, coin)
  values (v_user_id, p_worker_name, p_coin)
  on conflict (worker_name) do update
    set coin = excluded.coin
  returning id into v_worker_id;

  return query
    select v_user_id, v_worker_id, p_worker_name, p_coin, true;
end;
$$;
