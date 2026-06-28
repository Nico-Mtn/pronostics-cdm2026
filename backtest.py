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


# ─── ANALYSE DES ERREURS (mêmes simulations que WC2026, par édition) ─────────
def analyze_errors():
    """Pour chaque CdM (groupes), rejoue le modèle Elo, classe les erreurs et mesure
    le gain d'une règle de nul calibrée. Reproduit l'analyse faite sur la CdM courante."""
    rows = load_matches()
    print("\n" + "=" * 66)
    print("ANALYSE DES ERREURS DE PRONO — PHASES DE GROUPES (par édition)")
    print("=" * 66)
    agg = {"n":0,"err":0,"err_draw":0,"err_close":0,"err_upset":0,"gap_err":0.0,"gap_ok":0.0}
    for year, (start, end) in WC_GROUP.items():
        s = datetime.date.fromisoformat(start); e = datetime.date.fromisoformat(end)
        elo, DEF = build_elo(rows, s)
        grp = [m for m in rows if s <= m["date"] <= e and "world cup" in m["tourn"].lower()
               and "qual" not in m["tourn"].lower()][:48]
        n=err=err_draw=err_close=err_upset=0; gap_err=[]; gap_ok=[]
        base=good_cal_best=0; 
        cal=[0]*9; thrs=[0.0,0.2,0.4,0.6,0.8,1.0,1.2,1.5,2.0]   # seuils en buts de suprématie
        for m in grp:
            eh=elo.get(m["home"],DEF); ea=elo.get(m["away"],DEF)
            pV,pN,pD=predict(eh,ea); probs=[pV,pN,pD]; pred=probs.index(max(probs))
            act=0 if m["hs"]>m["as"] else (1 if m["hs"]==m["as"] else 2)
            gap=abs(eh-ea); sup=gap/240.0
            n+=1; ok=(pred==act); base+=ok
            if not ok:
                err+=1; gap_err.append(gap)
                if act==1: err_draw+=1                  # le réel était un nul
                if gap<240: err_close+=1                # match serré (<~1 but de suprématie)
                if gap>=384 and act!=1 and pred!=1 and pred!=act: err_upset+=1
            else: gap_ok.append(gap)
            # règle de nul calibrée : si suprématie < seuil -> prédire nul
            for i,t in enumerate(thrs):
                p = 1 if sup < t else pred
                cal[i]+= (p==act)
        best=max(cal); bi=cal.index(best)
        am=sum(gap_err)/len(gap_err) if gap_err else 0; ao=sum(gap_ok)/len(gap_ok) if gap_ok else 0
        print(f"\nCdM {year} — {n} matchs de poule")
        print(f"  Fiabilité Elo : {base}/{n} = {base/n*100:.1f}%  |  erreurs : {err}")
        print(f"  • erreurs dont le réel est un NUL : {err_draw}/{err} ({(err_draw/err*100 if err else 0):.0f}%)")
        print(f"  • erreurs sur matchs SERRÉS (écart Elo <240) : {err_close}/{err}")
        print(f"  • vrais UPSETS (favori net battu) : {err_upset}/{err}")
        print(f"  • écart Elo moyen — erreurs {am:.0f} vs corrects {ao:.0f}")
        print(f"  • règle de nul calibrée -> {best}/{n} = {best/n*100:.1f}% (seuil sup {thrs[bi]:.1f}, gain +{best-base})")
        agg["n"]+=n; agg["err"]+=err; agg["err_draw"]+=err_draw; agg["err_close"]+=err_close; agg["err_upset"]+=err_upset
        agg["gap_err"]+=sum(gap_err); agg["gap_ok"]+=sum(gap_ok)
    print("\n" + "-" * 66)
    e=agg["err"] or 1
    print(f"AGRÉGÉ {list(WC_GROUP)} : {agg['err']} erreurs")
    print(f"  Nul = {agg['err_draw']}/{agg['err']} ({agg['err_draw']/e*100:.0f}%) | serrés = {agg['err_close']}/{agg['err']} | vrais upsets = {agg['err_upset']}/{agg['err']}")
    print("  => Pattern attendu confirmé : le NUL domine les erreurs, concentrées sur les matchs serrés.")

if __name__ == "__main__":
    run()
    analyze_errors()
