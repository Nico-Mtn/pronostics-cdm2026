# Pronostix — Pronostics IA · Coupe du Monde 2026 ⚽🤖

> **Auteur : Nico-Mtn** — https://github.com/Nico-Mtn
> Application web **gratuite, sans publicité, sans paris**, qui pronostique les matchs de
> la Coupe du Monde 2026 et se met à jour automatiquement au fil des résultats réels.
> 🟢 **Réutilisation libre — un crédit au créateur (Nico-Mtn) serait grandement apprécié.**

Démo : https://nico-mtn.github.io/pronostics-cdm2026/

---

## Ce que fait Pronostix

- **Deux modes** : *Réel* (résultats et qualifiés factuels) et *Prono de Nono* (projections IA).
- **Phase de groupes** : prono par match, indice de confiance, dynamique, classements, buteurs & passeurs.
- **Phases finales** : tableau **format FIFA** (finale au centre), projections de parcours,
  indice de confiance par match, **2ᵉ scénario** quand la confiance < 65 %, champion projeté, partage.
- **PWA** installable, hors-ligne, **notification matinale** (récap de la veille + matchs du jour).
- **Auto-update** : un cron (Cloudflare) déclenche le workflow GitHub toutes les 25 min.

## Le modèle de prédiction (v3.5)

Le moteur est documenté en détail dans [`MODELE.md`](MODELE.md). En résumé :

| Brique | Rôle |
|---|---|
| **Elo réel** (`data/elo_snapshot.json`) | Force de base des équipes (eloratings.net, figé au coup d'envoi) |
| **Elo + forme LIVE** | Recalculés à chaque run depuis les vrais résultats → le modèle s'affûte dans le temps |
| **Dixon-Coles** | Modèle de buts (λ depuis l'Elo, correction faible-score) → probas V/N/D, scores |
| **Forme** (`data/team_form.json`) | Attaque/défense récente (~50 matchs) |
| **Confrontations directes** (`data/h2h.json`) | Tendances des duels |
| **Style tactique** | Confrontation (contre/possession…) + ouverture du match |
| **Momentum + prestige** | Récence pondérée, exploit récent valorisé |
| **Expérience des grands matchs** | Pèse dans les tours décisifs |
| **Surprise calibrée** | Le qualifié principal est toujours le plus probable ; la surprise reste prévisible |
| **Calibration apprise** (`data/calibration.json`) | Paramètres auto-ajustés par `learn.py` |

**Fiabilité** : phase de groupes mesurée à **62,5 %** ; cible réaliste **73-76 %** sur l'issue
1/N/2 (plafond du sport ~75-78 %). Le score exact n'est pas l'objectif — c'est la **direction**.

## Apprentissage continu

Le modèle **apprend au fil du temps** : à chaque exécution, l'Elo et la forme intègrent les
résultats réels. La boucle d'**auto-calibration** affine les paramètres :

```
python3 learn.py        # ajuste data/calibration.json (validation croisée anti-surapprentissage)
```

> Le **prono noté est figé** (on ne réécrit jamais le passé). L'apprentissage sert aux **futurs**
> pronos (phases finales en cours, phases de groupes des prochaines éditions).

## Scripts (offline, hors `update.py`)

| Script | Rôle |
|---|---|
| `backtest.py` | Mesure la fiabilité (direction, Brier, log-loss) + analyse d'erreurs, CdM 2010-2022 |
| `build_stats.py` | Régénère `team_form.json` / `h2h.json` + calibration des buts depuis le dataset CC0 |
| `learn.py` | Boucle d'auto-calibration → `data/calibration.json` |
| `benchmark_versions.py` | Compare la fiabilité des versions du modèle (2.3 → 3.5) |

## Architecture

- Site **statique** (GitHub Pages). `update.py` (sans dépendance) génère `index.html` depuis
  `template.html` + les données.
- Données : **football-data.org** (scores, buteurs, affiches KO) ; repli `data/results_manual.json`.
- Notifications & cron : **Cloudflare Worker** → workflows GitHub Actions.

## Sources de données

- World Football Elo Ratings — eloratings.net
- Dataset CC0 « International football results 1872→présent » (martj42) — backtest & stats
- football-data.org — résultats live

## Licence & crédit

Projet personnel de **Nico-Mtn**, sans but lucratif, **sans publicité ni paris**.
Vous pouvez vous en inspirer ou le réutiliser : **merci de créditer le créateur, Nico-Mtn**
(https://github.com/Nico-Mtn). Un simple lien suffit et fait toujours plaisir. 🙏

🤖 Conçu par Nicolas Martin
