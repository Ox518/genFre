/**
 * GitMine Dashboard — Supabase integration
 *
 * Loaded by index.html after GitHub Device Flow login.
 * Handles:
 *   - Upsert user + default worker into Supabase on first login
 *   - Load/save worker names per user
 *   - Live stats from Supabase (shares, balance, last share)
 *
 * Required env (injected by index.html as window.GITMINE_CONFIG):
 *   SUPABASE_URL, SUPABASE_ANON_KEY
 *
 * The anon key is safe to expose in the browser — RLS policies
 * enforce that each user can only see their own rows.
 */

const { createClient } = window.supabase; // loaded from CDN

let _sb = null;
function sb() {
  if (!_sb) {
    const { SUPABASE_URL, SUPABASE_ANON_KEY } = window.GITMINE_CONFIG || {};
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) return null;
    _sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return _sb;
}

/**
 * Called right after GitHub Device Flow succeeds.
 * Creates or updates the user + default worker in Supabase.
 *
 * @param {object} ghUser   - GitHub /user API response
 * @param {string} ghToken  - GitHub OAuth access token (used to verify identity)
 */
export async function onGitHubLogin(ghUser, ghToken) {
  const client = sb();
  if (!client) return; // Supabase not configured — graceful degradation

  // Exchange the GitHub token for a Supabase session using the custom
  // GitHub provider sign-in (requires Supabase GitHub OAuth configured,
  // OR use signInWithPassword with github_id as a stable identifier).
  //
  // Because we used Device Flow (not a redirect), we pass the GitHub
  // access token directly to Supabase's signInWithOAuth isn't applicable.
  // Instead we call a Supabase Edge Function that validates the token
  // with GitHub and returns a Supabase JWT.
  try {
    const resp = await fetch(
      `${window.GITMINE_CONFIG.SUPABASE_URL}/functions/v1/github-login`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ github_token: ghToken }),
      }
    );
    if (!resp.ok) throw new Error('github-login function failed');
    const { access_token, refresh_token } = await resp.json();
    await client.auth.setSession({ access_token, refresh_token });
  } catch (e) {
    console.warn('[gitmine] Supabase login skipped:', e.message);
    return;
  }

  // Upsert user row
  await client.from('users').upsert({
    github_id:    ghUser.id,
    github_login: ghUser.login,
    avatar_url:   ghUser.avatar_url,
    last_seen_at: new Date().toISOString(),
  }, { onConflict: 'github_login' });

  // Ensure default worker exists
  const defaultWorker = `${ghUser.login}.gitmine`;
  await ensureWorker(defaultWorker, 'FNNC');
}

/**
 * Ensure a worker row exists for this user. Creates if missing.
 */
export async function ensureWorker(workerName, coin = 'FNNC') {
  const client = sb();
  if (!client) return;
  const { data: existing } = await client
    .from('workers')
    .select('id')
    .eq('worker_name', workerName)
    .maybeSingle();
  if (!existing) {
    await client.from('workers').insert({ worker_name: workerName, coin });
  }
}

/**
 * Save a new worker name (user edited the suffix).
 * Old default worker is kept; new one is added.
 */
export async function saveWorker(workerName, coin = 'FNNC') {
  const client = sb();
  if (!client) return;
  await client.from('workers').upsert(
    { worker_name: workerName, coin },
    { onConflict: 'worker_name' }
  );
}

/**
 * Fetch this user's workers.
 */
export async function getMyWorkers() {
  const client = sb();
  if (!client) return [];
  const { data } = await client
    .from('workers')
    .select('worker_name, coin, created_at')
    .order('created_at', { ascending: true });
  return data || [];
}

/**
 * Fetch per-worker share counts and balance for the stats panel.
 */
export async function getMyStats() {
  const client = sb();
  if (!client) return null;

  const [{ data: shares }, { data: balances }] = await Promise.all([
    client
      .from('shares')
      .select('worker_name, coin, accepted, submitted_at')
      .order('submitted_at', { ascending: false })
      .limit(500),
    client
      .from('balances')
      .select('coin, amount'),
  ]);

  const stats = { workers: {}, balances: {}, last_share: null };

  for (const s of (shares || [])) {
    if (!stats.workers[s.worker_name]) {
      stats.workers[s.worker_name] = { total: 0, fnnc: 0, tty: 0 };
    }
    stats.workers[s.worker_name].total++;
    if (s.coin === 'FNNC') stats.workers[s.worker_name].fnnc++;
    if (s.coin === 'TTY')  stats.workers[s.worker_name].tty++;
    if (!stats.last_share) stats.last_share = s.submitted_at;
  }

  for (const b of (balances || [])) {
    stats.balances[b.coin] = b.amount;
  }

  return stats;
}

/**
 * Fetch pool-wide stats (public, no auth needed).
 */
export async function getPoolStats() {
  const client = sb();
  if (!client) return null;
  const { data } = await client
    .from('pool_stats')
    .select('*')
    .order('snapshot_at', { ascending: false })
    .limit(2);
  return data || [];
}

/**
 * Subscribe to real-time share inserts for the current user's workers.
 * Calls `onShare(row)` whenever a new accepted share arrives.
 */
export function subscribeShares(workerNames, onShare) {
  const client = sb();
  if (!client || !workerNames.length) return () => {};

  const channel = client
    .channel('my-shares')
    .on(
      'postgres_changes',
      {
        event:  'INSERT',
        schema: 'public',
        table:  'shares',
        filter: `worker_name=in.(${workerNames.map(w => `"${w}"`).join(',')})`,
      },
      payload => onShare(payload.new)
    )
    .subscribe();

  return () => client.removeChannel(channel);
}
