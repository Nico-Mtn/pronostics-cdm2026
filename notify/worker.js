/* PronoBot — Cloudflare Worker : stockage des abonnements push (gratuit, KV).
   Endpoints :
     POST /subscribe   → enregistre un abonnement (depuis le site)
     GET  /list?key=…  → liste les abonnements (pour l'envoi GitHub Actions, protégé)
     POST /remove?key=…→ retire un abonnement expiré (appelé par l'expéditeur)
   Binding KV attendu : SUBS · Secret attendu : LIST_SECRET */
export default {
  async fetch(req, env) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type'
    };
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors });
    const url = new URL(req.url);

    if (req.method === 'POST' && url.pathname === '/subscribe') {
      const sub = await req.json().catch(() => null);
      if (!sub || !sub.endpoint) return new Response('bad request', { status: 400, headers: cors });
      await env.SUBS.put('sub:' + await sha(sub.endpoint), JSON.stringify(sub));
      return new Response('ok', { headers: cors });
    }

    if (req.method === 'GET' && url.pathname === '/list') {
      if (url.searchParams.get('key') !== env.LIST_SECRET) return new Response('forbidden', { status: 403 });
      const list = await env.SUBS.list({ prefix: 'sub:' });
      const out = [];
      for (const k of list.keys) { const v = await env.SUBS.get(k.name); if (v) out.push(JSON.parse(v)); }
      return new Response(JSON.stringify(out), { headers: { 'Content-Type': 'application/json' } });
    }

    if (req.method === 'POST' && url.pathname === '/remove') {
      if (url.searchParams.get('key') !== env.LIST_SECRET) return new Response('forbidden', { status: 403 });
      const body = await req.json().catch(() => ({}));
      if (body.endpoint) await env.SUBS.delete('sub:' + await sha(body.endpoint));
      return new Response('ok');
    }

    return new Response('PronoBot push service', { headers: cors });
  }
};
async function sha(s) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}
