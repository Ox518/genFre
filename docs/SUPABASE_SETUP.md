# Supabase Setup for GitMine Pool

## 1. Create a Supabase project

1. Go to [supabase.com](https://supabase.com) → New project
2. Note your **Project URL** and **anon public key** (Settings → API)
3. Also note the **service_role key** (keep secret — only used server-side)

## 2. Run the schema

In your Supabase dashboard → **SQL Editor → New query**, paste and run:

```
supabase/schema.sql
```

This creates: `users`, `workers`, `shares`, `balances`, `payouts`, `pool_stats`,
the `resolve_worker()` RPC function, and all RLS policies.

## 3. Deploy the Edge Function

```bash
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase functions deploy github-login
```

## 4. Configure the dashboard

In `docs/index.html`, find this block near the top of the `<script>` and fill in your values:

```js
window.GITMINE_CONFIG = {
  SUPABASE_URL:      'https://xxxx.supabase.co',
  SUPABASE_ANON_KEY: 'eyJ...',   // public anon key — safe to expose
};
```

The anon key is safe to commit. RLS policies ensure users can only read/write
their own rows. The service_role key is **never** in the frontend.

## 5. Configure the resolver (server-side)

Set environment variables wherever `relay/worker_resolver.py` runs:

```bash
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_KEY=eyJ...  # service_role key
```

Start the resolver:

```bash
pip install aiohttp supabase
python relay/worker_resolver.py --host 127.0.0.1 --port 8767
```

## 6. Wire your Stratum server to the resolver

When a miner connects with username `alice.rig1`, your Stratum server should:

```
POST http://127.0.0.1:8767/resolve
{ "worker_name": "alice.rig1", "coin": "FNNC" }
```

Response `200 {"ok": true, "user_id": "...", "worker_id": "...", "enabled": true}`
→ allow the connection.

Response `404 {"ok": false, "error": "unknown_prefix"}`
→ reject the connection (no GitHub account with that username).

When a share is accepted:

```
POST http://127.0.0.1:8767/share
{ "worker_name": "alice.rig1", "coin": "FNNC", "algo": "yescryptr16", "difficulty": 1.0 }
```

## 7. Real-time dashboard

The dashboard subscribes to Supabase Realtime on the `shares` table.
Whenever a share is inserted by the pool server, the miner's stats
update live without polling.

## Flow summary

```
miner (cgminer)  →  Stratum server  →  POST /resolve  →  Supabase
                                    →  POST /share    →  Supabase
                                                           ↓
                                               Realtime broadcast
                                                           ↓
                                               Dashboard updates live
```
