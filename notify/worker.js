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
  },

  /* Cron Triggers Cloudflare (fiables, contrairement au cron GitHub).
     Déclenche les workflows GitHub via l'API (workflow_dispatch).
     Secret attendu : GH_TOKEN (PAT fine-grained, repo Nico-Mtn/pronostics-cdm2026,
     permission Actions: Read and write).
     Crons configurés :
       "0 */2 * * *"  → mise à jour de la page (update.yml)
       "5 6 * * *"    → notification matinale 08h05 Paris (notify.yml) */
  async scheduled(event, env, ctx) {
    const REPO = 'Nico-Mtn/pronostics-cdm2026';
    const dispatch = (wf) => fetch(
      'https://api.github.com/repos/' + REPO + '/actions/workflows/' + wf + '/dispatches',
      {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + env.GH_TOKEN,
          'Accept': 'application/vnd.github+json',
          'X-GitHub-Api-Version': '2022-11-28',
          'User-Agent': 'pronobot-cron'
        },
        body: JSON.stringify({ ref: 'main' })
      }
    );
    if (event.cron === '5 6 * * *') {
      ctx.waitUntil(dispatch('notify.yml'));
    } else {
      ctx.waitUntil(dispatch('update.yml'));
    }
  }
};
async function sha(s) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}
