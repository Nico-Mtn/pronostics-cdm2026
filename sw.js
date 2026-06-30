/* Pronostix — Coupe du Monde 2026 | Auteur : Nico-Mtn (https://github.com/Nico-Mtn) | Projet gratuit. Réutilisation : crédit au créateur (Nico-Mtn) apprécié. */
/* Pronostix — Service Worker (PWA installable + hors-ligne + prêt pour le push) */
const CACHE = 'pronobot-v7';
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

/* ── Notifications push : message « résultats d'hier + justesse de Pronostix » ──
   L'expéditeur (GitHub Actions) envoie un push « nu » ; le message Pronostix est
   construit ici à partir de data.json (résultats réels + statut du pronostic noté). */
function digestHier(){
  return fetch('./data.json', {cache:'no-store'}).then(function(r){ return r.json(); }).then(function(data){
    function isoOf(off){ var d=new Date(); d.setDate(d.getDate()+off);
      return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
    var yiso=isoOf(-1), tiso=isoOf(0);
    var all=(data.matches||[]).concat(data.ko_feed||[]);
    var y=all.filter(function(m){ return m.reel && m.iso===yiso; });
    var todays=all.filter(function(m){ return !m.reel && m.iso===tiso; });
    var parts=[];
    if(y.length){
      var scores=y.slice(0,5).map(function(m){ return m.home+' '+m.reel[0]+'-'+m.reel[1]+' '+m.away; }).join(' / ');
      var ok=y.filter(function(m){ return m.statut==='exact'||m.statut==='bon'; }).length;
      parts.push('Hier : '+scores+(ok?' ('+ok+'/'+y.length+' pronos ✅)':''));
    }
    if(todays.length){
      var tl=todays.slice(0,6).map(function(m){ return m.home+'–'+m.away+(m.heure?' '+m.heure:''); }).join(' / ');
      parts.push('📅 Aujourd\'hui : '+tl);
    }
    if(!parts.length) return { title:'⚽ Pronostix', body:"Pas de match hier ni aujourd'hui — à bientôt !" };
    return { title:'⚽ Pronostix — résultats & matchs du jour', body:parts.join('   •   ') };
  }).catch(function(){ return { title:'⚽ Pronostix', body:"Résultats et matchs du jour disponibles." }; });
}
self.addEventListener('push', function(e){
  e.waitUntil(digestHier().then(function(msg){
    return self.registration.showNotification(msg.title, {
      body: msg.body, icon: './icon-192.png', badge: './icon-192.png', tag: 'pronobot-daily', data: './'
    });
  }));
});
self.addEventListener('notificationclick', function(e){
  e.notification.close();
  e.waitUntil(clients.matchAll({type:'window'}).then(function(ws){
    for(var i=0;i<ws.length;i++){ if('focus' in ws[i]) return ws[i].focus(); }
    return clients.openWindow(e.notification.data || './');
  }));
});
