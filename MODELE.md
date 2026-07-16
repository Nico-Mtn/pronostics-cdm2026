# Pronostix — Modèle de prédiction (v3.6)

> **Auteur : Nico-Mtn** — https://github.com/Nico-Mtn
> Document de référence du moteur de pronostics. Projet gratuit, sans pub, sans paris.
> 🟢 **Réutilisation libre — un crédit au créateur (Nico-Mtn) serait grandement apprécié.**

---

## 0. Principes

- Métrique visée : **fiabilité directionnelle** = (exact + bon) / joués sur l'issue 1/N/2.
- **Prono noté FIGÉ** : le prono de référence d'un match de poule = `compute(home, away, None)`,
  calculé pré-tournoi, jamais réécrit. Les évolutions ci-dessous ne modifient **pas** les grades passés.
- **Déterministe / reproductible** : aucune dépendance réseau à l'exécution ; tout dérive de
  snapshots committés + des vrais résultats.
- Distinction **phase de groupes** (un nul est une issue) vs **phases finales** (il y a toujours
  un vainqueur : prolongation / tirs au but).

## 1. Phase de groupes (moteur historique, inchangé depuis la 2.3)

`compute()` : force de base `TEAM_DATA` + tendance + momentum observé + facteur qualification
(3ᵉ match) + avantage hôte + clash de styles + blend force↔niveau réel observé. Le score est
tiré d'un panier réaliste calé sur les CdM 2010-2022 (graine stable par affiche).
Fiabilité mesurée : **62,5 %** (4 exacts / 41 bons / 27 ratés sur 72 matchs).

## 2. Phases finales (V3 — refonte Elo + Dixon-Coles)

### 2.1 Ratings Elo réels (Lot 1)
Force de base = **World Football Elo** figé dans `data/elo_snapshot.json` (daté du coup d'envoi).
Avantage hôte = +60 pts Elo. Repli déterministe dérivé de `TEAM_DATA` si une équipe manque.

### 2.2 Elo + forme LIVE (dynamique — v3.2)
À chaque run, on **rejoue chronologiquement tous les vrais résultats** du tournoi (groupes + KO
joués) pour mettre à jour l'Elo (poids tournoi + marge de victoire) et la forme (buts réels
blendés). Le modèle **s'affûte donc dans le temps**, sans réécrire le passé noté.

### 2.3 Modèle de buts Dixon-Coles (Lot 3)
`λ_dom / λ_ext` dérivés de l'écart Elo (suprématie bornée) et d'un **total de buts calibré**
(`ko_mu` par tour, ~2,5-2,9). Correction τ de Dixon-Coles sur les faibles scores. Sortie :
**P(V) / P(N) / P(D)**, distribution, score le plus probable.

### 2.4 Surcouches
- **Forme** (`team_form.json`) : prolificité attaque × faille défensive adverse.
- **H2H** (`h2h.json`) : nudge léger suprématie + total selon le bilan des duels.
- **Style** : confrontation tactique (`style_bonus`) + ouverture du match (`STYLE_OPEN`).
- **Momentum + prestige** : performance récente pondérée ; une **victoire de prestige** récente
  (battre un mieux classé) est amplifiée. Borné ±~40 pts Elo.
- **Expérience des grands matchs** : nudge croissant avec l'enjeu du tour (R32 → finale).
- **Défense d'élite** (v3.6) : au-delà du plancher de forme (0,78), on réduit **légèrement** le
  nombre de buts attendus d'une équipe qui **affronte un bloc d'élite**. Métrique = buts
  encaissés/match sur les **10 derniers résultats** de l'adversaire (`ga10` de `team_form.json`,
  régénéré par `build_stats.py` — fenêtre qui inclut le tournoi en cours). Effet **gradué et
  borné** : nul au-dessus de `def_elite_zero` (≈ défense moyenne, 0,90), maximal à `def_elite_full`
  (0,20 → réduction `def_elite_k`, 15 %). **Réservé aux matchs À VENIR** : les pronos déjà notés
  ne sont **pas** réécrits. **Inerte** tant que `ga10` n'est pas committé (déploiement sans risque).

### 2.5 Issue, qualifié, score affiché
- Qualification : `advH = P(V) + ½·P(N)`, `advA = P(D) + ½·P(N)` (les nuls se décident aux t.a.b.).
- **Qualifié principal = toujours le plus probable** (plus haute confiance). Pas de tirage
  aléatoire : une « surprise » n'apparaît que si les signaux du modèle (forme, momentum, style,
  H2H, expérience) la **justifient** — une surprise *prévisible*.
- **2ᵉ scénario** affiché quand la confiance < 65 % (qualifié alternatif + score + probabilité).
- Score décisif pour le qualifié ; **nul + t.a.b. réservé aux vrais 50/50** (`ko_coinflip`).
- **Justesse (✓/✗ prono)** mesurée sur le favori mathématique, côté Prono uniquement.
- **Prono KO FIGÉ (v3.6)** : le prono d'un match à élimination directe est **verrouillé 24 h avant
  le coup d'envoi** et persisté dans `data/ko_pronos.json`. Ensuite il ne bouge plus — le prono
  affiché la veille est **exactement** celui qui sera noté (fini le score qui dérive au fil des
  runs quand l'Elo/forme live évoluent). Gel strictement **avant** le coup d'envoi (jamais après :
  une panne API ne peut donc pas geler des matchs déjà joués). Repli sûr = calcul à la volée si un
  match n'a pu être figé. La surcouche défense d'élite est incluse **au moment du gel**.

## 3. Calibration apprise (`data/calibration.json`)

Paramètres auto-ajustés par `learn.py` : `ko_sup_div`, `ko_mu`, `ko_coinflip`, poids d'expérience,
`group_draw_band` (bande de nul pour les matchs de poule **à venir**). `update.py` lit ce fichier ;
défauts = comportement actuel. La bande de nul ne s'applique **jamais** aux matchs déjà joués.
Surcouche défense d'élite (v3.6) : `def_elite_zero` (0,90), `def_elite_full` (0,20), `def_elite_k`
(0,15). `learn.py` **préserve** ces clés (fusion dans le fichier existant). Étude de validation :
`python3 backtest.py --defense` (hors-ligne, dataset CC0).

## 4. Apprentissage continu

`learn.py` ajuste les paramètres depuis les résultats accumulés avec **validation croisée**
(leave-one-group-out) pour éviter le sur-apprentissage. Exemple mesuré : la bande de nul calibrée
ferait passer la fiabilité des poules de 62,5 % à ~66,7 % (à valider hors-échantillon).
Cible réaliste globale : **73-76 %** ; plafond du sport ~75-78 % (l'aléa et les nuls serrés sont
en grande partie irréductibles).

## 5. Données & fichiers

| Fichier | Contenu |
|---|---|
| `data/elo_snapshot.json` | Elo figé par équipe |
| `data/team_form.json` | Forme attaque/défense (~50 matchs) + `ga10` (défense sur 10 derniers) |
| `data/h2h.json` | Bilans des confrontations directes |
| `data/calibration.json` | Paramètres apprenables (dont défense d'élite) |
| `data/ko_pronos.json` | Pronos KO **figés** 24 h avant le coup d'envoi (affichage = notation) |
| `data/results_manual.json` | Repli résultats + affiches KO |
| `update.py` | Moteur + génération de `index.html` |
| `learn.py` / `backtest.py` / `build_stats.py` / `benchmark_versions.py` | Outils offline |

## 6. Historique des versions

2.3 base · 3.0 Elo + Dixon-Coles · 3.1 forme/H2H/calibration buts · 3.2 Elo & forme LIVE ·
3.3 style tactique · 3.4 momentum + expérience + surprise calibrée + 2ᵉ scénario ·
3.5 calibration apprise + qualifié = plus haute confiance + KO sans nuls superflus ·
**3.6 surcouche « défense d'élite » (ga10 sur 10 derniers, léger & calibrable) + prono KO figé 24 h
avant le coup d'envoi (affichage = notation, plus de dérive du score).**

---

🤖 Conçu et itéré avec l'assistance de Claude (Cowork), relu et validé par **Nico-Mtn**.
Réutilisation : **merci de créditer le créateur, Nico-Mtn** (https://github.com/Nico-Mtn). 🙏
