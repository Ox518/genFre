/**
 * Supabase Edge Function: github-login
 *
 * Accepts a GitHub OAuth access token from the browser (obtained via
 * GitHub Device Flow), validates it against the GitHub API, then creates
 * or signs in the corresponding Supabase user and returns a session.
 *
 * Deploy:
 *   supabase functions deploy github-login
 *
 * Env vars (set in Supabase dashboard → Edge Functions → Secrets):
 *   SUPABASE_URL          – your project URL (auto-available)
 *   SUPABASE_SERVICE_ROLE_KEY – service role key (auto-available)
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Headers': 'authorization, content-type',
};

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { github_token } = await req.json();
    if (!github_token) {
      return new Response(JSON.stringify({ error: 'missing github_token' }), {
        status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Validate token with GitHub
    const ghRes = await fetch('https://api.github.com/user', {
      headers: { Authorization: `token ${github_token}`, 'User-Agent': 'gitmine-pool' },
    });
    if (!ghRes.ok) {
      return new Response(JSON.stringify({ error: 'invalid_github_token' }), {
        status: 401, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    const ghUser = await ghRes.json();

    // Build a stable fake email from github_id (avoids real email scope)
    const fakeEmail = `${ghUser.id}+${ghUser.login}@github.gitmine`;

    const admin = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
      { auth: { autoRefreshToken: false, persistSession: false } }
    );

    // Create or retrieve the Supabase auth user
    let userId: string;
    const { data: existing } = await admin.auth.admin.listUsers();
    const found = existing?.users?.find(u => u.email === fakeEmail);

    if (found) {
      userId = found.id;
    } else {
      const { data: created, error } = await admin.auth.admin.createUser({
        email:          fakeEmail,
        email_confirm:  true,
        user_metadata:  { github_login: ghUser.login, github_id: ghUser.id, avatar_url: ghUser.avatar_url },
      });
      if (error) throw error;
      userId = created.user.id;
    }

    // Issue a session for this user
    const { data: session, error: sessErr } = await admin.auth.admin.generateLink({
      type:       'magiclink',
      email:      fakeEmail,
      options: { data: { github_login: ghUser.login } },
    });
    if (sessErr) throw sessErr;

    // Exchange the magic link token for a real session
    // We return the token_hash so the browser can exchange it
    return new Response(
      JSON.stringify({
        ok:           true,
        github_login: ghUser.login,
        github_id:    ghUser.id,
        avatar_url:   ghUser.avatar_url,
        // The browser will call supabase.auth.verifyOtp to get a session
        token_hash:   session.properties?.hashed_token,
        email:        fakeEmail,
      }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (e) {
    console.error(e);
    return new Response(JSON.stringify({ error: String(e) }), {
      status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
