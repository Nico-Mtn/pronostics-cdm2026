/* PronoBot — Service Worker (PWA installable + hors-ligne + prêt pour le push) */
const CACHE = 'pronobot-v1';
const CORE = ['./', './index.html', './logo.png', './icon-192.png', './icon-512.png', './manifest.webmanifest'];

self.addEventListener('install', function(e){
  e.waitUntil(caches.open(CACHE).then(function(c){ return c.addAll(CORE); }).then(function(){ return self.skipWaiting(); }));
});

self.addEventListener('activate', function(e){
  e.waitUntil(caches.keys().then(function(ks){
    return Promise.all(ks.filter(function(k){ return k!==CACHE; }).map(function(k){ return caches.delete(k); }));
  }).then(function(){ return self.clients.claim(); }));
});

self.addEventListener('fetch', function(e){
  var req = e.request;
  if(req.method !== 'GET') return;
  var url = new URL(req.url);
  // Page / index : réseau d'abord (données fraîches), repli sur le cache hors-ligne
  if(req.mode === 'navigate' || url.pathname.endsWith('/') || url.pathname.endsWith('index.html')){
    e.respondWith(
      fetch(req).then(function(r){
        var cp = r.clone(); caches.open(CACHE).then(function(c){ c.put('./index.html', cp); });
        return r;
      }).catch(function(){ return caches.match('./index.html'); })
    );
    return;
  }
  // Autres ressources : cache d'abord, mise à jour en arrière-plan
  e.respondWith(caches.match(req).then(function(cached){
    var net = fetch(req).then(function(r){
      if(r && r.status===200){ var cp=r.clone(); caches.open(CACHE).then(function(c){ c.put(req, cp); }); }
      return r;
    }).catch(function(){ return cached; });
    return cached || net;
  }));
});

/* ── Notifications push (phase 2 : nécessite l'envoi côté serveur via VAPID) ── */
self.addEventListener('push', function(e){
  var data = { title: 'PronoBot ⚽', body: 'Les matchs du jour sont disponibles.', url: './' };
  try { if(e.data) data = Object.assign(data, e.data.json()); } catch(_){}
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, icon: './icon-192.png', badge: './icon-192.png',
    tag: 'pronobot-daily', data: data.url
  }));
});
self.addEventListener('notificationclick', function(e){
  e.notification.close();
  e.waitUntil(clients.matchAll({type:'window'}).then(function(ws){
    for(var i=0;i<ws.length;i++){ if('focus' in ws[i]) return ws[i].focus(); }
    return clients.openWindow(e.notification.data || './');
  }));
});
