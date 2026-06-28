# Pronostix — Fonctionnement du modèle de prédiction des matchs

> Document technique destiné à étudier la faisabilité d'évolutions du moteur.
> Code de référence : `update.py` (Python, sans dépendance externe). Version actuelle : **MODEL_VERSION = 2.3**.
> Site statique : GitHub Pages ; régénération toutes les 25 min via un Cloudflare Worker qui
> déclenche le workflow GitHub (`workflow_dispatch`). Données : **football-data.org** (offre gratuite).

---

## 1. Vue d'ensemble

Pour chaque match, le moteur calcule une **force** par équipe, en dérive un **écart de force** `diff = forceDom − forceExt`, puis en tire :
- l'**issue** (victoire dom / nul / victoire ext) selon le signe de `diff` ;
- un **indice de confiance** (%) via une courbe logistique sur `|diff|` ;
- un **score exact** tiré d'un panier de scores réalistes (déterministe par affiche), puis légèrement ajusté par la forme observée.

Deux jeux de pronostics coexistent :
- **`prono_initial`** : calculé **sans aucune donnée dynamique** (`compute(home, away, None)`) → c'est le prono **figé pré-tournoi**, celui qui est **noté** (✓ exact / ~ bon résultat / ✗ raté).
- **prono affiché** (matchs à venir) : `compute(home, away, momentum, qualif, form)` → intègre toute la dynamique et **évolue** au fil de la compétition.

Cette séparation garantit que les améliorations dynamiques **ne faussent jamais la notation**.

---

## 2. Données & pipeline

- `fetch_from_api()` : récupère via `GET /v4/competitions/WC/matches` les **scores** (matchs FINISHED), les **horaires** officiels, et les **affiches réelles de phase finale** (équipes + scores + vainqueur, par `stage`, mappées aux identifiants 73–104). `fetch_scorers()` : `GET /scorers?limit=50` → buteurs + passeurs.
- Repli : si l'API est indisponible, lecture de `data/results_manual.json` (résultats, horaires et `ko_affiches` mémorisés).
- `build_payload()` : assemble tout dans un dictionnaire sérialisé en JSON et **injecté dans `index.html`** (placeholder `/*__DATA__*/`). Le front (`template.html`) ne fait que **lire `DATA`** ; aucun calcul de prono côté client.
- Sorties clés de `DATA` : `matches` (72 matchs de groupe), `standings`, `momentum`, `knockout` (projection Prono), `knockout_real` (réel), `ko_feed` (matchs KO pour le live feed), `scorers`, `assists`, `stats`.

---

## 3. Calcul de la force — `compute(home, away, momentum, qualif, dyn, ko, ko_tier)`

Force d'une équipe = somme des composantes :

| Composante | Détail | Valeur |
|---|---|---|
| **Force FIFA de base** | `TEAM_DATA[équipe] = (force, tendance, style, outsider)`. `force` ≈ échelle 3.8–9.1 (saisie manuelle). | ex. Argentine 9.1, Curaçao 3.8 |
| **Tendance statique** | `tendance ∈ {up, down, stable}` | +0.4 / −0.4 / 0 |
| **Momentum (dynamique)** | forme réelle réinjectée (voir §6) | plafonné ±1.2 |
| **Avantage pays-hôte** | USA / Canada / Mexique | +0.25 |
| **Facteur qualification** (3e match de poule) | équipe déjà qualifiée (turnover) / en survie / éliminée | −0.35 / +0.20 / −0.25 |
| **Clash de style** | bonus selon l'opposition tactique (voir §7) | de −0.3 à +0.4 |
| **Blend FIFA ↔ réel** (v2.3) | niveau réel observé (voir §5) | plafonné ±0.35 |

`diff = forceDom − forceExt` → passé à la confiance et à la génération de score.

---

## 4. Génération du score — `_score_from_diff(diff, ..., ko, ko_tier)`

- Le score est tiré d'un **panier** `(buts_favori, buts_adverse)` choisi selon `|diff|`, via une **graine déterministe par affiche** (`seed = Σ ord(c)` sur `home|away`) → diversité réaliste **reproductible**.
- **Phase de groupes** : paniers calés sur la distribution des CM 2010-2022 (1-0, 2-1, 2-0, 3-1, 0-0…).
- **Phase finale** (`ko=True`) : paniers **plus bas et plus serrés**, **resserrés par tour** via `ko_tier` (0 = 16es/8es, 1 = quarts/demies, 2 = finale). Calibré sur l'étude des 4 dernières CM (les KO sont plus fermés ; le 1-0 domine ; finale ≈ 1 but). Conséquence : davantage de nuls → tirs au but (le favori passe).
- Orientation finale du score selon le signe de `diff`. Léger resserrement « outsider » sur match serré.

---

## 5. Ajustement dynamique & forme observée

`compute_form(results)` calcule, à partir des vrais résultats de groupe :
- `off[équipe]` = buts marqués / match ; `def_[équipe]` = buts encaissés / match ;
- `level[équipe]` = `clamp(((pts/n − 1.0)·0.20 + (diffButs/n)·0.10), ±0.35) · min(1, n/2)` → **blend FIFA ↔ niveau réel** (monte en confiance après 2 matchs) ;
- `tg` = buts moyens / match du **tournoi** (tendance de scoring) ;
- `styles[équipe]` = **tactique observée** déduite des buts (voir §7).

`_adjust_goals(...)` (appliqué aux matchs à venir, ≥ 4 matchs joués) ajuste le score d'**au plus 1 but**, en **préservant le vainqueur**, selon :
- l'attaque/défense observée des deux équipes : `buts_attendus = 0.6·1.2 + 0.2·off(soi) + 0.2·def_(adverse)` ;
- l'**environnement de scoring** du tournoi : `env = clamp(tg/2.4, 0.85..1.15)`.

---

## 6. Momentum — `compute_momentum(results)` (pondération récence)

Pour chaque match joué : Victoire **+0.30** / Défaite **−0.30** / Nul 0, + bonus d'écart `marge·0.07`, + effet exploit/contre-perf `écartForce·0.10` (0.05 pour un nul). Les matchs d'une équipe sont **pondérés par récence** (rampe douce 0.85 → 1.15, le dernier match pèse plus). Somme **plafonnée ±1.2**.

---

## 7. Style / tactiques — `style_bonus(s1, s2)` + tactiques observées

Bonus de clash tactique (styles ∈ bloc_bas, pressing, contre, possession) :
`bloc_bas vs pressing → (+0.3, −0.3)` ; `contre vs possession → (+0.4, −0.2)` ; `pressing vs bloc_bas → (−0.2, +0.1)` ; `possession vs contre → (−0.2, +0.3)`.

**v2.3 — tactiques OBSERVÉES** : si une équipe a ≥ 2 matchs, son style est **redéduit de son jeu réel** (proxy buts marqués/encaissés) et **prime** sur le style théorique pour le clash :
- gf<1.1 & ga<1.0 → `bloc_bas` ; gf≥1.7 & ga≤1.0 → `possession` ; gf≥1.6 & ga≥1.3 → `pressing` ; gf≤1.2 & ga≥1.4 → `contre`.

> Limite : pas de données de formation/possession/xG en gratuit → c'est un **proxy** basé sur les buts.

---

## 8. Indice de confiance — `confidence_pct(diff)`

`p = 1/(1+e^(−1.35·|diff|))` ; `pct = 38 + (p−0.5)/0.5·56` ; `pct −= 3` ; borné **[28, 92]**. Moyenne cible ~75 %, plancher ~30 % pour les matchs indécis.

---

## 9. Badge « Surprise »

Un match porte `surprise = True` si : match joué, **confiance > 85 %** sur le vainqueur prédit, mais ce favori **ne gagne pas** (défaite **ou** nul). Calculé sur `prono_initial` (figé) → indépendant de la dynamique.

---

## 10. Phase finale — brackets

- **Affiches réelles** : dès que l'API publie le tirage, `ko_fixtures` fournit les vraies équipes/scores/vainqueurs ; les brackets les utilisent (repli sur reconstruction `_resolve_ref` tant qu'inconnues). Identifiants 73–104 alignés sur la numérotation officielle FIFA.
- **`knockout` (Prono)** : vraies affiches + **score prédit** pour les matchs à venir ; **vrai score** pour les matchs joués ; propagation du vainqueur ; `champion` projeté. Chaque match joué porte `hit` = (vainqueur prédit == vainqueur réel) → badge ✓/✗ **côté Prono uniquement**.
- **`knockout_real` (Réel)** : vraies affiches + vrais scores (sans prédiction).
- Score KO généré avec `ko=True` + `ko_tier` croissant (voir §4).

---

## 11. Constantes principales (où régler le modèle)

- `TEAM_DATA` (force/tendance/style/outsider par équipe) — `update.py`.
- `HOST_BONUS = 0.25`, `HOST_NATIONS`.
- Momentum : ±0.30, marge·0.07, exploit·0.10, cap ±1.2, récence 0.85→1.15.
- Qualification : −0.35 / +0.20 / −0.25.
- `style_bonus` (matrice).
- Confiance : pente 1.35, remappe 38→94, abattement −3, bornes 28/92.
- `level` (blend) : 0.20 / 0.10, cap ±0.35.
- `_adjust_goals` : poids 0.6/0.2/0.2, `env` ±15 %, seuil n≥4, ±1 but.
- Paniers de score (groupe & KO par tier) dans `_score_from_diff`.

---

## 12. Limites connues

- **Pas de modèle de buts probabiliste** : le score vient d'un panier + graine (pas de probabilités 1/N/2 ni distribution).
- **Pas de probabilités de parcours** : la projection du bracket est déterministe (le favori passe).
- **Forces de base manuelles & statiques** (`TEAM_DATA`).
- **Confiance calibrée à la main** (non backtestée).
- **Pas d'xG, ni blessures/suspensions, ni cotes** (indisponibles en gratuit). Le « style » est un proxy de buts.
- **Notation limitée** à la phase de groupes.

---

## 13. Pistes d'évolution à étudier (faisabilité)

1. **Modèle de Poisson bivarié / Dixon-Coles** : ratings d'attaque/défense par équipe (initialisés depuis `TEAM_DATA`, mis à jour sur résultats réels), avantage terrain, correction faible-score → **probabilités** V/N/D, score le plus probable, distribution. Remplacerait les paniers + la courbe de confiance ad hoc.
2. **Simulation Monte-Carlo** (~10 000 tirages) sur le bracket → **% de qualification / finale / titre** par équipe.
3. **Initialisation par Elo** (ex. World Football Elo) au lieu d'une force manuelle.
4. **Backtest hors-ligne** sur CM passées : **Brier score**, log-loss, courbe de calibration → réglage objectif des hyperparamètres.
5. **Intégration de données contextuelles** si une source (même payante) devient disponible : xG, repos/voyage, absences.

Contraintes à respecter pour toute évolution : rester **gratuit, sans paris, sans pub** ; conserver la **compatibilité GitHub Pages/Actions** ; **ne pas casser le format de `data.json`** (ajouter des champs, n'en retirer aucun) ; garder la distinction **prono noté figé vs prono affiché dynamique** ; rester **déterministe/reproductible** d'un run à l'autre.

---

## 14. Fichiers

- `update.py` — moteur (tout ce qui précède) + génération de `index.html` et `data.json`.
- `template.html` — front (lecture de `DATA`, rendu, PWA, push, bracket).
- `data/results_manual.json` — filet de secours (résultats, horaires, `ko_affiches`).
- `sw.js` — service worker (offline + notification matinale).
- `.github/workflows/update.yml` — régénération + déploiement Pages (déclenché par le Cron Trigger Cloudflare).
