import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ALLOWED_PATHS = ['/template.json', '/submit', '/worker', '/stats', '/archive-upload'];

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'authorization, content-type, x-bench-target, x-discord-webhook'
      }
    });
  }

  const url  = new URL(req.url);
  const path = url.pathname.replace(/^\/bench-relay/, '') || '/template.json';

  // ── Discord webhook proxy ────────────────────────────────────────────────
  // POST /bench-relay/discord  { embeds:[...] }  header: x-discord-webhook: <url>
  if (path === '/discord') {
    const webhookUrl = req.headers.get('x-discord-webhook') || Deno.env.get('DISCORD_WEBHOOK') || '';
    if (!webhookUrl) {
      return new Response(JSON.stringify({ error: 'No Discord webhook configured' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
    try {
      const body = await req.text();
      const dr = await fetch(webhookUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        signal: AbortSignal.timeout(8000)
      });
      return new Response(null, {
        status: dr.ok ? 204 : dr.status,
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e) }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
  }

  // ── Pool proxy ────────────────────────────────────────────────────────────
  const target = req.headers.get('x-bench-target');
  if (!target) {
    return new Response(JSON.stringify({ error: 'Missing X-Bench-Target header' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  let targetUrl: URL;
  try { targetUrl = new URL(target); }
  catch {
    return new Response(JSON.stringify({ error: 'Invalid target URL' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  // Archive upload special-case (FormData passthrough)
  if (path === '/archive-upload') {
    const archiveTarget = req.headers.get('x-bench-target') || 'https://archive.org/upload/';
    try {
      const body = await req.arrayBuffer();
      const ct   = req.headers.get('content-type') || '';
      const up   = await fetch(archiveTarget, {
        method: 'POST',
        headers: { 'Content-Type': ct },
        body,
        signal: AbortSignal.timeout(30000)
      });
      return new Response(await up.text(), {
        status: up.status,
        headers: { 'Content-Type': up.headers.get('content-type') || 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e) }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }
  }

  const allowed = ALLOWED_PATHS.some(p => path.endsWith(p));
  if (!allowed) {
    return new Response(JSON.stringify({ error: `Path not allowed: ${path}` }), {
      status: 403,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  const proxyUrl = targetUrl.origin + path;

  try {
    const body     = req.method !== 'GET' ? await req.arrayBuffer() : undefined;
    const ct       = req.headers.get('content-type') || 'application/json';
    const upstream = await fetch(proxyUrl, {
      method:  req.method,
      headers: { 'Content-Type': ct },
      body,
      signal:  AbortSignal.timeout(12000)
    });
    const text   = await upstream.text();
    const status = upstream.status;
    return new Response(text, {
      status,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'application/json',
        'Access-Control-Allow-Origin': '*',
        'X-Proxied-From': proxyUrl,
        'X-Upstream-Status': String(status)
      }
    });
  } catch (e) {
    return new Response(JSON.stringify({ error: String(e), proxy_url: proxyUrl }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }
});
