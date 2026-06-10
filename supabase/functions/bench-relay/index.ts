import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ALLOWED_PATHS = ['/template.json', '/submit', '/worker', '/stats'];

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'authorization, content-type, x-bench-target'
      }
    });
  }

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

  const url     = new URL(req.url);
  const path    = url.pathname.replace(/^\/bench-relay/, '') || '/template.json';
  const allowed = ALLOWED_PATHS.some(p => path.endsWith(p));
  if (!allowed) {
    return new Response(JSON.stringify({ error: `Path not allowed: ${path}` }), {
      status: 403,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  const proxyUrl = targetUrl.origin + path;

  try {
    const body    = req.method !== 'GET' ? await req.arrayBuffer() : undefined;
    const ct      = req.headers.get('content-type') || 'application/json';
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
