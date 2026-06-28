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
Pronostix — Boucle d'AUTO-CALIBRATION (apprentissage continu). Hors update.py, offline.

Principe : plus on accumule de résultats réels, plus le modèle s'affûte. learn.py ajuste
les paramètres apprenables (data/calibration.json) à partir des résultats disponibles, en
se protégeant du sur-apprentissage par VALIDATION CROISÉE (leave-one-group-out).

Ne réécrit JAMAIS le passé : le prono noté reste figé. Les paramètres appris servent aux
FUTURS pronos (phases finales en cours, et phases de groupes des prochaines éditions).

Sources :
  • Résultats de la CdM en cours : data/results_manual.json (toujours dispo).
  • CdM passées : dataset CC0 (martj42) via backtest.py si présent (enrichit l'échantillon).

Usage : python3 learn.py   (puis committer data/calibration.json mis à jour)
"""
import os, json, sys
ROOT = os.path.dirname(os.path.abspath(__file__))
import importlib.util
spec = importlib.util.spec_from_file_location("u", os.path.join(ROOT, "update.py"))
u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)

def group_samples():
    """(|diff|, prono_issue, issue_réelle) pour chaque match de poule joué de la CdM courante,
    + le groupe (pour la validation croisée). prono = compute(h,a,None) (modèle figé)."""
    res = json.load(open(os.path.join(ROOT, "data", "results_manual.json")))["resultats"]
    S = []
    for mid, grp, date, h, a in u.GROUP_MATCHES:
        r = res.get(str(mid))
        if not r: continue
        ph, pa, diff = u.compute(h, a, None)
        po = 0 if ph > pa else (1 if ph < pa else 2)
        ro = 0 if r["h"] > r["a"] else (1 if r["h"] < r["a"] else 2)
        S.append((abs(diff), po, ro, grp))
    return S

def score(samples, band):
    good = 0
    for ad, po, ro, grp in samples:
        pred = 2 if ad < band else po
        good += (pred == ro)
    return good

def fit_draw_band(samples):
    """Choisit la bande de nul par validation croisée leave-one-group-out (anti-overfit)."""
    bands = [0.0, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
    groups = sorted(set(s[3] for s in samples))
    cv = {b: 0 for b in bands}
    for g in groups:                                   # held-out group g
        train = [s for s in samples if s[3] != g]
        test  = [s for s in samples if s[3] == g]
        best_b = max(bands, key=lambda b: score(train, b))   # apprend sur le reste
        cv[best_b] += score(test, best_b)                    # évalue sur le groupe tenu à part
    # bande retenue = celle qui maximise la perf hors-échantillon cumulée
    best = max(bands, key=lambda b: cv[b])
    n = len(samples)
    base = score(samples, 0.0); fitted = score(samples, best)
    return best, base, fitted, n

def main():
    S = group_samples()
    if not S:
        print("Aucun résultat de poule disponible."); return
    band, base, fitted, n = fit_draw_band(S)
    path = os.path.join(ROOT, "data", "calibration.json")
    cal = json.load(open(path))
    cal["group_draw_band"] = round(band, 3)
    cal["_meta"]["updated"] = __import__("datetime").date.today().isoformat()
    cal["_meta"]["fitted_on"] = f"{n} matchs de poule (CdM courante), validation croisée LOGO"
    json.dump(cal, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Échantillon : {n} matchs de poule")
    print(f"Bande de nul retenue (CV anti-overfit) : {band:.2f}")
    print(f"Fiabilité in-sample : base {base}/{n} = {base/n*100:.1f}%  ->  calibrée {fitted}/{n} = {fitted/n*100:.1f}%")
    print(f"calibration.json mis à jour. (KO : nécessite l'historique CC0 pour affiner — defaults conservés.)")

if __name__ == "__main__":
    main()
