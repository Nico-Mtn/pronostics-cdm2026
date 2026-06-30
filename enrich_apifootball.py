#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich_apifootball.py — Couche d'ENRICHISSEMENT Pronostix via API-Football (API-Sports).
Auteur : Nico-Mtn.

Architecture HYBRIDE : football-data.org reste le socle live (cron 25 min) ; ce script
est appelé quelques fois par jour par un workflow séparé et met en cache des données
riches dans data/af_*.json (committées au repo), consommées ensuite par update.py.

Contraintes plan gratuit : 100 requêtes/jour, 10/min, IP partagée sensible.
Garde-fous : lecture des en-têtes de quota, arrêt si réserve basse, backoff sur 429,
lissage des appels, cache (on ne redemande pas une donnée figée).

La clé est lue dans la variable d'environnement APIFOOTBALL_KEY (secret GitHub).
JAMAIS committée. Repo public : la clé ne doit apparaître nulle part.
"""
import os, sys, json, time, datetime
import urllib.request, urllib.error

import update  # réutilise le calendrier officiel (MATCH_BY_TEAMS, KO_KICKOFF_UTC, …)

API_KEY  = os.environ.get("APIFOOTBALL_KEY", "").strip()
BASE     = "https://v3.football.api-sports.io"
LEAGUE   = 1
SEASON   = 2026
ROOT     = os.path.dirname(os.path.abspath(__file__))
DATA     = os.path.join(ROOT, "data")
SAFETY_REMAINING = 15     # on s'arrête si le quota journalier restant passe sous ce seuil
MAX_CALLS_PER_RUN = 40    # plafond dur par exécution (sécurité supplémentaire)

# ── Correspondance noms anglais (API-Football) -> noms FR (Pronostix) ────────
# Best-effort + alias. Toute équipe non mappée est LOGGÉE pour correction rapide.
EN_FR = {
    "South Africa":"Afrique du Sud", "Algeria":"Algérie", "Germany":"Allemagne",
    "England":"Angleterre", "Saudi Arabia":"Arabie Saoudite", "Argentina":"Argentine",
    "Australia":"Australie", "Austria":"Autriche", "Belgium":"Belgique",
    "Bosnia and Herzegovina":"Bosnie-Herzégovine", "Bosnia & Herzegovina":"Bosnie-Herzégovine",
    "Brazil":"Brésil", "Canada":"Canada", "Cape Verde Islands":"Cap-Vert",
    "Cape Verde":"Cap-Vert", "Cabo Verde":"Cap-Vert", "Colombia":"Colombie",
    "South Korea":"Corée du Sud", "Korea Republic":"Corée du Sud", "Croatia":"Croatie",
    "Curacao":"Curaçao", "Curaçao":"Curaçao", "Ivory Coast":"Côte d'Ivoire",
    "Cote d'Ivoire":"Côte d'Ivoire", "Spain":"Espagne", "France":"France", "Ghana":"Ghana",
    "Haiti":"Haïti", "Iraq":"Irak", "Iran":"Iran", "Japan":"Japon", "Jordan":"Jordanie",
    "Morocco":"Maroc", "Mexico":"Mexique", "Norway":"Norvège", "New Zealand":"Nouvelle-Zélande",
    "Uzbekistan":"Ouzbékistan", "Panama":"Panama", "Paraguay":"Paraguay",
    "Netherlands":"Pays-Bas", "Portugal":"Portugal", "Qatar":"Qatar",
    "DR Congo":"RD Congo", "Congo DR":"RD Congo", "Switzerland":"Suisse", "Sweden":"Suède",
    "Senegal":"Sénégal", "Czech Republic":"Tchéquie", "Czechia":"Tchéquie",
    "Tunisia":"Tunisie", "Turkey":"Turquie", "Türkiye":"Turquie", "Uruguay":"Uruguay",
    "Scotland":"Écosse", "Egypt":"Égypte", "Ecuador":"Équateur", "USA":"États-Unis",
    "United States":"États-Unis",
}
def to_fr(name):
    if not name: return None
    if name in EN_FR: return EN_FR[name]
    n=name.strip()
    if n in EN_FR: return EN_FR[n]
    # normalisation accents/casse
    low=n.lower()
    for k,v in EN_FR.items():
        if k.lower()==low: return v
    return None

# Tranches d'ids par tour KO (mêmes plages que update.py / fetch_from_api)
KO_ROUNDS = {
    "Round of 32":     list(range(73,89)),
    "Round of 16":     list(range(89,97)),
    "Quarter-finals":  [97,98,99,100],
    "Semi-finals":     [101,102],
    "Final":           [104],
    "3rd Place Final": [103],
}
def norm_round(r):
    r=(r or "").lower()
    if "round of 32" in r or "last 32" in r: return "Round of 32"
    if "round of 16" in r or "last 16" in r or "8th" in r: return "Round of 16"
    if "quarter" in r: return "Quarter-finals"
    if "semi" in r: return "Semi-finals"
    if "3rd" in r or "third" in r: return "3rd Place Final"
    if "final" in r: return "Final"
    return None

_calls=[0]
def api_get(path, params):
    """GET API-Football avec garde-fous quota. Retourne (json|None)."""
    if not API_KEY:
        print("[AF] APIFOOTBALL_KEY absente — abandon.", file=sys.stderr); return None
    if _calls[0] >= MAX_CALLS_PER_RUN:
        print(f"[AF] Plafond de {MAX_CALLS_PER_RUN} appels/run atteint — arrêt.", file=sys.stderr); return None
    qs="&".join(f"{k}={urllib.parse.quote(str(v))}" for k,v in params.items())
    url=f"{BASE}/{path}?{qs}"
    for attempt in range(4):
        req=urllib.request.Request(url, headers={"x-apisports-key":API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                _calls[0]+=1
                day_rem=resp.headers.get("x-ratelimit-requests-remaining")
                if day_rem is not None:
                    try:
                        if int(day_rem) < SAFETY_REMAINING:
                            print(f"[AF] Réserve journalière basse ({day_rem}) — on garde la marge.", file=sys.stderr)
                    except ValueError: pass
                data=json.loads(resp.read().decode("utf-8"))
                time.sleep(7)   # lissage : ≤ ~9/min, marge sous la limite 10/min
                return data
        except urllib.error.HTTPError as e:
            if e.code==429:
                wait=[5,15,30][min(attempt,2)]
                print(f"[AF] 429 — backoff {wait}s", file=sys.stderr); time.sleep(wait); continue
            print(f"[AF] HTTP {e.code} sur {path}", file=sys.stderr); return None
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"[AF] réseau {e} sur {path}", file=sys.stderr); time.sleep(5)
    return None

def _read(name):
    p=os.path.join(DATA,name)
    if os.path.exists(p):
        try:
            with open(p,encoding="utf-8") as f: return json.load(f)
        except Exception: return {}
    return {}

def _write(name, obj):
    os.makedirs(DATA, exist_ok=True)
    obj=dict(obj); obj["_meta"]={"author":"Nico-Mtn","source":"API-Football v3",
        "updated":datetime.datetime.utcnow().isoformat()+"Z",
        "note":"Cache d'enrichissement. Crédit créateur apprécié si réutilisé (Nico-Mtn)."}
    with open(os.path.join(DATA,name),"w",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2)

def map_fixtures(fixtures):
    """API /fixtures -> dict {numéro FIFA(str): champs utiles}.
    Groupes : par paire d'équipes (FR). KO : par tour + chronologie."""
    out={}; unmapped=[]
    ko_by_round={}
    for fx in fixtures:
        teams=fx.get("teams") or {}; hn=(teams.get("home") or {}).get("name"); an=(teams.get("away") or {}).get("name")
        fr_h, fr_a = to_fr(hn), to_fr(an)
        rnd=norm_round(((fx.get("league") or {}).get("round")))
        rec=_extract(fx, fr_h, fr_a)
        if fr_h and fr_a and frozenset((fr_h,fr_a)) in update.MATCH_BY_TEAMS:
            mid,_,_=update.MATCH_BY_TEAMS[frozenset((fr_h,fr_a))]
            out[str(mid)]=rec
        elif rnd in KO_ROUNDS:
            ko_by_round.setdefault(rnd,[]).append((fx.get("fixture",{}).get("date",""), rec))
        else:
            unmapped.append(f"{hn} vs {an} [{(fx.get('league') or {}).get('round')}]")
    # KO : on apparie les fixtures du tour (triées par date) aux ids du tour
    # (triés par horaire officiel KO_KICKOFF_UTC) -> chaque fixture tombe sur son n° FIFA.
    for rnd, lst in ko_by_round.items():
        ids=sorted(KO_ROUNDS[rnd], key=lambda m: update.KO_KICKOFF_UTC.get(m,"9999"))
        lst.sort(key=lambda x:x[0])
        for i,(_,rec) in enumerate(lst):
            if i<len(ids): out[str(ids[i])]=rec
    if unmapped:
        print(f"[AF] {len(unmapped)} fixture(s) non mappée(s) : "+" ; ".join(unmapped[:10]), file=sys.stderr)
    return out

def _extract(fx, fr_h, fr_a):
    f=fx.get("fixture") or {}; sc=fx.get("score") or {}; goals=fx.get("goals") or {}
    ft=sc.get("fulltime") or {}; et=sc.get("extratime") or {}; pen=sc.get("penalty") or {}
    ven=f.get("venue") or {}; teams=fx.get("teams") or {}
    # score "sur le terrain" (hors t.a.b.) : prolongation si présente, sinon temps plein
    lvl_h = et.get("home") if et.get("home") is not None else ft.get("home")
    lvl_a = et.get("away") if et.get("away") is not None else ft.get("away")
    win=None
    if (teams.get("home") or {}).get("winner") is True: win="home"
    elif (teams.get("away") or {}).get("winner") is True: win="away"
    return {
        "fid":f.get("id"), "home_fr":fr_h, "away_fr":fr_a,
        "date":f.get("date"), "status":(f.get("status") or {}).get("short"),
        "venue":ven.get("name"), "city":ven.get("city"),
        "sh":lvl_h, "sa":lvl_a,
        "penh":pen.get("home"), "pena":pen.get("away"),
        "winner":win,
    }

def build_injuries(rows):
    """API /injuries -> dict {équipe FR: [ {player, type, reason} ]}."""
    out={}
    for r in rows or []:
        team=to_fr(((r.get("team") or {}).get("name")))
        pl=(r.get("player") or {})
        if not team: continue
        out.setdefault(team,[]).append({
            "player":pl.get("name"), "type":pl.get("type"), "reason":pl.get("reason")})
    return out

def main():
    if not API_KEY:
        print("[AF] Pas de clé APIFOOTBALL_KEY : rien à faire (le site continue sur football-data).")
        return 0
    print("[AF] Enrichissement API-Football…")
    # 1) Fixtures (calendrier + venue + t.a.b.)
    fixtures_resp=api_get("fixtures", {"league":LEAGUE,"season":SEASON})
    if fixtures_resp and fixtures_resp.get("response"):
        af_fix=map_fixtures(fixtures_resp["response"])
        prev=_read("af_fixtures.json"); prev.pop("_meta",None)
        prev.update(af_fix)   # on conserve l'historique, on met à jour
        _write("af_fixtures.json", prev)
        print(f"[AF] af_fixtures.json : {len(af_fix)} match(s) mappé(s).")
    # 2) Blessés / suspendus (tout le tournoi en 1 appel)
    inj_resp=api_get("injuries", {"league":LEAGUE,"season":SEASON})
    if inj_resp is not None:
        _write("af_injuries.json", build_injuries(inj_resp.get("response")))
        print(f"[AF] af_injuries.json mis à jour.")
    print(f"[AF] Terminé — {_calls[0]} appel(s) consommé(s) ce run.")
    return 0

if __name__=="__main__":
    sys.exit(main())
