# ⚽ Pronostix — Pronostics IA, Coupe du Monde 2026

Page web **gratuite, partageable et auto-actualisée chaque jour** : pronostics IA de la Coupe du Monde 2026, mis à jour avec les vrais scores récupérés via football-data.org. La dynamique (momentum) de chaque sélection est recalculée à partir des résultats réels et réinjectée dans les pronostics des matchs à venir.

**Le tout tourne tout seul, gratuitement, via GitHub Actions + GitHub Pages.**

---

## 🚀 Mise en place (≈ 10 minutes, une seule fois)

### 1. Créer le dépôt
- Crée un nouveau dépôt GitHub (public, c'est requis pour GitHub Pages gratuit).
- Téléverse tous ces fichiers en respectant l'arborescence :

```
.
├── update.py                      moteur : fetch scores + pronostics + génération
├── template.html                  gabarit de la SPA (modes, PWA, push)
├── index.html                     page générée (publiée sur Pages)
├── data.json                      payload complet généré (lu par le service worker)
├── manifest.webmanifest           manifeste PWA
├── sw.js                          service worker (offline + notifications push)
├── logo.png · icon-192.png · icon-512.png · apple-touch-icon.png
├── data/
│   └── results_manual.json        filet de sécurité / historique des scores
├── notify/                        infra notifications (Cloudflare + envoi)
│   ├── worker.js                  Worker : abonnements push + Cron Triggers
│   ├── send.mjs                   envoi des push (web-push)
│   ├── notify.yml                 → à placer dans .github/workflows/
│   └── wrangler.toml
├── .github/
│   └── workflows/
│       ├── update.yml             mise à jour + déploiement Pages
│       └── notify.yml             notification matinale
├── NOTIFICATIONS.md               guide de mise en place des notifications
├── SECURITY.md                    politique de signalement de vulnérabilité
└── README.md
```

### 2. Obtenir une clé football-data.org (gratuit)
- Crée un compte sur **https://www.football-data.org/** (offre **Free**, valable « Forever »).
- La compétition **`WC` | FIFA World Cup est incluse dans le plan gratuit**.
- Récupère ta clé (token) dans ton compte.
- Test rapide (remplace TA_CLE) :
  `curl -H "X-Auth-Token: TA_CLE" https://api.football-data.org/v4/competitions/WC/matches`

### 3. Enregistrer la clé comme secret GitHub
- Dépôt → **Settings → Secrets and variables → Actions → New repository secret**
- Nom : `FOOTBALLDATA_KEY`
- Valeur : ton token football-data.org
- ⚠️ Ne mets **jamais** la clé en clair dans le code.

### 4. Activer GitHub Pages
- Dépôt → **Settings → Pages**
- Source : **GitHub Actions**

### 5. Lancer une première fois
- Onglet **Actions** → workflow « Mise à jour quotidienne des pronostics » → **Run workflow**.
- Une fois terminé, ta page est en ligne à :
  `https://TON-PSEUDO.github.io/NOM-DU-DEPOT/`

C'est cette **URL que tu partages**. Elle se met à jour toute seule.

---

## 🔄 Fonctionnement automatique

**Toutes les 2 heures**, le pipeline :
  1. interroge football-data.org pour les matchs **terminés** (statut FINISHED) ;
  2. mappe les noms d'équipes (anglais → français) et réoriente les scores ;
  3. calcule la **dynamique** de chaque sélection ;
  4. recalcule les pronostics des matchs **à venir** ;
  5. régénère `index.html` + `data.json` et les publie sur GitHub Pages.

Tu n'as **rien à faire**. Déclenchement manuel possible via **Actions → Run workflow**.

### Qui déclenche quoi ? (architecture)

Le **cron natif de GitHub Actions n'est pas fiable** : les exécutions planifiées
sont « best-effort » et régulièrement ignorées la nuit. Pour garantir des mises à
jour et des notifications **à l'heure**, c'est un **Cloudflare Worker** (dont les
Cron Triggers sont fiables) qui pilote les workflows GitHub via l'API
(`workflow_dispatch`) :

| Cron Cloudflare (UTC) | Action | Workflow GitHub appelé |
|---|---|---|
| `0 */2 * * *` | Mise à jour de la page | `update.yml` |
| `5 6 * * *` (08h05 Paris l'été) | Notification matinale | `notify.yml` |

Le Worker utilise un **token GitHub fine-grained** (secret Cloudflare `GH_TOKEN`,
permission *Actions: read/write* sur ce dépôt uniquement). Les workflows GitHub
n'ont donc **plus de `schedule`** : seulement `workflow_dispatch` (Cloudflare + manuel).

> ⚠️ **Pas de trigger `push`** sur `update.yml` : le job committe lui-même
> `index.html` (dont l'horodatage change à chaque run), donc un déclenchement sur
> `push` relancerait le workflow en boucle. Les commits du bot portent `[skip ci]`.

---

## 🛟 Mode repli (sans API)

Si la clé API est absente, le quota épuisé ou la compétition indisponible, le script lit `data/results_manual.json`.
Tu peux y saisir/corriger des scores à la main :

```json
{
  "derniere_maj": "2026-06-12",
  "resultats": {
    "1": { "h": 2, "a": 0 },
    "2": { "h": 2, "a": 1 }
  }
}
```

La clé est le **numéro du match** (id de 1 à 72, ordre des matchs de groupe), `h` = buts équipe 1, `a` = buts équipe 2. Les résultats récupérés via l'API sont aussi sauvegardés ici automatiquement (historique + filet de sécurité).

---

## 🧠 Le moteur de pronostics

Chaque pronostic combine : **force FIFA**, **tendance de forme** (15 derniers matchs), **clash tactique** (bloc bas vs pressing, contre vs possession), **léger avantage pays-hôte** (USA/Canada/Mexique — terrain neutre partout ailleurs) et un **facteur surprise** pour les dark horses.

Chaque match affiche :
- un **indice de confiance en %** (issu de l'écart de force via une courbe logistique : ~50 % = issue ouverte, 90 %+ = favori net) ;
- l'**analyse de style** (ex. « Contre-attaque vs Possession ») avec une note tactique.

**Dynamique (momentum)** : à partir des vrais résultats, chaque équipe gagne ou perd de la « forme » (victoire +0,30 / défaite −0,30, bonus d'écart de buts, effet exploit/contre-performance, plafonné à ±1,2). Cette forme ajustée recalcule les pronostics des matchs suivants.

**Notation** : le pronostic noté est celui du **modèle initial** (pré-tournoi). ✓ score exact · ~ bon résultat · ✗ raté.

## 🎨 Interface (page web)

- **Mode clair par défaut**, bouton 🌙/☀️ pour basculer en **mode sombre** (préférence mémorisée).
- **Logo** de l'événement, **drapeaux en images** (via flagcdn.com — gère correctement Écosse et Angleterre).
- Badge **🏟️ pays-hôte** sur les nations organisatrices.
- 4 vues : Live feed, Matchs (confiance + style + **phases finales en bracket arborescent**), Classements (avec **top buteurs**), Dynamique.
- **Fiche équipe** : un clic sur n'importe quel nom d'équipe ouvre son parcours (matchs joués + à venir, dynamique, projection en phase finale).
- **Top buteurs** : classement des 5 meilleurs buteurs réels (et passes décisives), récupéré via football-data.org, dans l'onglet Classements.
- **Bracket arborescent** : tableau final en branches avec connecteurs, défilement horizontal, vainqueur projeté en tête.

---

## 🔀 Deux modes : Réel & Prono de Nono

Un sélecteur global bascule l'ensemble du site entre :

- **Réel** (par défaut) : uniquement les faits — scores réels, classements réels,
  bracket des qualifiés provisoires. Aucun pronostic affiché.
- **Prono de Nono** : les pronostics du modèle (confiance, style, scores prédits,
  projection du tableau final).

## 📱 Application mobile (PWA) & notifications

Le site est une **PWA** : sur mobile, il peut être **installé sur l'écran d'accueil**
(« Ajouter à l'écran d'accueil ») et fonctionne **hors-ligne** (mise en cache des
dernières données via un *service worker*).

Les visiteurs sur mobile peuvent **activer une notification matinale** (08h05 Paris) :
elle résume les **résultats de la veille** et la **justesse des pronostics** de
Pronostix. L'abonnement est anonyme et désactivable à tout moment.

> Détails d'implémentation : voir [`NOTIFICATIONS.md`](./NOTIFICATIONS.md).

---

## ⚙️ Personnalisation

- **Forces des équipes** : dict `TEAM_DATA` dans `update.py`.
- **Apparence** : variables CSS `:root` en haut de `template.html`.
- **Fréquence des mises à jour / heure de notification** : **Cron Triggers** du
  Worker Cloudflare (`pronobot-push`), section *Settings → Trigger events*.

---

## 📋 Limites à connaître

- L'offre gratuite football-data.org limite le débit (environ 10 requêtes/minute) ; une mise à jour quotidienne reste très largement dans les clous. La Coupe du Monde (WC) est incluse dans le plan gratuit.
- GitHub Pages nécessite un dépôt **public** pour l'offre gratuite.
- Seule la **phase de groupes** (72 matchs) est pronostiquée ; les matchs à élimination dépendent des qualifiés.

---

*Scores réels : football-data.org. Pronostics : modèle maison. Hébergement & automatisation : GitHub (gratuit).*
