# -*- coding: utf-8 -*-
"""
Pronostix — Lot 0 : harnais de backtest (HORS update.py, offline, exécution manuelle).

Mesure la VRAIE baseline de précision de DIRECTION (V/N/D) du modèle V3
(Elo + Dixon-Coles) sur la phase de groupes des Coupes du Monde 2010-2022,
match par match (jamais sur des distributions agrégées — invalide pour Brier/log-loss).

Données : dataset CC0 « International football results 1872→présent » (martj42).
Téléchargé UNE fois puis mis en cache local (backtest_results.csv). Aucune dépendance
au runtime de l'app : ce script ne sert qu'à mesurer/chiffrer les leviers.

Métriques : précision direction (métrique cible), Brier score multi-classe, log-loss.
Usage : python3 backtest.py
"""
import os, sys, csv, math, urllib.request, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_LOCAL = os.path.join(ROOT, "backtest_results.csv")
CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"

# Fenêtres officielles des phases de GROUPES (48 matchs, format 32 équipes 2010-2022)
WC_GROUP = {
    2010: ("2010-06-11", "2010-06-25"),
    2014: ("2014-06-12", "2014-06-26"),
    2018: ("2018-06-14", "2018-06-28"),
    2022: ("2022-11-20", "2022-12-02"),
}

# ─── Données ─────────────────────────────────────────────────────────────────
def ensure_csv():
    if os.path.exists(CSV_LOCAL):
        return
    print(f"[dl] téléchargement unique du dataset CC0 → {CSV_LOCAL}", file=sys.stderr)
    urllib.request.urlretrieve(CSV_URL, CSV_LOCAL)

def load_matches():
    ensure_csv()
    rows = []
    with open(CSV_LOCAL, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                d = datetime.date.fromisoformat(r["date"])
                hs = int(r["home_score"]); as_ = int(r["away_score"])
            except (ValueError, TypeError):
                continue
            rows.append({"date": d, "home": r["home_team"], "away": r["away_team"],
                         "hs": hs, "as": as_, "tourn": r["tournament"],
                         "neutral": (r.get("neutral", "").lower() == "true")})
    rows.sort(key=lambda x: x["date"])
    return rows

# ─── Moteur Elo (style World Football Elo) ───────────────────────────────────
HOME_ADV = 100.0
def k_factor(tourn):
    t = tourn.lower()
    if "world cup" in t and "qual" not in t: return 60.0
    if "world cup qual" in t or "uefa euro" in t or "copa am" in t or "african cup" in t or "afc asian" in t: return 40.0
    if "friendly" in t: return 20.0
    return 30.0
def mov_mult(gd):
    gd = abs(gd)
    if gd <= 1: return 1.0
    if gd == 2: return 1.5
    return (11.0 + gd) / 8.0

def build_elo(rows, until):
    elo = {}
    DEF = 1500.0
    for m in rows:
        if m["date"] >= until: break
        h, a = m["home"], m["away"]
        eh = elo.get(h, DEF); ea = elo.get(a, DEF)
        ha = 0.0 if m["neutral"] else HOME_ADV
        we = 1.0 / (1.0 + 10 ** (-((eh + ha) - ea) / 400.0))
        gd = m["hs"] - m["as"]
        res = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
        k = k_factor(m["tourn"]) * mov_mult(gd)
        delta = k * (res - we)
        elo[h] = eh + delta; elo[a] = ea - delta
    return elo, DEF

# ─── Modèle de prédiction V3 (Elo + Dixon-Coles), identique à update.py ──────
RHO = -0.13
def _pois(k, lam): return math.exp(-lam) * lam ** k / math.factorial(k)
def _tau(x, y, lh, la):
    if x == 0 and y == 0: return 1 - lh*la*RHO
    if x == 0 and y == 1: return 1 + lh*RHO
    if x == 1 and y == 0: return 1 + la*RHO
    if x == 1 and y == 1: return 1 - RHO
    return 1.0
def predict(eh, ea):
    d = eh - ea
    sup = max(-2.6, min(2.6, d / 200.0)); mu = 2.6
    lh = max(0.16, (mu + sup) / 2.0); la = max(0.16, (mu - sup) / 2.0)
    pV = pN = pD = 0.0
    for x in range(9):
        for y in range(9):
            p = _pois(x, lh) * _pois(y, la) * _tau(x, y, lh, la)
            if x > y: pV += p
            elif x == y: pN += p
            else: pD += p
    tot = pV + pN + pD
    return pV/tot, pN/tot, pD/tot

# ─── Backtest ────────────────────────────────────────────────────────────────
def actual(m): return 0 if m["hs"] > m["as"] else (1 if m["hs"] == m["as"] else 2)

def run():
    rows = load_matches()
    tot_n = tot_hit = 0; brier_sum = 0.0; ll_sum = 0.0
    print(f"\n{'CM':<6}{'matchs':>7}{'direction':>12}{'Brier':>9}{'logloss':>9}")
    print("-" * 43)
    for year, (start, end) in WC_GROUP.items():
        s = datetime.date.fromisoformat(start); e = datetime.date.fromisoformat(end)
        elo, DEF = build_elo(rows, s)
        grp = [m for m in rows if s <= m["date"] <= e and "world cup" in m["tourn"].lower()
               and "qual" not in m["tourn"].lower()][:48]
        n = hit = 0; b = 0.0; ll = 0.0
        for m in grp:
            eh = elo.get(m["home"], DEF); ea = elo.get(m["away"], DEF)
            pV, pN, pD = predict(eh, ea)
            probs = [pV, pN, pD]; pred = probs.index(max(probs)); act = actual(m)
            n += 1; hit += (pred == act)
            b += sum((probs[k] - (1.0 if k == act else 0.0)) ** 2 for k in range(3))
            ll += -math.log(max(1e-9, probs[act]))
        if n:
            print(f"{year:<6}{n:>7}{hit/n*100:>11.1f}%{b/n:>9.3f}{ll/n:>9.3f}")
            tot_n += n; tot_hit += hit; brier_sum += b; ll_sum += ll
    print("-" * 43)
    if tot_n:
        print(f"{'TOTAL':<6}{tot_n:>7}{tot_hit/tot_n*100:>11.1f}%{brier_sum/tot_n:>9.3f}{ll_sum/tot_n:>9.3f}")
        print(f"\nPrécision DIRECTION (métrique cible) : {tot_hit/tot_n*100:.1f}% sur {tot_n} matchs de poule (CM 2010-2022).")
        print("Repère : top-pick 1/N/2, bons modèles internationaux ~50-55% sur ligues équilibrées ; CM plus favorable.")

if __name__ == "__main__":
    run()
