# 🔔 Notifications matinales PronoBot (8h — résultats de la veille + justesse)

Le code est prêt. Il reste à brancher l'infrastructure d'envoi, **gratuite**, en ~20 min.
Architecture : un petit **Cloudflare Worker** stocke les abonnés ; **GitHub Actions** envoie le push chaque matin à 8h ; le **service worker** du site compose le message (« hier : 3/4 pronos réussis… ») à partir de `data.json`.

Tu fais les étapes ci-dessous (compte Cloudflare + clés + secrets) — je ne peux pas créer de compte ni manipuler tes secrets à ta place.

---

## 1. Générer les clés VAPID (une fois)

```bash
npx web-push generate-vapid-keys
```
Note la **clé publique** et la **clé privée**.

## 2. Déployer le Cloudflare Worker (stockage des abonnés)

```bash
npm install -g wrangler
cd notify
wrangler login
wrangler kv namespace create SUBS          # copie l'id affiché
# → colle cet id dans wrangler.toml (champ id)
wrangler secret put LIST_SECRET             # invente une longue chaîne aléatoire, garde-la
wrangler deploy
```
Wrangler affiche l'URL du Worker, par ex. `https://pronobot-push.<toncompte>.workers.dev`.

## 3. Renseigner la config côté site (`template.html`)

Cherche `var PUSH_CONFIG` et remplis :
```js
var PUSH_CONFIG = {
  subscribeUrl: "https://pronobot-push.<toncompte>.workers.dev/subscribe",
  vapidPublicKey: "TA_CLE_PUBLIQUE_VAPID"
};
```
Le bouton **« 🔔 Activer »** apparaîtra alors automatiquement sur le site.

## 4. Ajouter les secrets GitHub (Settings → Secrets and variables → Actions)

| Secret | Valeur |
|---|---|
| `VAPID_PUBLIC` | clé publique VAPID |
| `VAPID_PRIVATE` | clé privée VAPID |
| `SUBS_URL` | URL du Worker **sans** `/subscribe` (ex. `https://pronobot-push.<toncompte>.workers.dev`) |
| `PUSH_LIST_SECRET` | la chaîne définie à l'étape 2 (`LIST_SECRET`) |

## 5. Activer le workflow d'envoi

Déplace `notify/notify.yml` vers `.github/workflows/notify.yml`, puis commit.
- Envoi automatique chaque jour à **06:00 UTC = 08:00 Paris** (heure d'été).
- Test manuel : onglet **Actions → Notification matinale PronoBot → Run workflow**.

---

## Vérifier

1. Ouvre le site sur mobile → bouton **🔔 Activer** → autorise les notifications.
2. Lance le workflow manuellement → tu dois recevoir une notification « PronoBot — résultats d'hier ».

## Notes

- Le push est « nu » (sans contenu chiffré) : le **service worker** récupère `data.json` et compose le message au moment de l'affichage. Plus simple et robuste.
- Les abonnements expirés (téléphone déconnecté, etc.) sont **retirés automatiquement** (codes 404/410).
- En hiver (heure d'hiver), 8h Paris = 07:00 UTC : ajuste le `cron` si besoin hors Mondial.
- 100 % gratuit dans les quotas Cloudflare (Workers + KV) et GitHub Actions.
