# ⚽ Pronostics IA — Coupe du Monde 2026

Page web **gratuite, partageable et auto-actualisée chaque jour** : pronostics IA de la Coupe du Monde 2026, mis à jour avec les vrais scores récupérés via football-data.org. La dynamique (momentum) de chaque sélection est recalculée à partir des résultats réels et réinjectée dans les pronostics des matchs à venir.

**Le tout tourne tout seul, gratuitement, via GitHub Actions + GitHub Pages.**

---

## 🚀 Mise en place (≈ 10 minutes, une seule fois)

### 1. Créer le dépôt
- Crée un nouveau dépôt GitHub (public, c'est requis pour GitHub Pages gratuit).
- Téléverse tous ces fichiers en respectant l'arborescence :

```
.
├── update.py
├── template.html
├── index.html                     (généré, mais inclus pour le premier affichage)
├── data/
│   └── results_manual.json
├── .github/
│   └── workflows/
│       └── update.yml
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

- **Tous les jours à 08:00 UTC** (10h Paris l'été), GitHub Actions :
  1. interroge football-data.org pour les matchs **terminés** (statut FINISHED) ;
  2. mappe les noms d'équipes (anglais → français) et réoriente les scores ;
  3. calcule la **dynamique** de chaque sélection ;
  4. recalcule les pronostics des matchs **à venir** ;
  5. régénère `index.html` et le publie sur GitHub Pages.
- Tu n'as **rien à faire**. Tu peux aussi déclencher manuellement via **Actions → Run workflow**.

> Modifier l'heure : change la ligne `cron: "0 8 * * *"` dans `.github/workflows/update.yml` (en UTC).

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

**Dynamique (momentum)** : à partir des vrais résultats, chaque équipe gagne ou perd de la « forme » (victoire +0,30 / défaite −0,30, bonus d'écart de buts, effet exploit/contre-performance, plafonné à ±1,2). Cette forme ajustée recalcule les pronostics des matchs suivants — un match serré peut basculer si une équipe est lancée.

**Notation** : le pronostic noté est celui du **modèle initial** (pré-tournoi), pour mesurer la qualité des prévisions de départ. ✓ score exact · ~ bon résultat · ✗ raté.

---

## ⚙️ Personnalisation

- **Forces des équipes** : dict `TEAM_DATA` dans `update.py`.
- **Apparence** : variables CSS `:root` en haut de `template.html`.
- **Heure de mise à jour** : `cron` dans le workflow.

---

## 📋 Limites à connaître

- L'offre gratuite football-data.org limite le débit (environ 10 requêtes/minute) ; une mise à jour quotidienne reste très largement dans les clous. La Coupe du Monde (WC) est incluse dans le plan gratuit.
- GitHub Pages nécessite un dépôt **public** pour l'offre gratuite.
- Seule la **phase de groupes** (72 matchs) est pronostiquée ; les matchs à élimination dépendent des qualifiés.

---

*Scores réels : football-data.org. Pronostics : modèle maison. Hébergement & automatisation : GitHub (gratuit).*
