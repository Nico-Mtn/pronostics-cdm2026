/* Pronostix — Service Worker | Auteur : Nico-Mtn (https://github.com/Nico-Mtn)
   Projet gratuit, sans publicité, sans paris. Réutilisation : crédit apprécié.

   UN SEUL service worker pour tout le site, enregistré à la racine (/pronostix/).
   Un SW placé dans un sous-dossier ne peut contrôler que ce sous-dossier : chaque
   compétition aurait alors sa propre souscription push, et un même appareil se
   retrouverait abonné trois fois. La racine évite cela.

   Il assure : PWA installable, consultation hors-ligne, et affichage des
   notifications de journée (annonce et bilan), envoyées par compétition. */
const CACHE = 'pronostix-v18';
const CORE = ['./', './index.html', './logo.png', './icon-192.png', './icon-512.png'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE)
    .then(function (c) { return c.addAll(CORE); })
    .catch(function () { /* une ressource absente ne doit pas bloquer l'installation */ })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (ks) {
    return Promise.all(ks.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // CDN externes : on laisse passer

  // Page : réseau d'abord (données fraîches), repli sur le cache hors-ligne.
  // La réponse est mise en cache SOUS SON PROPRE URL : avec une clé unique, le hub,
  // la Ligue 1 et la Premier League s'écraseraient mutuellement, et la navigation
  // hors-ligne servirait la dernière page visitée quelle que soit l'adresse demandée.
  if (req.mode === 'navigate' || url.pathname.endsWith('/') || url.pathname.endsWith('index.html')) {
    e.respondWith(
      fetch(req).then(function (r) {
        var cp = r.clone();
        caches.open(CACHE).then(function (c) { c.put(req, cp); });
        return r;
      }).catch(function () {
        return caches.match(req).then(function (c) { return c || caches.match('./index.html'); });
      })
    );
    return;
  }
  // Autres ressources : cache d'abord, mise à jour en arrière-plan.
  e.respondWith(caches.match(req).then(function (cached) {
    var net = fetch(req).then(function (r) {
      if (r && r.status === 200) {
        var cp = r.clone();
        caches.open(CACHE).then(function (c) { c.put(req, cp); });
      }
      return r;
    }).catch(function () { return cached; });
    return cached || net;
  }));
});

/* ── Notifications push ──
   Le message arrive COMPOSÉ depuis GitHub Actions : { title, body, tag, url }.
   Le service worker n'a donc pas à deviner de quelle compétition il s'agit ni à
   aller relire un data.json — ce qui, avec plusieurs championnats, n'était plus
   possible de façon fiable. Le « tag » porte la compétition et la journée :
   une annonce de Ligue 1 ne remplace jamais une annonce de Premier League. */
self.addEventListener('push', function (e) {
  var p = null;
  try { p = e.data ? e.data.json() : null; } catch (_) { p = null; }
  var titre = (p && p.title) || '⚽ Pronostix';
  var corps = (p && p.body) || 'Résultats et matchs du jour disponibles.';
  var url = (p && p.url) || '/pronostix/';
  e.waitUntil(self.registration.showNotification(titre, {
    body: corps,
    icon: '/pronostix/icon-192.png',
    badge: '/pronostix/icon-192.png',
    tag: (p && p.tag) || 'pronostix',
    renotify: true,
    data: { url: url }
  }));
});

/* Au clic : on rouvre la bonne page. L'ancienne version se contentait de donner le
   focus à n'importe quelle fenêtre ouverte — une notification Ligue 1 pouvait donc
   ramener sur la Premier League. */
self.addEventListener('notificationclick', function (e) {
  e.notification.close();
  var cible = (e.notification.data && e.notification.data.url) || '/pronostix/';
  e.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (ws) {
    for (var i = 0; i < ws.length; i++) {
      if (ws[i].url.indexOf(cible.split('#')[0]) === 0 && 'focus' in ws[i]) {
        if ('navigate' in ws[i]) ws[i].navigate(cible);
        return ws[i].focus();
      }
    }
    return clients.openWindow(cible);
  }));
});
