# -*- coding: utf-8 -*-
# ============================================================================
#  Pronostix — Pronostics IA Coupe du Monde 2026
#  Auteur / Author : Nico-Mtn — https://github.com/Nico-Mtn
#  Projet gratuit, sans publicité, sans paris.
#  Réutilisation libre : un CRÉDIT au créateur (Nico-Mtn) serait grandement
#  apprécié. / If you reuse this model or code, a credit to the creator
#  (Nico-Mtn) would be greatly appreciated.
# ============================================================================
"""
Pronostix — Générateur de statistiques figées (V3.1, HORS update.py, offline).

Régénère, depuis le dataset CC0 « International football results 1872→présent »
(martj42), les trois snapshots committés utilisés par le modèle de phase finale :

  • data/team_form.json  : forme récente (≈50 derniers matchs) attaque/défense par équipe
  • data/h2h.json        : tendances des confrontations directes (bilan, suprématie, buts)
  • calibration mu        : total de buts/match des 250 derniers matchs de Coupe du Monde

Aucune dépendance réseau au runtime de l'app : on télécharge UNE fois, on fige, on commit.
Mapping noms anglais (dataset) → noms FR de l'app via NAME_MAP ci-dessous.

Usage : python3 build_stats.py   (nécessite un accès réseau ; le sandbox de dev le bloque)
"""
import os, sys, csv, json, urllib.request, datetime
from collections import defaultdict, deque

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_LOCAL = os.path.join(ROOT, "backtest_results.csv")
CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SNAPSHOT_DATE = "2026-06-11"
FORM_WINDOW = 50          # derniers matchs par équipe
WC_CALIB_N = 250          # derniers matchs de CdM pour calibrer le total de buts

# Noms dataset (anglais) -> noms FR de l'app (48 équipes du tournoi)
NAME_MAP = {
    "Spain":"Espagne","Argentina":"Argentine","France":"France","England":"Angleterre","Brazil":"Brésil",
    "Portugal":"Portugal","Netherlands":"Pays-Bas","Belgium":"Belgique","Germany":"Allemagne","Croatia":"Croatie",
    "Colombia":"Colombie","Uruguay":"Uruguay","Morocco":"Maroc","Switzerland":"Suisse","Japan":"Japon",
    "Senegal":"Sénégal","United States":"États-Unis","USA":"États-Unis","Mexico":"Mexique","Norway":"Norvège",
    "Iran":"Iran","Turkey":"Turquie","Türkiye":"Turquie","Ecuador":"Équateur","Austria":"Autriche","Algeria":"Algérie",
    "Sweden":"Suède","South Korea":"Corée du Sud","Korea Republic":"Corée du Sud","Australia":"Australie","Egypt":"Égypte",
    "Ivory Coast":"Côte d'Ivoire","Scotland":"Écosse","Canada":"Canada","Paraguay":"Paraguay","Tunisia":"Tunisie",
    "Bosnia and Herzegovina":"Bosnie-Herzégovine","Ghana":"Ghana","DR Congo":"RD Congo","Qatar":"Qatar","Panama":"Panama",
    "Cape Verde":"Cap-Vert","Uzbekistan":"Ouzbékistan","South Africa":"Afrique du Sud","Saudi Arabia":"Arabie Saoudite",
    "Iraq":"Irak","Jordan":"Jordanie","Czech Republic":"Tchéquie","Czechia":"Tchéquie","Curaçao":"Curaçao",
    "Haiti":"Haïti","New Zealand":"Nouvelle-Zélande",
}
TEAMS = set(NAME_MAP.values())

def ensure_csv():
    if not os.path.exists(CSV_LOCAL):
        print(f"[dl] téléchargement unique du dataset CC0 → {CSV_LOCAL}", file=sys.stderr)
        urllib.request.urlretrieve(CSV_URL, CSV_LOCAL)

def load_matches():
    ensure_csv()
    rows = []
    with open(CSV_LOCAL, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                d = datetime.date.fromisoformat(r["date"]); hs=int(r["home_score"]); as_=int(r["away_score"])
            except (ValueError, TypeError): continue
            rows.append({"date":d,"home":r["home_team"],"away":r["away_team"],"hs":hs,"as":as_,"tourn":r["tournament"]})
    rows.sort(key=lambda x:x["date"])
    return rows

def fr(name): return NAME_MAP.get(name)

def build_form(rows):
    last = defaultdict(lambda: deque(maxlen=FORM_WINDOW))   # team -> (gf,ga)
    for m in rows:
        h, a = fr(m["home"]), fr(m["away"])
        if h: last[h].append((m["hs"], m["as"]))
        if a: last[a].append((m["as"], m["hs"]))
    form = {}
    for t, dq in last.items():
        if not dq: continue
        gf = sum(x[0] for x in dq) / len(dq); ga = sum(x[1] for x in dq) / len(dq)
        form[t] = {"gf": round(gf, 2), "ga": round(ga, 2), "n": len(dq)}
    return form

def build_h2h(rows):
    agg = defaultdict(lambda: {"n":0,"gA":0,"gB":0,"wA":0,"wB":0})   # key A|B (triés), A<B
    for m in rows:
        h, a = fr(m["home"]), fr(m["away"])
        if not h or not a or h == a: continue
        A, B = sorted([h, a]); key = A + "|" + B
        gh, ga = (m["hs"], m["as"]) if h == A else (m["as"], m["hs"])
        d = agg[key]; d["n"] += 1; d["gA"] += gh; d["gB"] += ga
        if gh > ga: d["wA"] += 1
        elif ga > gh: d["wB"] += 1
    h2h = {}
    for key, d in agg.items():
        if d["n"] < 4: continue   # bilan significatif uniquement
        A, B = key.split("|")
        diff = (d["wA"] - d["wB"]) / d["n"]
        fav = A if diff > 0 else (B if diff < 0 else None)
        edge = round(min(0.30, abs(diff) * 0.30), 3)
        goals = round(min(0.30, max(-0.30, ((d["gA"] + d["gB"]) / d["n"] - 2.6) * 0.25)), 3)
        if fav and edge >= 0.03:
            h2h[key] = {"fav": fav, "edge": edge, "goals": goals, "n": d["n"]}
    return h2h

def calib_mu(rows):
    wc = [m for m in rows if "world cup" in m["tourn"].lower() and "qual" not in m["tourn"].lower()]
    wc = wc[-WC_CALIB_N:]
    if not wc: return None
    avg = sum(m["hs"] + m["as"] for m in wc) / len(wc)
    return round(avg, 3), len(wc)

def main():
    rows = load_matches()
    form = build_form(rows); h2h = build_h2h(rows); mu = calib_mu(rows)
    json.dump({"_meta":{"source":"dataset CC0 martj42","snapshot_date":SNAPSHOT_DATE,
               "window":FORM_WINDOW,"fields":"gf/ga = buts pour/contre par match"},"form":form},
              open(os.path.join(ROOT,"data","team_form.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    json.dump({"_meta":{"source":"dataset CC0 martj42","snapshot_date":SNAPSHOT_DATE,
               "key":"A|B triés ; fav/edge/goals"},"h2h":h2h},
              open(os.path.join(ROOT,"data","h2h.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print(f"team_form.json : {len(form)} équipes (fenêtre {FORM_WINDOW})")
    print(f"h2h.json       : {len(h2h)} duels (≥4 confrontations)")
    if mu: print(f"Calibration mu : moyenne {mu[0]} buts/match sur les {mu[1]} derniers matchs de CdM")
    print("→ Ajuster KO_MU dans update.py si la calibration diffère sensiblement.")

if __name__ == "__main__":
    main()
