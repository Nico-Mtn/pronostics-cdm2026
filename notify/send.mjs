/* PronoBot — envoi de la notification matinale (push « nu », le message est
   construit par le service worker à partir de data.json). Lancé par GitHub Actions. */
import webpush from 'web-push';

const {
  VAPID_PUBLIC, VAPID_PRIVATE,
  VAPID_SUBJECT = 'mailto:nicolas.martin@simplebo.fr',
  SUBS_URL, LIST_SECRET
} = process.env;

if (!VAPID_PUBLIC || !VAPID_PRIVATE || !SUBS_URL || !LIST_SECRET) {
  console.error('Secrets manquants (VAPID_PUBLIC, VAPID_PRIVATE, SUBS_URL, LIST_SECRET).');
  process.exit(0);
}

webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC, VAPID_PRIVATE);

const base = SUBS_URL.replace(/\/$/, '');
const subs = await fetch(base + '/list?key=' + encodeURIComponent(LIST_SECRET)).then(r => r.json());
console.log('Abonnements:', subs.length);

let ok = 0, gone = 0;
for (const sub of subs) {
  try {
    await webpush.sendNotification(sub);   // push nu : le SW compose le message
    ok++;
  } catch (e) {
    if (e.statusCode === 404 || e.statusCode === 410) {
      gone++;
      try {
        await fetch(base + '/remove?key=' + encodeURIComponent(LIST_SECRET), {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint: sub.endpoint })
        });
      } catch (_) {}
    } else {
      console.error('Erreur push:', e.statusCode || e.message);
    }
  }
}
console.log(`Envoyés: ${ok} · Expirés retirés: ${gone}`);
