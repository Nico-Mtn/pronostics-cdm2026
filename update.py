# -*- coding: utf-8 -*-
"""
Pronostics IA — Coupe du Monde 2026
Récupère les scores réels via API-Football, calcule la dynamique (momentum)
des sélections, met à jour les pronostics des matchs à venir et génère index.html.

Lancé quotidiennement par GitHub Actions. Fonctionne aussi sans clé API
(mode repli) en lisant data/results_manual.json.
"""

import os, json, sys, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.environ.get("FOOTBALLDATA_KEY", "").strip()
API_BASE = "https://api.football-data.org/v4"
WC_CODE = "WC"        # football-data.org : code compétition FIFA World Cup

# ─── DONNÉES ÉQUIPES (force, tendance, style, surprise) ──────────────────────
TEAM_DATA = {
    "Mexique": (7.2,"up","pressing",False), "Afrique du Sud": (5.2,"stable","bloc_bas",False),
    "Corée du Sud": (6.7,"up","contre",True), "Tchéquie": (5.8,"down","bloc_moyen",False),
    "Canada": (6.8,"up","pressing",True), "Bosnie-Herzégovine": (5.3,"down","bloc_moyen",False),
    "Qatar": (5.0,"stable","possession",False), "Suisse": (7.0,"stable","bloc_moyen",False),
    "Brésil": (8.3,"up","possession",False), "Maroc": (7.6,"up","bloc_bas",True),
    "Haïti": (4.6,"stable","bloc_bas",True), "Écosse": (5.9,"stable","pressing",False),
    "États-Unis": (7.1,"up","contre",False), "Paraguay": (5.4,"stable","bloc_bas",False),
    "Australie": (6.1,"stable","bloc_moyen",False), "Turquie": (6.6,"up","contre",True),
    "Allemagne": (8.0,"up","possession",False), "Curaçao": (3.8,"stable","bloc_bas",False),
    "Côte d'Ivoire": (6.6,"up","contre",True), "Équateur": (6.2,"stable","bloc_bas",False),
    "Pays-Bas": (7.6,"stable","possession",False), "Japon": (7.2,"up","pressing",True),
    "Suède": (6.4,"up","contre",False), "Tunisie": (5.6,"up","bloc_bas",True),
    "Belgique": (7.4,"down","possession",False), "Égypte": (6.1,"stable","contre",True),
    "Iran": (6.0,"stable","bloc_bas",False), "Nouvelle-Zélande": (4.8,"stable","bloc_bas",False),
    "Espagne": (9.0,"up","possession",False), "Cap-Vert": (5.6,"up","contre",True),
    "Arabie Saoudite": (5.8,"stable","bloc_moyen",False), "Uruguay": (7.1,"stable","bloc_moyen",False),
    "France": (8.6,"stable","contre",False), "Sénégal": (7.0,"stable","pressing",True),
    "Irak": (4.9,"stable","bloc_bas",False), "Norvège": (7.2,"up","contre",True),
    "Argentine": (9.1,"stable","possession",False), "Algérie": (6.0,"up","contre",True),
    "Autriche": (6.4,"stable","pressing",False), "Jordanie": (5.1,"up","bloc_bas",True),
    "Portugal": (8.1,"stable","contre",False), "RD Congo": (5.6,"up","contre",True),
    "Ouzbékistan": (5.0,"up","bloc_moyen",False), "Colombie": (7.2,"up","pressing",True),
    "Angleterre": (8.2,"stable","bloc_moyen",False), "Croatie": (6.9,"down","possession",False),
    "Ghana": (5.6,"stable","contre",True), "Panama": (5.0,"stable","bloc_bas",False),
}
STYLE_FR = {"pressing":"Pressing haut","bloc_bas":"Bloc bas","bloc_moyen":"Bloc médian","contre":"Contre-attaque","possession":"Possession"}
HOST_NATIONS = ["États-Unis","Canada","Mexique"]
HOST_BONUS = 0.25
# Codes pays ISO 3166 pour flagcdn.com (images fiables, gère Écosse/Angleterre via gb-sct/gb-eng)
FLAG_CODES = {
    "Mexique":"mx","Afrique du Sud":"za","Corée du Sud":"kr","Tchéquie":"cz","Canada":"ca",
    "Bosnie-Herzégovine":"ba","Qatar":"qa","Suisse":"ch","Brésil":"br","Maroc":"ma","Haïti":"ht",
    "Écosse":"gb-sct","États-Unis":"us","Paraguay":"py","Australie":"au","Turquie":"tr","Allemagne":"de",
    "Curaçao":"cw","Côte d'Ivoire":"ci","Équateur":"ec","Pays-Bas":"nl","Japon":"jp","Suède":"se",
    "Tunisie":"tn","Belgique":"be","Égypte":"eg","Iran":"ir","Nouvelle-Zélande":"nz","Espagne":"es",
    "Cap-Vert":"cv","Arabie Saoudite":"sa","Uruguay":"uy","France":"fr","Sénégal":"sn","Irak":"iq",
    "Norvège":"no","Argentine":"ar","Algérie":"dz","Autriche":"at","Jordanie":"jo","Portugal":"pt",
    "RD Congo":"cd","Ouzbékistan":"uz","Colombie":"co","Angleterre":"gb-eng","Croatie":"hr","Ghana":"gh","Panama":"pa",
}


# ─── CORRESPONDANCE NOMS API (anglais) → NOMS FR ─────────────────────────────
API_NAME_MAP = {
    "mexico":"Mexique","south africa":"Afrique du Sud","south korea":"Corée du Sud","korea republic":"Corée du Sud",
    "czechia":"Tchéquie","czech republic":"Tchéquie","canada":"Canada","bosnia and herzegovina":"Bosnie-Herzégovine",
    "bosnia & herzegovina":"Bosnie-Herzégovine","qatar":"Qatar","switzerland":"Suisse","brazil":"Brésil",
    "morocco":"Maroc","haiti":"Haïti","scotland":"Écosse","usa":"États-Unis","united states":"États-Unis",
    "paraguay":"Paraguay","australia":"Australie","turkey":"Turquie","türkiye":"Turquie","turkiye":"Turquie",
    "germany":"Allemagne","curacao":"Curaçao","curaçao":"Curaçao","ivory coast":"Côte d'Ivoire","cote d'ivoire":"Côte d'Ivoire",
    "côte d'ivoire":"Côte d'Ivoire","ecuador":"Équateur","netherlands":"Pays-Bas","japan":"Japon","sweden":"Suède",
    "tunisia":"Tunisie","belgium":"Belgique","egypt":"Égypte","iran":"Iran","new zealand":"Nouvelle-Zélande",
    "spain":"Espagne","cape verde":"Cap-Vert","cabo verde":"Cap-Vert","cape verde islands":"Cap-Vert",
    "saudi arabia":"Arabie Saoudite","uruguay":"Uruguay","france":"France","senegal":"Sénégal","iraq":"Irak",
    "norway":"Norvège","argentina":"Argentine","algeria":"Algérie","austria":"Autriche","jordan":"Jordanie",
    "portugal":"Portugal","dr congo":"RD Congo","congo dr":"RD Congo","democratic republic of congo":"RD Congo",
    "uzbekistan":"Ouzbékistan","colombia":"Colombie","england":"Angleterre","croatia":"Croatie","ghana":"Ghana","panama":"Panama",
    # variantes football-data.org (noms officiels / FIFA)
    "korea republic":"Corée du Sud","republic of korea":"Corée du Sud","ir iran":"Iran","iran (islamic republic)":"Iran",
    "united states of america":"États-Unis","cape verde islands":"Cap-Vert","republic of ireland":"Irlande",
    "congo democratic republic":"RD Congo","dr congo (kinshasa)":"RD Congo","türkiye (turkey)":"Turquie",
    "south korea republic":"Corée du Sud","bosnia-herzegovina":"Bosnie-Herzégovine","côte d’ivoire":"Côte d'Ivoire",
}
# correspondance par code TLA (3 lettres) en repli, si le nom n'est pas reconnu
TLA_MAP = {
    "MEX":"Mexique","RSA":"Afrique du Sud","KOR":"Corée du Sud","CZE":"Tchéquie","CAN":"Canada",
    "BIH":"Bosnie-Herzégovine","QAT":"Qatar","SUI":"Suisse","BRA":"Brésil","MAR":"Maroc","HAI":"Haïti",
    "SCO":"Écosse","USA":"États-Unis","PAR":"Paraguay","AUS":"Australie","TUR":"Turquie","GER":"Allemagne",
    "CUW":"Curaçao","CIV":"Côte d'Ivoire","ECU":"Équateur","NED":"Pays-Bas","JPN":"Japon","SWE":"Suède",
    "TUN":"Tunisie","BEL":"Belgique","EGY":"Égypte","IRN":"Iran","NZL":"Nouvelle-Zélande","ESP":"Espagne",
    "CPV":"Cap-Vert","KSA":"Arabie Saoudite","URU":"Uruguay","FRA":"France","SEN":"Sénégal","IRQ":"Irak",
    "NOR":"Norvège","ARG":"Argentine","ALG":"Algérie","AUT":"Autriche","JOR":"Jordanie","POR":"Portugal",
    "COD":"RD Congo","UZB":"Ouzbékistan","COL":"Colombie","ENG":"Angleterre","CRO":"Croatie","GHA":"Ghana","PAN":"Panama",
}
def map_team(api_name, tla=None):
    if api_name:
        key=api_name.strip().lower()
        if key in API_NAME_MAP: return API_NAME_MAP[key]
        # tolérance : retirer les parenthèses, normaliser les apostrophes
        norm=key.replace("’","'").split("(")[0].strip()
        if norm in API_NAME_MAP: return API_NAME_MAP[norm]
    if tla and tla.upper() in TLA_MAP:
        return TLA_MAP[tla.upper()]
    return None

# ─── MATCHS DE GROUPE ────────────────────────────────────────────────────────
GROUP_MATCHES = [
    (1,"A","2026-06-11","Mexique","Afrique du Sud"),(2,"A","2026-06-11","Corée du Sud","Tchéquie"),
    (3,"A","2026-06-18","Tchéquie","Afrique du Sud"),(4,"A","2026-06-18","Mexique","Corée du Sud"),
    (5,"A","2026-06-24","Tchéquie","Mexique"),(6,"A","2026-06-24","Afrique du Sud","Corée du Sud"),
    (7,"B","2026-06-12","Canada","Bosnie-Herzégovine"),(8,"B","2026-06-13","Qatar","Suisse"),
    (9,"B","2026-06-18","Suisse","Bosnie-Herzégovine"),(10,"B","2026-06-18","Canada","Qatar"),
    (11,"B","2026-06-24","Suisse","Canada"),(12,"B","2026-06-24","Bosnie-Herzégovine","Qatar"),
    (13,"C","2026-06-13","Brésil","Maroc"),(14,"C","2026-06-13","Haïti","Écosse"),
    (15,"C","2026-06-19","Écosse","Maroc"),(16,"C","2026-06-19","Brésil","Haïti"),
    (17,"C","2026-06-24","Écosse","Brésil"),(18,"C","2026-06-24","Maroc","Haïti"),
    (19,"D","2026-06-12","États-Unis","Paraguay"),(20,"D","2026-06-13","Australie","Turquie"),
    (21,"D","2026-06-19","États-Unis","Australie"),(22,"D","2026-06-19","Turquie","Paraguay"),
    (23,"D","2026-06-25","Turquie","États-Unis"),(24,"D","2026-06-25","Paraguay","Australie"),
    (25,"E","2026-06-14","Allemagne","Curaçao"),(26,"E","2026-06-14","Côte d'Ivoire","Équateur"),
    (27,"E","2026-06-20","Allemagne","Côte d'Ivoire"),(28,"E","2026-06-20","Équateur","Curaçao"),
    (29,"E","2026-06-25","Équateur","Allemagne"),(30,"E","2026-06-25","Curaçao","Côte d'Ivoire"),
    (31,"F","2026-06-14","Pays-Bas","Japon"),(32,"F","2026-06-14","Suède","Tunisie"),
    (33,"F","2026-06-20","Pays-Bas","Suède"),(34,"F","2026-06-20","Tunisie","Japon"),
    (35,"F","2026-06-25","Japon","Suède"),(36,"F","2026-06-25","Tunisie","Pays-Bas"),
    (37,"G","2026-06-15","Belgique","Égypte"),(38,"G","2026-06-15","Iran","Nouvelle-Zélande"),
    (39,"G","2026-06-21","Belgique","Iran"),(40,"G","2026-06-21","Nouvelle-Zélande","Égypte"),
    (41,"G","2026-06-26","Égypte","Iran"),(42,"G","2026-06-26","Nouvelle-Zélande","Belgique"),
    (43,"H","2026-06-15","Espagne","Cap-Vert"),(44,"H","2026-06-15","Arabie Saoudite","Uruguay"),
    (45,"H","2026-06-21","Espagne","Arabie Saoudite"),(46,"H","2026-06-21","Uruguay","Cap-Vert"),
    (47,"H","2026-06-26","Cap-Vert","Arabie Saoudite"),(48,"H","2026-06-26","Uruguay","Espagne"),
    (49,"I","2026-06-16","France","Sénégal"),(50,"I","2026-06-16","Irak","Norvège"),
    (51,"I","2026-06-22","France","Irak"),(52,"I","2026-06-22","Norvège","Sénégal"),
    (53,"I","2026-06-26","Norvège","France"),(54,"I","2026-06-26","Sénégal","Irak"),
    (55,"J","2026-06-16","Argentine","Algérie"),(56,"J","2026-06-16","Autriche","Jordanie"),
    (57,"J","2026-06-22","Argentine","Autriche"),(58,"J","2026-06-22","Jordanie","Algérie"),
    (59,"J","2026-06-27","Algérie","Autriche"),(60,"J","2026-06-27","Jordanie","Argentine"),
    (61,"K","2026-06-17","Portugal","RD Congo"),(62,"K","2026-06-17","Ouzbékistan","Colombie"),
    (63,"K","2026-06-23","Portugal","Ouzbékistan"),(64,"K","2026-06-23","Colombie","RD Congo"),
    (65,"K","2026-06-27","Colombie","Portugal"),(66,"K","2026-06-27","RD Congo","Ouzbékistan"),
    (67,"L","2026-06-17","Angleterre","Croatie"),(68,"L","2026-06-17","Ghana","Panama"),
    (69,"L","2026-06-23","Angleterre","Ghana"),(70,"L","2026-06-23","Panama","Croatie"),
    (71,"L","2026-06-27","Panama","Angleterre"),(72,"L","2026-06-27","Croatie","Ghana"),
]
MATCH_BY_TEAMS = {}   # frozenset({home,away}) -> (id, home, away)
for mid,grp,date,h,a in GROUP_MATCHES:
    MATCH_BY_TEAMS[frozenset((h,a))] = (mid,h,a)

DATE_FR = {"06-11":"11 juin","06-12":"12 juin","06-13":"13 juin","06-14":"14 juin","06-15":"15 juin",
           "06-16":"16 juin","06-17":"17 juin","06-18":"18 juin","06-19":"19 juin","06-20":"20 juin",
           "06-21":"21 juin","06-22":"22 juin","06-23":"23 juin","06-24":"24 juin","06-25":"25 juin",
           "06-26":"26 juin","06-27":"27 juin"}

# Horaires par défaut (heure de Paris) si l'API ne fournit pas encore l'utcDate.
# Créneaux types de la phase de groupes ; affinés automatiquement dès que l'API renvoie l'heure réelle.
DEFAULT_TIME = {}  # match_id -> "HH:MM" (Paris) — laissé vide : on affiche la date seule à défaut

def paris_from_utc(utc_str):
    """Convertit un utcDate ISO (ex '2026-06-11T19:00:00Z') en (date_iso, 'HH:MM') heure de Paris.
    Paris = UTC+2 en été (juin/juillet). Retourne (None,None) si parsing impossible."""
    if not utc_str: return (None, None)
    try:
        s=utc_str.replace("Z","+00:00")
        dt=datetime.datetime.fromisoformat(s)
        # été : UTC+2
        dt_paris=dt + datetime.timedelta(hours=2)
        return (dt_paris.strftime("%Y-%m-%d"), dt_paris.strftime("%H:%M"))
    except Exception:
        return (None, None)

# ─── MOTEUR DE PRONOSTIC ─────────────────────────────────────────────────────
def style_bonus(s1,s2):
    if s1=="bloc_bas" and s2=="pressing": return (0.3,-0.3)
    if s1=="contre" and s2=="possession": return (0.4,-0.2)
    if s1=="pressing" and s2=="bloc_bas": return (-0.2,0.1)
    if s1=="possession" and s2=="contre": return (-0.2,0.3)
    return (0,0)

def compute(home,away,momentum=None):
    mo=momentum or {}
    hf0,ht,hs,hsur=TEAM_DATA[home]; af0,at,as_,asur=TEAM_DATA[away]
    tb={"up":0.4,"down":-0.4,"stable":0}
    hF=hf0+tb[ht]+mo.get(home,0.0); aF=af0+tb[at]+mo.get(away,0.0)
    if home in HOST_NATIONS: hF+=HOST_BONUS
    if away in HOST_NATIONS: aF+=HOST_BONUS
    sbh,sba=style_bonus(hs,as_); hF+=sbh; aF+=sba
    diff=hF-aF
    if   diff>=3.5: h,a=3,0
    elif diff>=2.5: h,a=3,1
    elif diff>=1.8: h,a=2,0
    elif diff>=1.2: h,a=2,1
    elif diff>=0.6: h,a=1,0
    elif diff>=0.2: h,a=2,1
    elif diff>-0.2: h,a=(0,0) if (hs=="bloc_bas" and as_=="bloc_bas") else (1,1)
    elif diff>-0.6: h,a=1,2
    elif diff>-1.2: h,a=0,1
    elif diff>-1.8: h,a=1,2
    elif diff>-2.5: h,a=0,2
    elif diff>-3.5: h,a=1,3
    else: h,a=0,3
    if asur and diff<1.8 and diff>-1.0 and h>a:
        a=max(a,h-1)
        if abs(diff)<0.5: h=a
    low=["Équateur","Tunisie","Panama","Irak","Iran","Bosnie-Herzégovine"]
    if home in low or away in low: h=min(h,2); a=min(a,1)
    high=["Argentine","France","Allemagne","Espagne","Angleterre","Norvège"]
    if home in high and diff>2: h=min(h+1,4)
    return h,a,diff

import math
def confidence_pct(diff):
    """Indice de confiance (%) = certitude du pronostic, selon l'ampleur de l'écart de force.
    Échelle étendue (option 2) : match très indécis ~25-30%, favori net jusqu'à ~92%.
    Un écart quasi nul (issue ouverte) descend volontairement bas pour refléter l'incertitude."""
    a = abs(diff)
    p = 1.0 / (1.0 + math.exp(-1.15*a))   # 0.5 (a=0) .. ~1.0
    # remappe [0.5..1.0] vers [28%..92%] : l'indécision tombe sous le seuil rouge
    pct = 28 + (p-0.5)/0.5 * 64
    return int(round(min(92, max(22, pct))))

def style_analysis(home, away):
    """Retourne (libellé court 'Style1 vs Style2', note tactique) pour l'affichage."""
    hs = TEAM_DATA[home][2]; as_ = TEAM_DATA[away][2]
    label = f"{STYLE_FR[hs]} vs {STYLE_FR[as_]}"
    notes = {
        ("bloc_bas","pressing"): "Le bloc bas peut neutraliser le pressing adverse",
        ("contre","possession"): "Jeu de transition efficace face à une équipe de possession",
        ("pressing","bloc_bas"): "Pressing confronté à une défense regroupée",
        ("possession","contre"): "Possession exposée aux contres adverses",
    }
    note = notes.get((hs,as_), "")
    if not note:
        if hs==as_: note = "Styles similaires, duel équilibré tactiquement"
        else: note = "Opposition de styles classique"
    return label, note

def match_summary(home, away, rh, ra, statut, mom_after, scorers_by_team):
    """Génère un résumé court combinant factuel (A) et analyse du moteur (C).
    mom_after : dict team->momentum (après ce match). scorers_by_team : dict team->[noms]."""
    # --- Factuel (A) ---
    if rh > ra:
        winner, wscore, lscore = home, rh, ra
        head = f"{home} s'impose {rh}-{ra} face à {away}."
    elif ra > rh:
        winner, wscore, lscore = away, ra, rh
        head = f"{away} s'impose {ra}-{rh} face à {home}."
    else:
        winner = None
        head = f"{home} et {away} se neutralisent {rh}-{ra}."
    total = rh + ra
    if winner is None and total == 0:
        head += " Un match fermé, sans but."
    elif total >= 5:
        head += " Une rencontre spectaculaire et offensive."
    elif total >= 3:
        head += " Un match animé."

    # buteurs si disponibles (endpoint scorers, partiel sur plan gratuit)
    scorer_bits = []
    for team in (home, away):
        names = scorers_by_team.get(team, [])
        if names:
            scorer_bits.append(f"Côté {team}, on retrouve {', '.join(names[:2])} parmi les buteurs du tournoi.")
    factual = " ".join(scorer_bits)

    # --- Analyse du moteur (C) ---
    if statut == "exact":
        verdict = "Résultat exactement conforme au pronostic IA."
    elif statut == "bon":
        verdict = "Le bon vainqueur avait été anticipé, mais pas le score exact."
    else:
        verdict = "Résultat à contre-courant du pronostic : le football reste imprévisible."

    # impact dynamique
    dyn_bits = []
    for team in (home, away):
        m = mom_after.get(team, 0.0)
        if m >= 0.30: dyn_bits.append(f"{team} repart avec une belle dynamique (+{m:.2f})")
        elif m <= -0.30: dyn_bits.append(f"{team} accuse le coup ({m:.2f})")
    dyn = (" " + " ; ".join(dyn_bits) + ".") if dyn_bits else ""

    parts = [head]
    if factual: parts.append(factual)
    parts.append(verdict + dyn)
    return " ".join(parts).strip()

def compute_momentum(results):
    from collections import defaultdict
    momentum=defaultdict(float); detail=defaultdict(list)
    by_id={m[0]:m for m in GROUP_MATCHES}
    for mid,sc in results.items():
        mid=int(mid)
        if mid not in by_id: continue
        _,grp,date,home,away=by_id[mid]
        rh,ra=sc["h"],sc["a"]; hf=TEAM_DATA[home][0]; af=TEAM_DATA[away][0]
        for team,gf,ga,opp_f in [(home,rh,ra,af),(away,ra,rh,hf)]:
            if gf>ga: base=0.30; tag="V"
            elif gf<ga: base=-0.30; tag="D"
            else: base=0.0; tag="N"
            margin=max(-3,min(3,gf-ga)); margin_bonus=margin*0.07
            gap=opp_f-TEAM_DATA[team][0]; surprise=0.0
            if gf>ga and gap>0: surprise=gap*0.10
            elif gf<ga and gap<0: surprise=gap*0.10
            elif gf==ga and gap>0: surprise=gap*0.05
            momentum[team]+=base+margin_bonus+surprise
            detail[team].append(f"{tag} {gf}-{ga}")
    for t in momentum: momentum[t]=max(-1.2,min(1.2,momentum[t]))
    return dict(momentum),dict(detail)

# ─── RÉCUPÉRATION DES RÉSULTATS ──────────────────────────────────────────────
def fetch_from_api():
    """Retourne {match_id: {'h':int,'a':int}} depuis football-data.org, ou None si échec."""
    if not API_KEY:
        return None
    url=f"{API_BASE}/competitions/{WC_CODE}/matches"
    req=urllib.request.Request(url, headers={"X-Auth-Token":API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload=json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body=""
        try: body=e.read().decode("utf-8")[:300]
        except Exception: pass
        print(f"[API] HTTP {e.code} : {body}", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[API] Erreur réseau : {e}", file=sys.stderr)
        return None

    results={}
    datetimes={}
    for fx in payload.get("matches", []):
        hn=map_team((fx.get("homeTeam") or {}).get("name"), (fx.get("homeTeam") or {}).get("tla"))
        an=map_team((fx.get("awayTeam") or {}).get("name"), (fx.get("awayTeam") or {}).get("tla"))
        if hn is None or an is None: continue
        key=frozenset((hn,an))
        if key not in MATCH_BY_TEAMS: continue
        mid,our_home,our_away=MATCH_BY_TEAMS[key]
        # horaire officiel (utcDate) si présent, quel que soit le statut
        utc=fx.get("utcDate")
        if utc: datetimes[str(mid)]=utc
        status=fx.get("status","")
        if status not in ("FINISHED","AWARDED"):   # score : match terminé uniquement
            continue
        full=(fx.get("score") or {}).get("fullTime") or {}
        gh=full.get("home"); ga=full.get("away")
        if gh is None or ga is None: continue
        # réorienter le score selon notre ordre (home/away de GROUP_MATCHES)
        if hn==our_home:
            results[str(mid)]={"h":int(gh),"a":int(ga)}
        else:
            results[str(mid)]={"h":int(ga),"a":int(gh)}
    return results, datetimes

def fetch_scorers():
    """Récupère les meilleurs buteurs du tournoi (endpoint /scorers, dispo en gratuit).
    Retourne {nom_equipe_FR: [noms_joueurs]}. Vide si indisponible."""
    if not API_KEY:
        return {}
    url=f"{API_BASE}/competitions/{WC_CODE}/scorers?limit=50"
    req=urllib.request.Request(url, headers={"X-Auth-Token":API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload=json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[INFO] Buteurs indisponibles : {e}", file=sys.stderr)
        return {}
    by_team={}
    for sc in payload.get("scorers", []):
        player=(sc.get("player") or {}).get("name")
        team_obj=sc.get("team") or {}
        team=map_team(team_obj.get("name"), team_obj.get("tla"))
        goals=sc.get("goals") or 0
        if player and team and goals:
            by_team.setdefault(team, []).append(player)
    return by_team

def load_results():
    """API en priorité, repli sur data/results_manual.json.
    Retourne (results, datetimes)."""
    out=fetch_from_api()
    if out is not None:
        api, datetimes = out
        if len(api)>0 or len(datetimes)>0:
            if len(api)>0:
                print(f"[OK] {len(api)} résultat(s) récupéré(s) via football-data.org")
            if len(datetimes)>0:
                print(f"[OK] {len(datetimes)} horaire(s) officiel(s) récupéré(s)")
            manual=load_manual()
            merged=dict(manual); merged.update(api)
            save_manual(merged, datetimes)
            return merged, load_datetimes(datetimes)
    print("[INFO] API indisponible ou vide → repli sur les données locales")
    return load_manual(), load_datetimes({})

def load_manual():
    p=os.path.join(ROOT,"data","results_manual.json")
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f:
            return json.load(f).get("resultats",{})
    return {}

def load_datetimes(fresh):
    """Fusionne les horaires fraîchement récupérés avec ceux déjà stockés."""
    stored={}
    p=os.path.join(ROOT,"data","results_manual.json")
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f:
            stored=json.load(f).get("horaires",{})
    merged=dict(stored); merged.update(fresh or {})
    return merged

def save_manual(results, datetimes=None):
    p=os.path.join(ROOT,"data","results_manual.json")
    os.makedirs(os.path.dirname(p),exist_ok=True)
    prev_h={}
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f:
            prev_h=json.load(f).get("horaires",{})
    horaires=dict(prev_h); horaires.update(datetimes or {})
    with open(p,"w",encoding="utf-8") as f:
        json.dump({"derniere_maj":datetime.date.today().isoformat(),
                   "resultats":results,"horaires":horaires},f,ensure_ascii=False,indent=2)

# ─── CONSTRUCTION DES DONNÉES DE LA PAGE ─────────────────────────────────────
def build_payload(results, scorers_by_team=None, datetimes=None):
    from collections import defaultdict
    scorers_by_team = scorers_by_team or {}
    datetimes = datetimes or {}
    results={str(k):v for k,v in results.items()}
    momentum,detail=compute_momentum(results)
    rint={int(k):v for k,v in results.items()}
    today_iso = datetime.date.today().isoformat()

    matches=[]; n_exact=n_bon=n_rate=n_joue=0; n_today=0
    for mid,grp,date,home,away in GROUP_MATCHES:
        pih,pia,_=compute(home,away,None)
        pah,paa,diffaj=compute(home,away,momentum)
        joue=mid in rint
        reel=None; statut="avenir"; resume=""
        if joue:
            rh,ra=rint[mid]["h"],rint[mid]["a"]; reel=[rh,ra]
            po=0 if pih>pia else (1 if pih<pia else 2)
            ro=0 if rh>ra else (1 if rh<ra else 2)
            if pih==rh and pia==ra: statut="exact"; n_exact+=1
            elif po==ro: statut="bon"; n_bon+=1
            else: statut="rate"; n_rate+=1
            n_joue+=1
            resume=match_summary(home, away, rh, ra, statut, momentum, scorers_by_team)
        # date + heure
        iso_date, heure = paris_from_utc(datetimes.get(str(mid)))
        if not iso_date:
            iso_date = date   # date programmée à défaut
        mmkey="06-"+iso_date.split("-")[2]
        date_fr = DATE_FR.get(mmkey, iso_date)
        is_today = (iso_date == today_iso)
        if is_today: n_today += 1
        # clé de tri chronologique (date + heure si dispo, sinon 23:59 pour passer après)
        sort_key = iso_date + "T" + (heure if heure else "23:59")
        style_label, style_note = style_analysis(home, away)
        matches.append({
            "id":mid,"grp":grp,"date":date_fr,"heure":heure or "","iso":iso_date,"sort":sort_key,
            "today":is_today,
            "home":home,"away":away,
            "ch":FLAG_CODES.get(home,""),"ca":FLAG_CODES.get(away,""),
            "host_h":home in HOST_NATIONS,"host_a":away in HOST_NATIONS,
            "prono":[pah,paa] if not joue else [pih,pia],
            "prono_initial":[pih,pia],"reel":reel,"statut":statut,"resume":resume,
            "confidence":confidence_pct(diffaj if not joue else compute(home,away,None)[2]),
            "style_label":style_label,"style_note":style_note,
            "mom_h":round(momentum.get(home,0.0),2),"mom_a":round(momentum.get(away,0.0),2),
        })

    # classements
    table=defaultdict(lambda:defaultdict(lambda:{"Pts":0,"J":0,"G":0,"N":0,"P":0,"BP":0,"BC":0,"reels":0}))
    for m in matches:
        grp=m["grp"]; home=m["home"]; away=m["away"]
        if m["reel"]: h,a=m["reel"]; isr=True
        else: h,a=m["prono"]; isr=False
        th,ta=table[grp][home],table[grp][away]
        th["J"]+=1; ta["J"]+=1; th["BP"]+=h; th["BC"]+=a; ta["BP"]+=a; ta["BC"]+=h
        if isr: th["reels"]+=1; ta["reels"]+=1
        if h>a: th["Pts"]+=3; th["G"]+=1; ta["P"]+=1
        elif a>h: ta["Pts"]+=3; ta["G"]+=1; th["P"]+=1
        else: th["Pts"]+=1; ta["Pts"]+=1; th["N"]+=1; ta["N"]+=1
    standings={}
    for grp,teams in table.items():
        ranked=sorted(teams.items(),key=lambda kv:(kv[1]["Pts"],kv[1]["BP"]-kv[1]["BC"],kv[1]["BP"]),reverse=True)
        standings[grp]=[{"team":t,"code":FLAG_CODES.get(t,""),"host":t in HOST_NATIONS,
                         "reels":table[grp][t]["reels"],**st} for t,st in ranked]

    mom_list=sorted(({"team":t,"code":FLAG_CODES.get(t,""),"mom":round(v,2),"detail":" · ".join(detail.get(t,[]))}
                     for t,v in momentum.items()), key=lambda x:-x["mom"])

    return {
        "maj":datetime.datetime.now().strftime("%d/%m/%Y à %H:%M"),
        "today":datetime.date.today().isoformat(),
        "stats":{"joue":n_joue,"exact":n_exact,"bon":n_bon,"rate":n_rate,"total":72,"today":n_today},
        "matches":matches,"standings":standings,"momentum":mom_list,
    }

# ─── GÉNÉRATION HTML ─────────────────────────────────────────────────────────
def render_html(payload):
    data_json=json.dumps(payload,ensure_ascii=False)
    tpl=open(os.path.join(ROOT,"template.html"),"r",encoding="utf-8").read()
    return tpl.replace("/*__DATA__*/null", data_json)

def main():
    results, datetimes = load_results()
    scorers=fetch_scorers()
    if scorers:
        print(f"[OK] Buteurs récupérés pour {len(scorers)} équipe(s)")
    payload=build_payload(results, scorers, datetimes)
    html=render_html(payload)
    out=os.path.join(ROOT,"index.html")
    with open(out,"w",encoding="utf-8") as f:
        f.write(html)
    s=payload["stats"]
    print(f"[OK] index.html généré — {s['joue']} joués | {s['exact']} exacts, {s['bon']} bons, {s['rate']} ratés | {s['today']} match(s) aujourd'hui")

if __name__=="__main__":
    main()
