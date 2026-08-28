# -*- coding: utf-8 -*-
# ============================================================================
#  Pronostix — Ligue 1 (France), saison 2026-2027
#  Auteur / Author : Nico-Mtn — https://github.com/Nico-Mtn
#  Projet gratuit, sans publicité, sans paris.
#  Réutilisation libre : un CRÉDIT au créateur (Nico-Mtn) serait grandement
#  apprécié. / If you reuse this model or code, a credit to the creator
#  (Nico-Mtn) would be greatly appreciated.
# ============================================================================
"""
Génère la page /ligue-1-france : calendrier, pronostics, classement (réel +
projeté) et buteurs du championnat de France, à partir de football-data.org
(compétition FL1, incluse dans le plan GRATUIT).

Reprend le fonctionnement éprouvé sur la Coupe du Monde 2026 :
  • moteur de prono Elo + Dixon-Coles (mêmes principes, adaptés au championnat) ;
  • PRONO FIGÉ 24 h avant le coup d'envoi (data/l1_pronos.json) : le prono affiché
    la veille est EXACTEMENT celui qui sera noté — aucune dérive ;
  • notation exact / bon / raté et indice de fiabilité ;
  • mode « Réel » (résultats officiels) et « Prono de Nono » (projections).

Sorties : ligue-1-france/index.html, ligue-1-france/data.json,
          ligue-1-france/content.sig (déploiement conditionnel),
          data/l1_pronos.json (pronos figés, committé).

Usage : python3 l1.py   (variable d'env FOOTBALLDATA_KEY)
"""
import os, sys, json, math, hashlib, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
API = "https://api.football-data.org/v4"
KEY = os.environ.get("FOOTBALLDATA_KEY", "")
FREEZE_LEAD_H = 24           # gel du prono 24 h avant le coup d'envoi

# ─── Championnats suivis ─────────────────────────────────────────────────────
# Ce fichier est un TEMPLATE : ajouter une entrée ci-dessous suffit à créer une
# nouvelle page complète (live feed, calendrier, classement réel + projeté, buteurs).
# `code` = identifiant football-data ; tous ceux listés ici sont en plan GRATUIT.
# `prefix` = préfixe des fichiers de données (data/<prefix>_pronos.json, etc.).
LEAGUES = [
    {"slug": "ligue-1-france", "prefix": "l1", "code": "FL1", "nom": "Ligue 1",
     "drapeau": "🇫🇷", "saison": 2026, "libelle": "2026-2027"},
    {"slug": "premier-league-england", "prefix": "pl", "code": "PL", "nom": "Premier League",
     "drapeau": "🏴", "saison": 2026, "libelle": "2026-2027"},
]
LG = LEAGUES[0]              # championnat courant (réassigné par set_league)
OUTDIR = os.path.join(ROOT, LG["slug"])
COMP = LG["code"]
SEASON = LG["saison"]

def set_league(lg):
    """Bascule le moteur sur un championnat : chemins, code API et saison de référence."""
    global LG, OUTDIR, COMP, SEASON, PREV_SEASON, ELO_START
    LG = lg
    OUTDIR = os.path.join(ROOT, lg["slug"])
    COMP = lg["code"]
    SEASON = lg["saison"]
    PREV_SEASON = SEASON - 1
    ELO_START = {}           # recalculé pour chaque championnat

def data_path(kind):
    """Chemin d'un fichier de données propre au championnat courant."""
    return os.path.join(ROOT, "data", f"{LG['prefix']}_{kind}.json")

def nav_html(current_slug):
    """Sélecteur de compétition commun à toutes les pages."""
    items = ['<a href="../">🏠 Accueil</a>',
             '<a href="../pronostics-cdm2026/">🏆 Coupe du Monde 2026</a>']
    for lg in LEAGUES:
        cls = ' class="on"' if lg["slug"] == current_slug else ""
        href = "./" if lg["slug"] == current_slug else f"../{lg['slug']}/"
        items.append(f'<a href="{href}"{cls}>{lg["drapeau"]} {lg["nom"]}</a>')
    return "\n  ".join(items)

# ─── Elo de départ des clubs ─────────────────────────────────────────────────
# Il n'est PAS saisi de mémoire : il est calculé (voir compute_elo_start) à partir
#   1. des résultats RÉELS de la saison précédente (walk-forward sur tous les matchs),
#      puis régressés vers la moyenne — une équipe ne repart jamais à 100 % de son
#      niveau de fin de saison (mercato, préparation, usure) ;
#   2. d'un ajustement qualitatif de PRÉ-SAISON (data/l1_mercato.json) : départs de
#      cadres, forte rotation d'effectif, changement d'entraîneur… Un groupe très
#      remanié met du temps à trouver son système de jeu.
# Le résultat est FIGÉ dans data/l1_elo_start.json (reproductible + économise le quota API).
ELO_START = {}                 # rempli au runtime
ELO_DEFAULT = 1500.0
PREV_SEASON = SEASON - 1       # saison de référence (2025-2026)
REGRESSION = 0.25              # part de retour vers la moyenne entre deux saisons
PROMU_ELO = 1420.0             # niveau de départ d'un promu (absent de la saison N-1)
MERCATO_CAP = 60.0             # borne de l'ajustement mercato (en points Elo)
HOME_ADV = 65.0        # avantage du terrain en points Elo (championnat)
MU_L1 = 2.72           # total de buts moyen par match en Ligue 1
DC_RHO = -0.13         # correction Dixon-Coles sur les petits scores

# Nom d'affichage : on privilégie le shortName OFFICIEL de l'API (« Paris SG »,
# « Marseille »…), puis le nom complet, puis le trigramme. Aucun découpage maison
# (qui produisait des libellés fautifs du type « de Marseille »).
def disp(team):
    t = team or {}
    for k in ("shortName", "name"):
        v = (t.get(k) or "").strip()
        if v:
            return v if len(v) <= 24 else (t.get("tla") or v[:24])
    return t.get("tla") or "?"

# ─── Accès API ───────────────────────────────────────────────────────────────
def api_get(path):
    if not KEY:
        print("[INFO] FOOTBALLDATA_KEY absente → mode hors-ligne", file=sys.stderr)
        return None
    req = urllib.request.Request(API + path, headers={"X-Auth-Token": KEY})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] API {path} : {e}", file=sys.stderr)
        return None

def fetch_all():
    """Renvoie (matches, standings, scorers) depuis football-data, ou du cache local."""
    m = api_get(f"/competitions/{COMP}/matches?season={SEASON}")
    s = api_get(f"/competitions/{COMP}/standings?season={SEASON}")
    b = api_get(f"/competitions/{COMP}/scorers?season={SEASON}&limit=20")
    cache = data_path("cache")
    if m and m.get("matches"):
        try:
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({"matches": m, "standings": s, "scorers": b,
                           "_saved": datetime.datetime.now(datetime.timezone.utc)
                           .strftime("%Y-%m-%dT%H:%M:%SZ")}, f, ensure_ascii=False)
        except Exception:
            pass
        return m, s, b
    # repli : dernier cache committé (le site reste debout si l'API tousse)
    if os.path.exists(cache):
        try:
            with open(cache, encoding="utf-8") as f:
                d = json.load(f)
            print("[INFO] API indisponible → repli sur le cache local", file=sys.stderr)
            return d.get("matches"), d.get("standings"), d.get("scorers")
        except Exception:
            pass
    return None, None, None

# ─── Modèle : Elo live + Dixon-Coles ─────────────────────────────────────────
def team_elo(elo, name):
    return elo.get(name, ELO_START.get(name, ELO_DEFAULT))

def elo_update(elo, h, a, sh, sa):
    """Applique le résultat d'un match aux ratings (Elo pondéré par l'écart de buts)."""
    eh = elo.setdefault(h, ELO_START.get(h, ELO_DEFAULT))
    ea = elo.setdefault(a, ELO_START.get(a, ELO_DEFAULT))
    exp_h = 1.0 / (1.0 + 10 ** (-((eh + HOME_ADV) - ea) / 400.0))
    res_h = 1.0 if sh > sa else (0.5 if sh == sa else 0.0)
    k = 20.0 * (1.0 + min(abs(sh - sa), 4) * 0.12)
    elo[h] = eh + k * (res_h - exp_h)
    elo[a] = ea + k * ((1.0 - res_h) - (1.0 - exp_h))

def walk_forward(rows):
    """Parcours CHRONOLOGIQUE : chaque match joué est pronostiqué avec l'Elo tel qu'il
    était AVANT ce match (aucune fuite d'information depuis le futur), puis les ratings
    sont mis à jour. Renvoie ({match_id: prono}, elo_final).
    Indispensable quand on démarre en cours de saison : les journées déjà disputées sont
    notées honnêtement, sans que le modèle « connaisse » leur résultat."""
    preds, elo = {}, {}
    for r in rows:
        preds[str(r["id"])] = predict(elo, r["home"], r["away"])
        if r["played"]:
            elo_update(elo, r["home"], r["away"], r["sh"], r["sa"])
    return preds, elo

def load_mercato():
    """Ajustements qualitatifs de PRÉ-SAISON, saisis à la main (jugement humain).
    Format data/l1_mercato.json :
        {"ajustements": {"Olympique Lyonnais": {"delta": -35, "note": "départ de 3 cadres"}}}
    delta en points Elo, borné à ±MERCATO_CAP. Négatif = effectif déstabilisé (beaucoup
    de départs/arrivées, vente de joueurs cadres, nouveau staff → temps d'adaptation) ;
    positif = recrutement qui renforce nettement un groupe déjà en place."""
    p = data_path("mercato")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("ajustements", {}) or {}
    except Exception:
        return {}

def prev_season_elo():
    """Elo de FIN de saison précédente, calculé en walk-forward sur les matchs réels
    (chaque rencontre met à jour les ratings, dans l'ordre chronologique)."""
    raw = api_get(f"/competitions/{COMP}/matches?season={PREV_SEASON}")
    if not raw or not raw.get("matches"):
        return {}
    ms = []
    for m in raw["matches"]:
        ft = ((m.get("score") or {}).get("fullTime") or {})
        if ft.get("home") is None: continue
        h, a = disp(m.get("homeTeam")), disp(m.get("awayTeam"))
        if not h or not a: continue
        ms.append((m.get("utcDate") or "", h, a, ft["home"], ft["away"]))
    ms.sort(key=lambda x: x[0])
    elo = {}
    for _, h, a, sh, sa in ms:
        elo.setdefault(h, ELO_DEFAULT); elo.setdefault(a, ELO_DEFAULT)
        elo_update(elo, h, a, sh, sa)
    return elo

def compute_elo_start(teams_now):
    """Elo de départ de la saison en cours :
       Elo fin N-1 → régression vers la moyenne → ajustement mercato → promus à part.
    Calculé UNE fois puis figé dans data/l1_elo_start.json (reproductible, et le quota
    API n'est pas consommé à chaque run)."""
    path = data_path("elo_start")
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("saison") == SEASON and set(teams_now) <= set((saved.get("elo") or {}).keys()):
            return {k: float(v) for k, v in saved["elo"].items()}
    except Exception:
        pass

    prev = prev_season_elo()
    mercato = load_mercato()
    detail = {}
    if prev:
        avg = sum(prev.values()) / len(prev)
        base = {t: avg + (e - avg) * (1.0 - REGRESSION) for t, e in prev.items()}
    else:
        base, avg = {}, ELO_DEFAULT
    elo, notes = {}, {}
    for t in (teams_now or list(base.keys())):
        if t in base:
            v = base[t]; src = "saison précédente (régressée)"
        else:
            v = PROMU_ELO; src = "promu (aucun match en N-1)"
        adj = mercato.get(t) or {}
        d = max(-MERCATO_CAP, min(MERCATO_CAP, float(adj.get("delta", 0) or 0)))
        elo[t] = round(v + d, 1)
        notes[t] = {"base": round(v, 1), "mercato": d, "source": src,
                    "note": adj.get("note", "")}
    if elo:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"_meta": {
                    "role": "Elo de DÉPART de la saison : résultats réels de la saison "
                            "précédente (walk-forward) régressés vers la moyenne, + ajustement "
                            "qualitatif de pré-saison (data/l1_mercato.json). Figé pour reproductibilité.",
                    "regression": REGRESSION, "promu_elo": PROMU_ELO,
                    "calcule_le": datetime.datetime.now(datetime.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "author": "Nico-Mtn"},
                    "saison": SEASON, "elo": elo, "detail": notes}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] écriture l1_elo_start.json : {e}", file=sys.stderr)
    return elo

def _pois(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def _tau(x, y, lh, la):
    if x == 0 and y == 0: return 1.0 - lh * la * DC_RHO
    if x == 0 and y == 1: return 1.0 + lh * DC_RHO
    if x == 1 and y == 0: return 1.0 + la * DC_RHO
    if x == 1 and y == 1: return 1.0 - DC_RHO
    return 1.0

def predict(elo, home, away):
    """Prono d'un match de championnat : proba V/N/D + score le plus plausible."""
    eh = team_elo(elo, home) + HOME_ADV
    ea = team_elo(elo, away)
    sup = max(-1.9, min(1.9, (eh - ea) / 230.0))
    lam_h = max(0.30, min(3.20, (MU_L1 + sup) / 2.0))
    lam_a = max(0.30, min(3.20, (MU_L1 - sup) / 2.0))
    grid = {}
    for x in range(7):
        for y in range(7):
            grid[(x, y)] = _pois(x, lam_h) * _pois(y, lam_a) * _tau(x, y, lam_h, lam_a)
    tot = sum(grid.values()) or 1.0
    for k in grid: grid[k] /= tot
    pv = sum(p for (x, y), p in grid.items() if x > y)
    pn = sum(p for (x, y), p in grid.items() if x == y)
    pd = sum(p for (x, y), p in grid.items() if x < y)
    # En championnat le NUL est une issue à part entière (contrairement aux phases finales)
    issue = max((("V", pv), ("N", pn), ("D", pd)), key=lambda t: t[1])
    if issue[0] == "V":   cands = {k: v for k, v in grid.items() if k[0] > k[1]}
    elif issue[0] == "N": cands = {k: v for k, v in grid.items() if k[0] == k[1]}
    else:                 cands = {k: v for k, v in grid.items() if k[0] < k[1]}
    (sx, sy) = max(cands.items(), key=lambda kv: kv[1])[0]
    return {"sh": sx, "sa": sy, "issue": issue[0], "conf": int(round(issue[1] * 100)),
            "proba": {"v": int(round(pv * 100)), "n": int(round(pn * 100)), "d": int(round(pd * 100))},
            "eh": int(round(eh - HOME_ADV)), "ea": int(round(ea))}

# ─── Pronos FIGÉS (24 h avant le coup d'envoi) ───────────────────────────────
def load_frozen():
    p = data_path("pronos")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("pronos", {})
    except Exception:
        return {}

def save_frozen(pronos):
    p = data_path("pronos")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"_meta": {
            "role": "Pronostics Ligue 1 FIGÉS 24 h avant le coup d'envoi "
                    "(affichage = notation, aucune dérive). Écrit par l1.py.",
            "author": "Nico-Mtn",
            "credit": "Auteur : Nico-Mtn (https://github.com/Nico-Mtn). Réutilisation libre, crédit apprécié."},
            "pronos": pronos}, f, ensure_ascii=False, indent=2)

def grade(pred, sh, sa):
    """exact = score pile ; bon = bonne issue (V/N/D) ; sinon raté."""
    if pred is None or sh is None: return None
    if pred["sh"] == sh and pred["sa"] == sa: return "exact"
    real = "V" if sh > sa else ("N" if sh == sa else "D")
    return "bon" if pred["issue"] == real else "rate"

# ─── Construction du payload ─────────────────────────────────────────────────
MOIS = {1:"janv.",2:"févr.",3:"mars",4:"avr.",5:"mai",6:"juin",
        7:"juil.",8:"août",9:"sept.",10:"oct.",11:"nov.",12:"déc."}

def paris(dt_utc):
    """UTC → heure de Paris (approximation été/hiver suffisante pour l'affichage)."""
    off = 2 if 3 < dt_utc.month < 11 else 1
    return dt_utc + datetime.timedelta(hours=off)

def build(matches_raw, standings_raw, scorers_raw):
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for m in (matches_raw or {}).get("matches", []):
        ht, at = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        if not (ht.get("name") or ht.get("shortName")) or not (at.get("name") or at.get("shortName")):
            continue
        hn, an = disp(ht), disp(at)      # identifiant unique d'équipe, partout le même
        try:
            dt = datetime.datetime.fromisoformat((m.get("utcDate") or "").replace("Z", "+00:00"))
        except Exception:
            dt = None
        ft = ((m.get("score") or {}).get("fullTime") or {})
        played = m.get("status") in ("FINISHED", "AWARDED") and ft.get("home") is not None
        rows.append({
            "id": m.get("id"), "j": m.get("matchday"), "dt": dt,
            "home": hn, "away": an,
            "hs": hn, "as_": an,
            "ch": ht.get("crest"), "ca": at.get("crest"),
            "sh": ft.get("home") if played else None,
            "sa": ft.get("away") if played else None,
            "played": played,
        })
    rows.sort(key=lambda r: (r["dt"] or datetime.datetime(2099, 1, 1, tzinfo=datetime.timezone.utc)))
    global ELO_START
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    ELO_START = compute_elo_start(teams)   # saison N-1 régressée + mercato (figé)
    walk, elo = walk_forward(rows)   # pronos sans fuite pour le passé + Elo à jour

    frozen = load_frozen(); out_frozen = dict(frozen)
    feed, stats = [], {"joue": 0, "exact": 0, "bon": 0, "rate": 0, "total": len(rows)}
    for r in rows:
        key = str(r["id"])
        fr = frozen.get(key)
        pred = None
        if fr and fr.get("home") == r["home"] and fr.get("away") == r["away"]:
            pred = {k: fr[k] for k in ("sh", "sa", "issue", "conf", "proba") if k in fr}
        elif r["played"]:
            pred = walk[key]                                   # prono « d'avant match » (honnête)
        elif r["dt"] and (r["dt"] - datetime.timedelta(hours=FREEZE_LEAD_H)) <= now < r["dt"]:
            pred = predict(elo, r["home"], r["away"])          # dans la fenêtre → on FIGE
            rec = dict(pred); rec["home"] = r["home"]; rec["away"] = r["away"]
            rec["frozen_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            out_frozen[key] = rec
        else:
            pred = predict(elo, r["home"], r["away"])          # projection (non figée)
        st = grade(pred, r["sh"], r["sa"]) if r["played"] else None
        if st:
            stats["joue"] += 1; stats[st] += 1
        d = paris(r["dt"]) if r["dt"] else None
        feed.append({
            "id": r["id"], "j": r["j"],
            "date": (f"{d.day} {MOIS[d.month]}" if d else ""),
            "heure": (d.strftime("%H:%M") if d else ""),
            "iso": (d.strftime("%Y-%m-%d") if d else ""),
            "sort": (r["dt"].strftime("%Y-%m-%dT%H:%M:%SZ") if r["dt"] else ""),
            "home": r["hs"], "away": r["as_"], "ch": r["ch"], "ca": r["ca"],
            "prono": [pred["sh"], pred["sa"]] if pred else None,
            "issue": pred.get("issue") if pred else None,
            "conf": pred.get("conf") if pred else None,
            "proba": pred.get("proba") if pred else None,
            "reel": [r["sh"], r["sa"]] if r["played"] else None,
            "statut": st, "fige": key in out_frozen,
        })
    save_frozen(out_frozen)

    # Classement RÉEL (API) ---------------------------------------------------
    table = []
    for blk in (standings_raw or {}).get("standings", []):
        if blk.get("type") != "TOTAL": continue
        for t in blk.get("table", []):
            tm = t.get("team") or {}
            table.append({"pos": t.get("position"), "team": disp(tm),
                          "crest": tm.get("crest"), "j": t.get("playedGames"), "pts": t.get("points"),
                          "g": t.get("won"), "n": t.get("draw"), "p": t.get("lost"),
                          "bp": t.get("goalsFor"), "bc": t.get("goalsAgainst"),
                          "diff": t.get("goalDifference")})
        break

    # Classement PROJETÉ fin de saison (réel acquis + pronos des matchs à venir)
    proj = {}
    def slot(name, crest):
        return proj.setdefault(name, {"team": name, "crest": crest, "pts": 0, "j": 0,
                                      "g": 0, "n": 0, "p": 0, "bp": 0, "bc": 0})
    for r, f in zip(rows, feed):
        sh, sa = (r["sh"], r["sa"]) if r["played"] else (
            (f["prono"][0], f["prono"][1]) if f["prono"] else (None, None))
        if sh is None: continue
        H = slot(f["home"], f["ch"]); A = slot(f["away"], f["ca"])
        H["j"] += 1; A["j"] += 1; H["bp"] += sh; H["bc"] += sa; A["bp"] += sa; A["bc"] += sh
        if sh > sa:   H["pts"] += 3; H["g"] += 1; A["p"] += 1
        elif sh < sa: A["pts"] += 3; A["g"] += 1; H["p"] += 1
        else:         H["pts"] += 1; A["pts"] += 1; H["n"] += 1; A["n"] += 1
    projected = sorted(proj.values(), key=lambda t: (-t["pts"], -(t["bp"] - t["bc"]), -t["bp"]))
    for i, t in enumerate(projected, 1):
        t["pos"] = i; t["diff"] = t["bp"] - t["bc"]

    scorers = []
    for s in (scorers_raw or {}).get("scorers", []):
        p = s.get("player") or {}; t = s.get("team") or {}
        scorers.append({"player": p.get("name"), "team": disp(t),
                        "crest": t.get("crest"), "goals": s.get("goals") or 0,
                        "assists": s.get("assists") or 0})

    jours = sorted({f["j"] for f in feed if f["j"]})
    cur = None
    for j in jours:
        if any(f["j"] == j and not f["reel"] for f in feed): cur = j; break
    return {
        "maj": paris(now).strftime("%d/%m/%Y à %H:%M") + " (Paris)",
        "today": now.strftime("%Y-%m-%d"),
        "saison": LG["libelle"], "nom": LG["nom"], "slug": LG["slug"], "journee": cur, "journees": jours,
        "stats": stats, "matches": feed, "table": table,
        "projected": projected, "scorers": scorers,
        "credit": "Auteur : Nico-Mtn (https://github.com/Nico-Mtn). Projet gratuit, sans pub, sans paris.",
    }

# ─── Rendu HTML (page autonome, codes visuels Pronostix) ─────────────────────
PAGE = """<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pronostix — __NOM__ __SAISON__</title>
<meta name="description" content="Pronostics IA gratuits de __NOM__ __SAISON__ : calendrier, classement, buteurs. Sans publicité, sans paris. Par Nico-Mtn.">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:#f4f6fb;color:#1b2333;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:0 14px 40px}
header{background:#fff;border-bottom:1px solid #e6e9f2;padding:14px 0 10px;position:sticky;top:0;z-index:9}
.hrow{max-width:820px;margin:0 auto;padding:0 14px;display:flex;align-items:center;gap:12px}
h1{margin:0;font-size:20px;font-weight:900}
.tag{color:#2246c7;font-weight:700;font-size:12px}
.sub{font-size:11px;opacity:.6;text-transform:uppercase;letter-spacing:.05em}
.pct{margin-left:auto;text-align:center}.pct .b{font-size:22px;font-weight:900;color:#e8a20c;line-height:1}
.pct .l{font-size:10px;opacity:.6;text-transform:uppercase}
.scorebar{max-width:820px;margin:10px auto 0;padding:0 14px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.sc{background:#fff;border:1px solid #e6e9f2;border-radius:12px;padding:9px 6px;text-align:center}
.sc b{display:block;font-size:17px;font-weight:900}.sc span{font-size:10px;opacity:.6;text-transform:uppercase}
.sc.ok b{color:#16a34a}.sc.ko b{color:#dc2626}
.maj{max-width:820px;margin:8px auto 0;padding:0 14px;text-align:center;font-size:11px;opacity:.6}
.compnav{display:flex;gap:8px;margin:14px 0 6px}
.compnav a{flex:1;text-align:center;padding:11px;border-radius:12px;text-decoration:none;font-weight:800;
font-size:14px;background:#fff;border:1px solid #e6e9f2;color:#5a6478}
.compnav a.on{background:#2246c7;color:#fff;border-color:#2246c7}
.modebar{display:flex;gap:8px;margin:10px 0 4px;background:#fff;border:1px solid #e6e9f2;border-radius:12px;padding:4px}
.modebar button{flex:1;padding:9px;border:0;border-radius:9px;background:transparent;font-weight:800;
font-size:14px;color:#5a6478;cursor:pointer}
.modebar button.on{background:#2246c7;color:#fff}
.note{text-align:center;font-size:12px;opacity:.7;margin:6px 0 10px}
nav.tabs{display:flex;gap:8px;margin:10px 0 16px;flex-wrap:wrap}
nav.tabs button{flex:1;min-width:110px;padding:10px;border-radius:12px;border:1px solid #e6e9f2;background:#fff;
font-weight:800;font-size:13px;color:#5a6478;cursor:pointer}
nav.tabs button.on{background:#2246c7;color:#fff;border-color:#2246c7}
.card{background:#fff;border:1px solid #e6e9f2;border-radius:16px;padding:16px;margin-bottom:16px}
.ctitle{display:flex;align-items:center;gap:9px;margin-bottom:14px}
.ctitle .ic{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
font-size:15px;background:linear-gradient(135deg,#f6c453,#e8a20c);flex:none}
.ctitle h3{margin:0;font-size:15px;font-weight:800}
.day{font-size:11px;font-weight:800;opacity:.55;text-transform:uppercase;letter-spacing:.05em;margin:16px 0 8px}
.m{display:flex;align-items:center;gap:10px;padding:12px 2px}
.m+.m{border-top:1px solid #eef0f6}
.m .t{flex:1;display:flex;align-items:center;gap:7px;min-width:0}
.m .t.a{justify-content:flex-end;text-align:right}
.m .t b{font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.m img{width:22px;height:22px;object-fit:contain;flex:none}
.sc2{flex:none;text-align:center;min-width:76px}
.sc2 .v{font-size:17px;font-weight:900}.sc2 .k{font-size:9px;opacity:.55;text-transform:uppercase;letter-spacing:.04em}
.sc2 .p{color:#e8a20c}
.meta{display:flex;align-items:center;gap:6px;justify-content:center;flex-wrap:wrap;margin-top:5px}
.b{font-size:10px;font-weight:800;padding:2px 7px;border-radius:99px;background:#eef1f8;color:#5a6478}
.b.ex{background:#dcfce7;color:#166534}.b.bo{background:#fef3c7;color:#92400e}.b.ra{background:#fee2e2;color:#991b1b}
.b.fg{background:#e0e7ff;color:#3730a3}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;opacity:.55;text-transform:uppercase;padding:6px 4px;font-weight:800}
td{padding:8px 4px;border-top:1px solid #eef0f6}
td.n{text-align:center;width:26px;font-weight:800}
td.p{text-align:center;font-weight:900}
tr.c1 td.n{color:#16a34a}tr.c2 td.n{color:#2246c7}tr.c3 td.n{color:#dc2626}
.tm{display:flex;align-items:center;gap:8px}.tm img{width:20px;height:20px;object-fit:contain}
.empty{text-align:center;opacity:.6;padding:26px 10px;font-size:14px}
footer{text-align:center;font-size:11px;opacity:.55;padding:22px 14px;line-height:1.7}
footer a{color:#2246c7}
@media(prefers-color-scheme:dark){
body{background:#0f1420;color:#e8ecf5}header{background:#161d2e;border-color:#242d42}
.card,.sc,.compnav a,nav.tabs button,.modebar{background:#161d2e;border-color:#242d42}
.modebar button,nav.tabs button,.compnav a{color:#94a0b8}
.m+.m,td{border-color:#242d42}.b{background:#242d42;color:#94a0b8}}
</style></head><body>
<header>
 <div class="hrow">
  <div><h1>Pronostix</h1><div class="tag">Nono le robot, roi des prono 👑</div>
   <div class="sub">__NOM__ · Saison __SAISON__</div></div>
  <div class="pct"><div class="b" id="pct">—</div><div class="l">Fiabilité</div></div>
 </div>
 <div class="scorebar" id="scorebar"></div>
 <div class="maj" id="maj"></div>
</header>
<div class="wrap">
 <div class="compnav">
  __NAV__
 </div>
 <div class="modebar">
  <button data-m="reel">⚽ Réel</button>
  <button data-m="prono" class="on">🤖 Prono de Nono</button>
 </div>
 <div class="note" id="note"></div>
 <nav class="tabs" id="tabs">
  <button data-v="feed" class="on">🔥 Live feed</button>
  <button data-v="cal">📅 Calendrier</button>
  <button data-v="clt">📊 Classement</button>
  <button data-v="but">⚽ Buteurs</button>
 </nav>
 <div id="content"></div>
</div>
<footer>
 __NOM__ __SAISON__ · Pronostics générés par modèle IA · Résultats réels via football-data.org<br>
 Créé par <a href="https://github.com/Nico-Mtn">Nico-Mtn</a> · Projet gratuit, sans publicité, sans paris
</footer>
<script>
var DATA = /*__DATA__*/null;
var view="feed", mode="prono";
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){
 return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function logo(u){return u?'<img src="'+esc(u)+'" alt="" loading="lazy">':'';}
function head(){
 var s=DATA.stats||{},j=s.joue||0,ok=(s.exact||0)+(s.bon||0);
 document.getElementById("pct").textContent = j?((ok/j*100).toFixed(1)+" %"):"—";
 document.getElementById("scorebar").innerHTML =
  '<div class="sc"><b>'+j+'</b><span>joués</span></div>'
 +'<div class="sc ok"><b>'+(s.exact||0)+'</b><span>exacts</span></div>'
 +'<div class="sc ok"><b>'+(s.bon||0)+'</b><span>bons</span></div>'
 +'<div class="sc ko"><b>'+(s.rate||0)+'</b><span>ratés</span></div>';
 document.getElementById("maj").textContent =
  "Dernière mise à jour : "+DATA.maj+" — "+j+"/"+(s.total||0)+" matchs joués";
 document.getElementById("note").innerHTML = (mode==="prono")
  ? 'Mode <b>Prono de Nono</b> : pronostics, indice de confiance et projections IA (résultats réels inclus).'
  : 'Mode <b>Réel</b> : résultats et classement officiels, sans projection.';
}
function issueLbl(i){return i==="V"?"1":(i==="N"?"N":"2");}
function matchRow(m){
 var right="";
 if(m.reel){
  right='<div class="v">'+m.reel[0]+" – "+m.reel[1]+'</div><div class="k">score final</div>';
 }else if(mode==="prono"&&m.prono){
  right='<div class="v p">'+m.prono[0]+" – "+m.prono[1]+'</div><div class="k">pronostic</div>';
 }else{
  right='<div class="v" style="opacity:.4">–</div><div class="k">'+esc(m.heure||"à venir")+'</div>';
 }
 var b=[];
 if(m.j) b.push('<span class="b">J'+m.j+'</span>');
 if(m.date) b.push('<span class="b">'+esc(m.date)+(m.heure?" · "+esc(m.heure):"")+'</span>');
 if(mode==="prono"){
  if(m.statut==="exact") b.push('<span class="b ex">✓ exact</span>');
  else if(m.statut==="bon") b.push('<span class="b bo">✓ bon</span>');
  else if(m.statut==="rate") b.push('<span class="b ra">✗ raté</span>');
  else if(m.conf!=null) b.push('<span class="b">'+m.conf+' % · '+issueLbl(m.issue)+'</span>');
  if(!m.reel&&m.fige) b.push('<span class="b fg">prono figé</span>');
 }
 return '<div class="m"><div class="t">'+logo(m.ch)+'<b>'+esc(m.home)+'</b></div>'
 +'<div class="sc2">'+right+'</div>'
 +'<div class="t a"><b>'+esc(m.away)+'</b>'+logo(m.ca)+'</div></div>'
 +'<div class="meta">'+b.join(" ")+'</div>';
}
function feedHtml(){
 var ms=(DATA.matches||[]).slice();
 var past=ms.filter(function(m){return m.reel;}).reverse().slice(0,10);
 var next=ms.filter(function(m){return !m.reel;}).slice(0,10);
 var h="";
 if(!ms.length) return '<div class="card"><div class="empty">Calendrier bientôt disponible.</div></div>';
 if(next.length){
  h+='<div class="card"><div class="ctitle"><span class="ic">🔜</span><h3>Prochains matchs</h3></div>';
  next.forEach(function(m){h+=matchRow(m);});h+='</div>';
 }
 if(past.length){
  h+='<div class="card"><div class="ctitle"><span class="ic">✅</span><h3>Derniers résultats</h3></div>';
  past.forEach(function(m){h+=matchRow(m);});h+='</div>';
 }
 return h;
}
function calHtml(){
 var ms=DATA.matches||[];
 if(!ms.length) return '<div class="card"><div class="empty">Calendrier bientôt disponible.</div></div>';
 var by={},order=[];
 ms.forEach(function(m){var k=m.j||0;if(!by[k]){by[k]=[];order.push(k);}by[k].push(m);});
 order.sort(function(a,b){return a-b;});
 var h="";
 order.forEach(function(j){
  h+='<div class="card"><div class="ctitle"><span class="ic">'+j+'</span><h3>Journée '+j+'</h3></div>';
  by[j].forEach(function(m){h+=matchRow(m);});
  h+='</div>';
 });
 return h;
}
function tableHtml(){
 var rows=(mode==="prono")?(DATA.projected||[]):(DATA.table||[]);
 if(!rows.length) return '<div class="card"><div class="empty">Le classement s\\'affichera dès la première journée.</div></div>';
 var t='<div class="card"><div class="ctitle"><span class="ic">📊</span><h3>'
 +(mode==="prono"?"Classement projeté en fin de saison":"Classement officiel")+'</h3></div>'
 +'<table><tr><th></th><th>Équipe</th><th>J</th><th>G</th><th>N</th><th>P</th><th>Diff</th><th>Pts</th></tr>';
 rows.forEach(function(r){
  var c=r.pos<=3?"c1":(r.pos<=6?"c2":(r.pos>=16?"c3":""));
  t+='<tr class="'+c+'"><td class="n">'+r.pos+'</td><td><div class="tm">'+logo(r.crest)+esc(r.team)+'</div></td>'
  +'<td class="n">'+(r.j||0)+'</td><td class="n">'+(r.g||0)+'</td><td class="n">'+(r.n||0)+'</td>'
  +'<td class="n">'+(r.p||0)+'</td><td class="n">'+((r.diff>0?"+":"")+(r.diff||0))+'</td>'
  +'<td class="p">'+(r.pts||0)+'</td></tr>';
 });
 t+='</table>';
 if(mode==="prono") t+='<div class="maj" style="margin-top:10px">Projection : résultats acquis + pronostics des matchs à venir.</div>';
 return t+'</div>';
}
function scorersHtml(){
 var s=DATA.scorers||[];
 if(!s.length) return '<div class="card"><div class="empty">Les buteurs apparaîtront dès les premiers matchs.</div></div>';
 var mx=s[0].goals||1,h='<div class="card"><div class="ctitle"><span class="ic">⚽</span><h3>Meilleurs buteurs</h3></div><table>';
 s.forEach(function(p,i){
  h+='<tr><td class="n">'+(i+1)+'</td><td><div class="tm">'+logo(p.crest)+'<b>'+esc(p.player)+'</b></div>'
  +'<div style="height:6px;border-radius:4px;background:#eef1f8;margin-top:5px;overflow:hidden">'
  +'<span style="display:block;height:100%;width:'+Math.round((p.goals||0)/mx*100)+'%;'
  +'background:linear-gradient(90deg,#f6c453,#e8a20c)"></span></div></td>'
  +'<td style="opacity:.6;font-size:11px">'+esc(p.team)+'</td><td class="p">'+(p.goals||0)+'</td></tr>';
 });
 return h+'</table></div>';
}
function render(){
 head();
 Array.prototype.forEach.call(document.querySelectorAll("#tabs button"),function(b){
  b.classList.toggle("on",b.dataset.v===view);});
 Array.prototype.forEach.call(document.querySelectorAll(".modebar button"),function(b){
  b.classList.toggle("on",b.dataset.m===mode);});
 var c=document.getElementById("content");
 c.innerHTML = view==="feed"?feedHtml():(view==="cal"?calHtml():(view==="clt"?tableHtml():scorersHtml()));
}
Array.prototype.forEach.call(document.querySelectorAll("#tabs button"),function(b){
 b.onclick=function(){view=b.dataset.v;render();};});
Array.prototype.forEach.call(document.querySelectorAll(".modebar button"),function(b){
 b.onclick=function(){mode=b.dataset.m;render();};});
render();
</script></body></html>"""

def build_league(lg):
    """Génère la page complète d'UN championnat."""
    set_league(lg)
    os.makedirs(OUTDIR, exist_ok=True)
    m, s, b = fetch_all()
    payload = build(m, s, b)
    html = (PAGE.replace("__NAV__", nav_html(lg["slug"]))
                .replace("__NOM__", lg["nom"])
                .replace("__SAISON__", payload["saison"])
                .replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False)))
    with open(os.path.join(OUTDIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(OUTDIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    sig_src = {k: v for k, v in payload.items() if k != "maj"}
    sig = hashlib.md5(json.dumps(sig_src, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    with open(os.path.join(OUTDIR, "content.sig"), "w", encoding="utf-8") as f:
        f.write(sig)
    st = payload["stats"]
    print(f"[OK] {lg['slug']} — {len(payload['matches'])} matchs | "
          f"{st['joue']} joués : {st['exact']} exacts, {st['bon']} bons, {st['rate']} ratés")

def main():
    for lg in LEAGUES:
        try:
            build_league(lg)
        except Exception as e:
            # Un championnat en échec (API, données) ne doit pas empêcher les autres.
            print(f"[ERREUR] {lg['slug']} : {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
