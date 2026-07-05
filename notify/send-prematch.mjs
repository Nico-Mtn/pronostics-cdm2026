/* Pronostix — Coupe du Monde 2026 | Auteur : Nico-Mtn (https://github.com/Nico-Mtn) | Projet gratuit. */
/* Envoi d'un RAPPEL PRÉ-MATCH (push avec payload texte). Lancé par GitHub Actions
   (notify-prematch.yml) avec l'id du match en entrée (MATCH_ID). Le message (affiche +
   prono + confiance) est composé ici et envoyé prêt à l'emploi ; le service worker
   l'affiche tel quel (branche « payload.body » de sw.js). */
import webpush from 'web-push';

const {
  VAPID_PUBLIC, VAPID_PRIVATE,
  VAPID_SUBJECT = 'mailto:nicolas.martin@simplebo.fr',
  SUBS_URL, LIST_SECRET, MATCH_ID,
  DATA_URL = 'https://nico-mtn.github.io/pronostics-cdm2026/data.json'
} = process.env;

if (!VAPID_PUBLIC || !VAPID_PRIVATE || !SUBS_URL || !LIST_SECRET) {
  console.error('Secrets manquants (VAPID_PUBLIC, VAPID_PRIVATE, SUBS_URL, LIST_SECRET).');
  process.exit(0);
}
if (!MATCH_ID) { console.error('MATCH_ID manquant.'); process.exit(0); }

webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC, VAPID_PRIVATE);

// 1) Retrouver le match par id dans data.json (matches de groupe + phases finales).
const data = await fetch(DATA_URL + '?t=' + Date.now(), { cache: 'no-store' }).then(r => r.json());
const all = (data.matches || []).concat(data.ko_feed || []);
const m = all.find(x => String(x.id) === String(MATCH_ID));
if (!m) { console.error('Match introuvable id=' + MATCH_ID); process.exit(0); }
if (m.reel) { console.log('Match déjà joué → pas de rappel.'); process.exit(0); }

// 2) Composer le message : coup d'envoi dans X min · affiche · prono · confiance.
let mins = null;
if (m.sort) { const d = Math.round((Date.parse(m.sort) - Date.now()) / 60000); if (Number.isFinite(d)) mins = Math.max(1, d); }
const title = mins ? ('⚽ Coup d\'envoi dans ' + mins + ' min') : '⚽ Coup d\'envoi imminent';
const heure = (m.heure || '').replace(':', 'h');
const p = m.prono || m.pred_score || [];
const conf = (m.confidence != null ? m.confidence : m.conf);
let prono = '';
if (p.length === 2) {
  prono = ' · Prono Pronostix : ' + p[0] + '-' + p[1];
  if (conf != null) prono += ', confiance ' + conf + ' %';
}
const body = m.home + ' – ' + m.away + (heure ? ' (' + heure + ')' : '') + prono;
const message = JSON.stringify({ title, body, tag: 'pm-' + m.id, url: './' });
console.log('Message pré-match:', title, '|', body);

// 3) Envoyer à tous les abonnés (retrait des abonnements expirés).
const base = SUBS_URL.replace(/\/$/, '');
const subs = await fetch(base + '/list?key=' + encodeURIComponent(LIST_SECRET)).then(r => r.json());
console.log('Abonnements:', subs.length);
let ok = 0, gone = 0;
for (const sub of subs) {
  try { await webpush.sendNotification(sub, message); ok++; }
  catch (e) {
    if (e.statusCode === 404 || e.statusCode === 410) {
      gone++;
      try {
        await fetch(base + '/remove?key=' + encodeURIComponent(LIST_SECRET), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint: sub.endpoint })
        });
      } catch (_) {}
    } else { console.error('Erreur push:', e.statusCode || e.message); }
  }
}
console.log(`Envoyés: ${ok} · Expirés retirés: ${gone}`);
