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

# Version du modèle de pronostic (affichée dans le pied de page).
# Historique : 1.x base · 2.0 facteur qualification + dynamique · 2.1 règles 2026 (compression ciblée)
#             · 2.2 variation réaliste des scores (distribution CM 2010-2022, graine par affiche)
MODEL_VERSION = "2.2"

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

# Heure de coup d'envoi en UTC (HH décimal) pour chaque match, d'après le calendrier officiel FIFA.
# Sert au tri chronologique du Live feed MÊME sans appel API. Annonces FIFA en ET (UTC-4 l'été) :
# créneaux ET 12h/15h/18h/21h -> UTC 16/19/22/01(+1j). Brésil-Haïti à 20h30 ET -> 00h30 UTC(+1j).
# La date de coup d'envoi réelle (avec passage au lendemain) est gérée par KICKOFF_DATE ci-dessous.
KICKOFF_UTC = {
    1:"19:00",2:"02:00", 7:"19:00",19:"01:00", 8:"19:00",13:"22:00",14:"01:00",20:"04:00",
    25:"17:00",31:"20:00",26:"23:00",32:"02:00", 37:"19:00",43:"16:00",44:"22:00",38:"01:00",
    49:"19:00",50:"22:00",55:"01:00",56:"04:00", 61:"16:00",67:"19:00",62:"22:00",68:"01:00",
    3:"19:00",9:"19:00",4:"01:00",10:"22:00", 15:"22:00",21:"19:00",16:"01:00",22:"04:00",
    27:"20:00",33:"17:00",28:"00:00",34:"04:00", 39:"19:00",45:"16:00",46:"22:00",40:"01:00",
    51:"21:00",57:"17:00",52:"00:00",58:"03:00", 63:"17:00",69:"20:00",64:"02:00",70:"23:00",
    5:"01:00",11:"19:00",6:"01:00",12:"19:00", 17:"22:00",23:"01:00",18:"22:00",24:"01:00",
    29:"01:00",35:"01:00",30:"22:00",36:"22:00", 41:"01:00",47:"01:00",42:"22:00",48:"22:00",
    53:"01:00",59:"01:00",54:"22:00",60:"22:00", 65:"01:00",71:"01:00",66:"22:00",72:"22:00",
}
# Décalage de jour : matchs dont le coup d'envoi UTC tombe le lendemain de la date "programme".
KICKOFF_NEXTDAY = {2,19,14,20,4,16,22,28,34,40,58,64,70,52,5,6,23,24,29,35,41,47,53,59,65,71,46}

def paris_time_str(hhmm):
    """'HH:MM' UTC -> 'HH:MM' Paris (UTC+2 été)."""
    try:
        h,m=hhmm.split(":"); h=(int(h)+2)%24
        return f"{h:02d}:{m}"
    except Exception:
        return ""

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

def _score_from_diff(diff, home, away, hs, as_, asur):
    """Score réaliste AVEC variation, calé sur la distribution des scores des Coupes
    du Monde récentes (1-0, 2-1, 2-0, 1-1, 0-0, 3-1… cf. stats FIFA 2010-2022).
    Le résultat (vainqueur/nul) suit l'écart de force ; le SCORE exact est tiré d'un
    panier réaliste via une graine STABLE par affiche -> fini les 1-0 partout, on
    retrouve une vraie diversité (2-1, 2-0, 3-1, 0-0…) reproductible d'un run à l'autre.
    Paniers exprimés (buts favori, buts adverse)."""
    ad=abs(diff)
    if   ad>=3.2: pool=[(4,0),(3,0),(3,1),(5,0),(4,1),(2,0)]   # écrasant
    elif ad>=2.4: pool=[(3,0),(2,0),(3,1),(4,1),(2,1)]         # très net
    elif ad>=1.6: pool=[(2,0),(3,1),(2,1),(3,0),(1,0)]         # net
    elif ad>=0.9: pool=[(2,1),(2,0),(1,0),(3,1),(2,2)]         # favori clair
    elif ad>=0.45: pool=[(1,0),(2,1),(2,0),(1,1)]              # léger avantage
    elif ad>=0.18: pool=[(1,0),(2,1),(1,1),(0,0)]              # serré
    else: pool=[(1,1),(0,0),(2,2),(1,0),(2,1)]                 # équilibré (souvent nul)
    # Graine stable par affiche (déterministe, varie d'un match à l'autre)
    seed=0
    for ch in (home+"|"+away): seed=(seed*31+ord(ch)) & 0xffffffff
    fav,dog=pool[seed % len(pool)]
    # Outsider (équipe surprise côté extérieur) : sur match serré, resserre l'écart
    if asur and ad<1.2 and fav>dog and (seed%3==0):
        dog=min(fav, dog+1)
    if fav==dog:
        return fav,dog
    # Orientation : diff>=0 -> le favori est l'équipe à domicile (home)
    return (fav,dog) if diff>=0 else (dog,fav)

def compute(home,away,momentum=None,qualif=None):
    mo=momentum or {}; qz=qualif or {}
    hf0,ht,hs,hsur=TEAM_DATA[home]; af0,at,as_,asur=TEAM_DATA[away]
    tb={"up":0.4,"down":-0.4,"stable":0}
    hF=hf0+tb[ht]+mo.get(home,0.0); aF=af0+tb[at]+mo.get(away,0.0)
    if home in HOST_NATIONS: hF+=HOST_BONUS
    if away in HOST_NATIONS: aF+=HOST_BONUS
    # Facteur qualification (3e match de poule) : une équipe déjà qualifiée lève le pied (turnover),
    # une équipe qui joue sa survie est galvanisée, une équipe éliminée est démobilisée.
    qb={"qualified":-0.35,"alive":0.20,"eliminated":-0.25,None:0.0}
    hF+=qb.get(qz.get(home),0.0); aF+=qb.get(qz.get(away),0.0)
    sbh,sba=style_bonus(hs,as_); hF+=sbh; aF+=sba
    diff=hF-aF
    h,a=_score_from_diff(diff, home, away, hs, as_, asur)
    return h,a,diff

def second_choice(home, away, diff):
    """Retourne (h,a,label) du 2e scénario le plus crédible pour un match incertain.
    Le SCORE est toujours COHÉRENT avec le libellé :
      - pronostic de victoire -> alternative = match nul (score nul garanti) ;
      - pronostic de nul -> alternative = victoire du favori (score décisif garanti)."""
    hs=TEAM_DATA[home][2]; as_=TEAM_DATA[away][2]; asur=TEAM_DATA[away][3]
    h1,a1=_score_from_diff(diff, home, away, hs, as_, asur)
    seed=sum(ord(c) for c in (home+away))
    if h1!=a1:
        # Prono = victoire -> alternative = MATCH NUL (toujours un nul réaliste)
        n=[1,0,2][seed%3]          # 1-1, 0-0 ou 2-2
        return n, n, "Match nul"
    # Prono = nul -> alternative = VICTOIRE du favori sur le papier (toujours décisif)
    if diff>=0:
        return 2, 1, "Victoire "+home
    return 1, 2, "Victoire "+away

import math
def confidence_pct(diff):
    """Indice de confiance (%) = certitude du pronostic, selon l'ampleur de l'écart de force.
    Échelle calibrée (option B) : le modèle, enrichi de la dynamique réelle, du facteur
    qualification et de l'avantage hôte, est plus tranché. Moyenne cible ~75% sur l'ensemble,
    tout en gardant un plancher bas (~30%) pour les vrais matchs indécis (seuil rouge actif).
    Un favori net atteint ~94%."""
    a = abs(diff)
    p = 1.0 / (1.0 + math.exp(-1.35*a))   # 0.5 (a=0) .. ~1.0, pente plus marquée
    # remappe [0.5..1.0] vers [38%..94%] : plancher relevé, sommet relevé
    pct = 38 + (p-0.5)/0.5 * 56
    pct -= 3   # abattement variance "règles 2026" : comebacks/anti-temps-mort -> upsets plus fréquents
    return int(round(min(92, max(28, pct))))

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

def compute_qualif_states(results):
    """Détermine, pour chaque équipe, son statut AVANT son 3e match de poule, à partir
    des résultats réels des journées 1 et 2.
    Retourne {equipe: 'qualified'|'eliminated'|'alive'|None}.
    None = on ne sait pas encore (moins de 2 matchs joués dans le groupe).
    Heuristique 4 équipes / 6 matchs : on évalue les points après 2 journées.
    - 6 pts (2 victoires) => qualifié quasi certain -> 'qualified'
    - 0 pt après 2 matchs => quasi éliminé -> 'eliminated'
    - sinon -> 'alive' (tout se joue à la 3e journée)
    Le statut n'est appliqué qu'aux équipes ayant DÉJÀ joué 2 matchs."""
    from collections import defaultdict
    rint={int(k):v for k,v in results.items()}
    # regrouper par groupe : points et nb matchs joués par équipe
    pts=defaultdict(int); played=defaultdict(int); gd=defaultdict(int)
    by_grp=defaultdict(list)
    for mid,grp,date,home,away in GROUP_MATCHES:
        by_grp[grp].append((mid,home,away))
        if mid in rint:
            rh,ra=rint[mid]["h"],rint[mid]["a"]
            played[home]+=1; played[away]+=1
            gd[home]+=rh-ra; gd[away]+=ra-rh
            if rh>ra: pts[home]+=3
            elif ra>rh: pts[away]+=3
            else: pts[home]+=1; pts[away]+=1
    states={}
    for grp, teams_matches in by_grp.items():
        teams=set()
        for _,h,a in teams_matches: teams.add(h); teams.add(a)
        # combien de matchs joués dans le groupe (sur 6) ?
        for t in teams:
            if played[t] >= 2:
                p=pts[t]
                if p>=6: states[t]="qualified"     # 2 victoires
                elif p>=4: states[t]="qualified"    # 4 pts après 2 matchs : très bien placé
                elif p==0: states[t]="eliminated"   # 0 pt : quasi éliminé
                else: states[t]="alive"             # 1 à 3 pts : tout ouvert
            else:
                states[t]=None
    return states

def match_summary(home, away, rh, ra, statut, mom_after, scorers_by_team):
    """Génère un résumé court combinant factuel (A) et analyse du moteur (C).
    mom_after : dict team->momentum (après ce match). scorers_by_team : dict team->[noms]."""
    # --- Factuel (A) ---
    total = rh + ra
    if rh > ra:
        winner, margin = home, rh - ra
        head = f"{home} s'impose {rh}-{ra} face à {away}."
    elif ra > rh:
        winner, margin = away, ra - rh
        head = f"{away} s'impose {ra}-{rh} face à {home}."
    else:
        winner, margin = None, 0
        head = f"{home} et {away} se neutralisent {rh}-{ra}."

    # Physionomie de la rencontre
    if winner is None:
        head += " Aucun but, les défenses ont tenu." if total == 0 else " Un nul équilibré."
    elif margin >= 3:
        head += f" Un large succès, {winner} n'a pas tremblé."
    elif total >= 4:
        head += " Un match ouvert et spectaculaire."
    elif margin == 1:
        head += " Une victoire arrachée."

    # Buteurs en forme (endpoint scorers, partiel sur le plan gratuit)
    scorer_bits = []
    for team in (home, away):
        names = scorers_by_team.get(team, [])[:2]
        if names:
            who = " et ".join(names)
            verb = "compte" if len(names) == 1 else "comptent"
            scorer_bits.append(f"Côté {team}, {who} {verb} parmi les buteurs en forme.")
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

    # Résumé factuel (mode Réel) : score + ambiance + buteurs, sans verdict de prono
    reel_parts = [head]
    if factual: reel_parts.append(factual)
    resume_reel = " ".join(reel_parts).strip()
    # Résumé complet (mode PronoBot) : factuel + verdict + dynamique
    parts = list(reel_parts)
    parts.append(verdict + dyn)
    return " ".join(parts).strip(), resume_reel

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

    # ── Dates des matchs à élimination directe (équipes encore "à définir") ──
    # On ne peut pas mapper par équipes : on s'appuie sur le champ `stage` officiel.
    # Repli silencieux si les libellés de stage diffèrent (les cartes gardent alors
    # le bandeau de période du tour). 3e place ignorée (non affichée).
    KO_STAGE_IDS={
        "LAST_32":list(range(73,89)), "LAST_16":list(range(89,97)),
        "QUARTER_FINALS":[97,98,99,100], "SEMI_FINALS":[101,102], "FINAL":[104],
    }
    by_stage={}
    for fx in payload.get("matches", []):
        st=(fx.get("stage") or "").upper()
        if st in KO_STAGE_IDS and fx.get("utcDate"):
            by_stage.setdefault(st,[]).append((fx["utcDate"], fx.get("id") or 0))
    for st,ids in KO_STAGE_IDS.items():
        for i,(utc,_id) in enumerate(sorted(by_stage.get(st,[]))):
            if i<len(ids): datetimes[str(ids[i])]=utc

    return results, datetimes

def fetch_scorers():
    """Récupère les meilleurs buteurs du tournoi (endpoint /scorers, dispo en gratuit).
    Retourne (by_team, top_list) :
      - by_team : {nom_equipe_FR: [noms_joueurs]} (utilisé dans les résumés de match)
      - top_list : [{'player','team','code','goals','assists'}] trié par buts décroissant
    (..., []) si indisponible."""
    if not API_KEY:
        return {}, []
    url=f"{API_BASE}/competitions/{WC_CODE}/scorers?limit=50"
    req=urllib.request.Request(url, headers={"X-Auth-Token":API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload=json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[INFO] Buteurs indisponibles : {e}", file=sys.stderr)
        return {}, []
    by_team={}; top_list=[]
    for sc in payload.get("scorers", []):
        player=(sc.get("player") or {}).get("name")
        team_obj=sc.get("team") or {}
        team=map_team(team_obj.get("name"), team_obj.get("tla"))
        goals=sc.get("goals") or 0
        assists=sc.get("assists") or 0
        if player and team and goals:
            by_team.setdefault(team, []).append(player)
            top_list.append({"player":player,"team":team,"code":FLAG_CODES.get(team,""),
                             "goals":int(goals),"assists":int(assists)})
    # tri : buts décroissants, puis passes décisives, puis ordre alphabétique
    top_list.sort(key=lambda x:(-x["goals"], -x["assists"], x["player"]))
    return by_team, top_list

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

# ─── TABLEAU FINAL (PHASES FINALES) ──────────────────────────────────────────
# Slots "meilleur 3e" : groupes autorisés par match (Annexe C FIFA).
THIRD_SLOTS = {74:"ABCDF",77:"CDFGH",79:"CEFHI",80:"EHIJK",81:"BEFIJ",82:"AEHIJ",85:"EFGIJ",87:"DEIJL"}
# 16es de finale : (id, refDom, refExt) ; ref = ('1',G)=vainqueur, ('2',G)=2e, ('3',slot)=meilleur 3e
KO_R32 = [
    (73,('2','A'),('2','B')), (74,('1','E'),('3',74)), (75,('1','F'),('2','C')), (76,('1','C'),('2','F')),
    (77,('1','I'),('3',77)),  (78,('2','E'),('2','I')), (79,('1','A'),('3',79)), (80,('1','L'),('3',80)),
    (81,('1','D'),('3',81)),  (82,('1','G'),('3',82)),  (83,('2','K'),('2','L')),(84,('1','H'),('2','J')),
    (85,('1','B'),('3',85)),  (86,('1','J'),('2','H')), (87,('1','K'),('3',87)), (88,('2','D'),('2','G')),
]
# Tours suivants : (id, vainqueur_match_a, vainqueur_match_b)
KO_NEXT = [
    (89,74,77),(90,73,75),(91,76,78),(92,79,80),(93,83,84),(94,81,82),(95,86,88),(96,85,87),  # 8es
    (97,89,90),(98,93,94),(99,91,92),(100,95,96),  # quarts
    (101,97,98),(102,99,100),  # demies
    (104,101,102),  # finale
]

def _assign_thirds(standings):
    """Classe les 12 troisièmes, retient les 8 meilleurs, et les affecte aux slots
    en respectant les groupes autorisés (résolution par backtracking)."""
    thirds=[]
    for g,rows in standings.items():
        if len(rows)>=3:
            r=rows[2]; thirds.append((g,r["Pts"],r["BP"]-r["BC"],r["BP"],r["team"]))
    thirds_sorted=sorted(thirds,key=lambda x:(x[1],x[2],x[3]),reverse=True)
    qualified=thirds_sorted[:8]
    qual_groups=[t[0] for t in qualified]
    team_by_group={t[0]:t[4] for t in qualified}
    slots=[74,77,79,80,81,82,85,87]; allowed={s:set(THIRD_SLOTS[s]) for s in slots}
    assignment={}
    def bt(i,used):
        if i==len(slots): return True
        s=slots[i]
        for g in qual_groups:
            if g not in used and g in allowed[s]:
                assignment[s]=g; used.add(g)
                if bt(i+1,used): return True
                used.discard(g); assignment.pop(s,None)
        return False
    ok=bt(0,set())
    slot_team={s:(team_by_group.get(assignment.get(s)) if ok else None) for s in slots}
    return thirds_sorted, qual_groups, slot_team

def _resolve_ref(ref, standings, slot_team):
    kind,key=ref
    rows=standings.get(key) if kind in ("1","2") else None
    if kind=="1": return rows[0]["team"] if rows else None
    if kind=="2": return rows[1]["team"] if rows and len(rows)>1 else None
    if kind=="3": return slot_team.get(key)
    return None

def _ko_match(home, away, momentum):
    if not home or not away: return {"home":home,"away":away,"sh":None,"sa":None,"winner":None,"tab":False}
    h,a,diff=compute(home,away,momentum)   # pas de facteur qualification en phase finale
    if h==a:
        winner = home if diff>=0 else away; tab=True   # nul -> tirs au but, le favori passe
    else:
        winner = home if h>a else away; tab=False
    return {"home":home,"away":away,"sh":h,"sa":a,"winner":winner,"tab":tab}

KO_NAMES={"r32":"16es de finale","r16":"8es de finale","qf":"Quarts de finale","sf":"Demi-finales","final":"Finale"}

def _bracket_orders():
    """Ordre d'AFFICHAGE des matchs par tour, dérivé de l'arbre officiel (KO_NEXT).
    Garantit que deux matchs visuellement adjacents alimentent bien le même match du
    tour suivant -> les branches du bracket suivent les bonnes lignes.
    Retourne {key: [match_id, ...]}."""
    feeders={mid:(a,b) for mid,a,b in KO_NEXT}   # match -> (feeder_a, feeder_b)
    parent={}
    for mid,(a,b) in feeders.items(): parent[a]=mid; parent[b]=mid
    def sub(mid):
        if mid in feeders:
            a,b=feeders[mid]; return sub(a)+sub(b)
        return [mid]   # feuille = match de 16es
    leaves=sub(104)    # 16 ids de 16es dans l'ordre de l'arbre
    orders={"r32":leaves}; cur=leaves
    for key in ("r16","qf","sf","final"):
        nxt=[]
        for i in range(0,len(cur),2):
            nxt.append(parent[cur[i]])
        orders[key]=nxt; cur=nxt
    return orders

def _ko_date_fr(datetimes, mid):
    """(date_fr_courte, heure_paris) pour un match KO depuis son utcDate, sinon ('','')."""
    iso=(datetimes or {}).get(str(mid))
    if not iso: return ("","")
    try:
        dt=datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))+datetime.timedelta(hours=2)
        mois={1:"janv.",2:"févr.",3:"mars",4:"avr.",5:"mai",6:"juin",7:"juil.",8:"août",
              9:"sept.",10:"oct.",11:"nov.",12:"déc."}
        return (f"{dt.day} {mois[dt.month]}", dt.strftime("%H:%M"))
    except Exception:
        return ("","")

def build_real_standings(rint):
    """Classement RÉEL-only (matchs joués uniquement), tous les 4 par groupe inclus.
    Sert au bracket 'Réel' (qualifiés provisoires d'après les vrais résultats)."""
    from collections import defaultdict
    table=defaultdict(lambda:defaultdict(lambda:{"Pts":0,"J":0,"G":0,"N":0,"P":0,"BP":0,"BC":0,"reels":0}))
    teams_by_grp=defaultdict(set)
    for mid,grp,date,h,a in GROUP_MATCHES:
        teams_by_grp[grp].add(h); teams_by_grp[grp].add(a)
        if mid in rint:
            rh,ra=rint[mid]["h"],rint[mid]["a"]
            th,ta=table[grp][h],table[grp][a]
            th["J"]+=1;ta["J"]+=1;th["BP"]+=rh;th["BC"]+=ra;ta["BP"]+=ra;ta["BC"]+=rh;th["reels"]+=1;ta["reels"]+=1
            if rh>ra: th["Pts"]+=3;th["G"]+=1;ta["P"]+=1
            elif ra>rh: ta["Pts"]+=3;ta["G"]+=1;th["P"]+=1
            else: th["Pts"]+=1;ta["Pts"]+=1;th["N"]+=1;ta["N"]+=1
    standings={}
    for grp,teams in teams_by_grp.items():
        for t in teams: table[grp][t]   # garantit la présence des 4 équipes
        ranked=sorted(table[grp].items(),key=lambda kv:(kv[1]["Pts"],kv[1]["BP"]-kv[1]["BC"],kv[1]["BP"]),reverse=True)
        standings[grp]=[{"team":t,"code":FLAG_CODES.get(t,""),"host":t in HOST_NATIONS,**st} for t,st in ranked]
    return standings

def build_knockout_real(real_standings, datetimes=None):
    """Bracket 'Réel' : 16es remplis selon le classement réel actuel (qualifiés provisoires),
    sans prédiction des vainqueurs. Les tours suivants restent à définir."""
    thirds_sorted, qual_groups, slot_team = _assign_thirds(real_standings)
    r32=[]
    for mid,ra,rb in KO_R32:
        home=_resolve_ref(ra,real_standings,slot_team); away=_resolve_ref(rb,real_standings,slot_team)
        d,h=_ko_date_fr(datetimes,mid)
        r32.append({"id":mid,"home":home,"away":away,"sh":None,"sa":None,"winner":None,"tab":False,
                    "ch":FLAG_CODES.get(home,""),"ca":FLAG_CODES.get(away,""),"date":d,"heure":h})
    def empty(ids,key):
        return {"key":key,"name":KO_NAMES[key],"matches":[
            {"id":i,"home":None,"away":None,"sh":None,"sa":None,"winner":None,"tab":False,
             "ch":"","ca":"","date":"","heure":""} for i in ids]}
    rounds=[{"key":"r32","name":KO_NAMES["r32"],"matches":r32},
            empty([89,90,91,92,93,94,95,96],"r16"),
            empty([97,98,99,100],"qf"), empty([101,102],"sf"), empty([104],"final")]
    order_map=_bracket_orders()
    for rd in rounds:
        om=order_map.get(rd["key"])
        if om:
            pos={m:i for i,m in enumerate(om)}
            rd["matches"].sort(key=lambda x:pos.get(x["id"],999))
    thirds_rank=[{"team":t[4],"code":FLAG_CODES.get(t[4],""),"grp":t[0],"Pts":t[1],"GD":t[2],"GF":t[3],
                  "qualified":t[0] in qual_groups} for t in thirds_sorted]
    return {"rounds":rounds,"thirds":thirds_rank}

def build_knockout(standings, momentum, datetimes=None):
    thirds_sorted, qual_groups, slot_team = _assign_thirds(standings)
    winners={}; rounds=[]
    r32=[]
    for mid,ra,rb in KO_R32:
        home=_resolve_ref(ra,standings,slot_team); away=_resolve_ref(rb,standings,slot_team)
        res=_ko_match(home,away,momentum); winners[mid]=res["winner"]
        res["id"]=mid; res["ch"]=FLAG_CODES.get(res["home"],""); res["ca"]=FLAG_CODES.get(res["away"],"")
        r32.append(res)
    rounds.append({"key":"r32","name":KO_NAMES["r32"],"matches":r32})
    def play(idset,key):
        arr=[]
        for mid,a,b in KO_NEXT:
            if mid not in idset: continue
            home=winners.get(a); away=winners.get(b)
            res=_ko_match(home,away,momentum); winners[mid]=res["winner"]
            res["id"]=mid; res["ch"]=FLAG_CODES.get(res["home"],""); res["ca"]=FLAG_CODES.get(res["away"],"")
            arr.append(res)
        rounds.append({"key":key,"name":KO_NAMES[key],"matches":arr})
    play({89,90,91,92,93,94,95,96},"r16")
    play({97,98,99,100},"qf")
    play({101,102},"sf")
    play({104},"final")
    # Réordonner chaque tour selon l'arbre officiel pour un tracé de branches correct
    order_map=_bracket_orders()
    for rd in rounds:
        om=order_map.get(rd["key"])
        if om:
            pos={mid:i for i,mid in enumerate(om)}
            rd["matches"].sort(key=lambda m: pos.get(m["id"], 999))
        # Date + heure officielles (Paris) par match, si disponibles
        for m in rd["matches"]:
            m["date"],m["heure"]=_ko_date_fr(datetimes, m["id"])
    champion = winners.get(104)
    thirds_rank=[{"team":t[4],"code":FLAG_CODES.get(t[4],""),"grp":t[0],"Pts":t[1],"GD":t[2],"GF":t[3],
                  "qualified":t[0] in qual_groups} for t in thirds_sorted]
    return {"rounds":rounds,"thirds":thirds_rank,"champion":champion,
            "champion_code":FLAG_CODES.get(champion,"")}

# ─── CONSTRUCTION DES DONNÉES DE LA PAGE ─────────────────────────────────────
def build_payload(results, scorers_by_team=None, datetimes=None, scorers_top=None):
    from collections import defaultdict
    scorers_by_team = scorers_by_team or {}
    scorers_top = scorers_top or []
    datetimes = datetimes or {}
    results={str(k):v for k,v in results.items()}
    momentum,detail=compute_momentum(results)
    qualif_states=compute_qualif_states(results)
    rint={int(k):v for k,v in results.items()}
    today_iso = datetime.date.today().isoformat()

    # Identifier les matchs de la 3e journée (derniers 2 matchs de chaque groupe)
    j3_ids=set()
    _by_grp=defaultdict(list)
    for mid,grp,date,home,away in GROUP_MATCHES:
        _by_grp[grp].append(mid)
    for grp,ids in _by_grp.items():
        for mid in ids[-2:]:   # les 2 derniers = 3e journée
            j3_ids.add(mid)

    matches=[]; n_exact=n_bon=n_rate=n_joue=0; n_today=0
    for mid,grp,date,home,away in GROUP_MATCHES:
        pih,pia,_=compute(home,away,None)
        # facteur qualification uniquement pour les 3es matchs
        qz = qualif_states if mid in j3_ids else None
        pah,paa,diffaj=compute(home,away,momentum,qz)
        joue=mid in rint
        reel=None; statut="avenir"; resume=""; resume_reel=""
        if joue:
            rh,ra=rint[mid]["h"],rint[mid]["a"]; reel=[rh,ra]
            po=0 if pih>pia else (1 if pih<pia else 2)
            ro=0 if rh>ra else (1 if rh<ra else 2)
            if pih==rh and pia==ra: statut="exact"; n_exact+=1
            elif po==ro: statut="bon"; n_bon+=1
            else: statut="rate"; n_rate+=1
            n_joue+=1
            resume, resume_reel = match_summary(home, away, rh, ra, statut, momentum, scorers_by_team)
        # === Date + heure + tri, à partir d'un instant UTC unique (cohérent) ===
        dt_utc = None
        api_iso = datetimes.get(str(mid))
        if api_iso:
            try:
                dt_utc = datetime.datetime.fromisoformat(api_iso.replace("Z","+00:00"))
            except Exception:
                dt_utc = None
        if dt_utc is None:
            # fallback : date programmée + heure UTC de la table officielle
            ku = KICKOFF_UTC.get(mid)
            try:
                base_d = datetime.date.fromisoformat(date)
                if ku:
                    hh,mm = ku.split(":")
                    dt_utc = datetime.datetime(base_d.year, base_d.month, base_d.day,
                                               int(hh), int(mm), tzinfo=datetime.timezone.utc)
                    if mid in KICKOFF_NEXTDAY:
                        dt_utc += datetime.timedelta(days=1)
                else:
                    # aucune heure connue : minuit UTC, tri en fin de journée
                    dt_utc = datetime.datetime(base_d.year, base_d.month, base_d.day,
                                               23, 59, tzinfo=datetime.timezone.utc)
            except Exception:
                dt_utc = None

        if dt_utc is not None:
            dt_paris = dt_utc + datetime.timedelta(hours=2)   # Paris = UTC+2 (été)
            paris_date = dt_paris.strftime("%Y-%m-%d")
            heure = dt_paris.strftime("%H:%M") if (KICKOFF_UTC.get(mid) or api_iso) else ""
            sort_key = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            paris_date = date; heure=""; sort_key = date + "T23:59:00Z"

        # Le "jour du match" = date OFFICIELLE FIFA (jour local sur place), pas la date de Paris.
        # C'est cette date qui sert au regroupement du feed ET au badge "match du jour"
        # (comportement type live feed L'Équipe). L'heure affichée reste l'heure de Paris.
        matchday_iso = date
        mmkey="06-"+matchday_iso.split("-")[2]
        day_fr = DATE_FR.get(mmkey, matchday_iso)
        # Si l'heure de Paris fait basculer le match au lendemain (matchs nocturnes aux Amériques),
        # on le signale discrètement à côté de l'heure.
        heure_note = ""
        if heure and paris_date != matchday_iso:
            try:
                pd = datetime.date.fromisoformat(paris_date)
                heure_note = pd.strftime("%d/%m")
            except Exception:
                heure_note = ""
        is_today = (matchday_iso == today_iso)
        if is_today: n_today += 1
        style_label, style_note = style_analysis(home, away)
        conf = confidence_pct(diffaj if not joue else compute(home,away,None)[2])
        # Surprise : favori net (>85 %) donné vainqueur mais battu par l'autre équipe (gros upset)
        surprise = bool(joue and conf > 85 and po in (0, 1) and ro in (0, 1) and po != ro)
        # Second choix : seulement pour les matchs à venir incertains (confiance < 70%)
        second = None
        if not joue and conf < 70:
            s_h, s_a, s_lbl = second_choice(home, away, diffaj)
            second = {"score":[s_h,s_a], "label":s_lbl}
        matches.append({
            "id":mid,"grp":grp,"date":day_fr,"day":day_fr,"heure":heure or "","heure_note":heure_note,
            "iso":matchday_iso,"sort":sort_key,"today":is_today,
            "home":home,"away":away,
            "ch":FLAG_CODES.get(home,""),"ca":FLAG_CODES.get(away,""),
            "host_h":home in HOST_NATIONS,"host_a":away in HOST_NATIONS,
            "prono":[pah,paa] if not joue else [pih,pia],
            "prono_initial":[pih,pia],"reel":reel,"statut":statut,"resume":resume,"resume_reel":resume_reel,
            "confidence":conf,"surprise":surprise,"second":second,
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

    knockout=build_knockout(standings, momentum, datetimes)
    real_standings=build_real_standings(rint)
    knockout_real=build_knockout_real(real_standings, datetimes)

    return {
        "maj":(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).strftime("%d/%m/%Y à %H:%M")+" (Paris)",
        "today":datetime.date.today().isoformat(),
        "version":MODEL_VERSION,
        "stats":{"joue":n_joue,"exact":n_exact,"bon":n_bon,"rate":n_rate,"total":72,"today":n_today},
        "matches":matches,"standings":standings,"momentum":mom_list,"knockout":knockout,
        "knockout_real":knockout_real,
        "scorers":scorers_top,
    }

# ─── GÉNÉRATION HTML ─────────────────────────────────────────────────────────
def render_html(payload):
    data_json=json.dumps(payload,ensure_ascii=False)
    tpl=open(os.path.join(ROOT,"template.html"),"r",encoding="utf-8").read()
    return tpl.replace("/*__DATA__*/null", data_json)

def main():
    results, datetimes = load_results()
    scorers, scorers_top = fetch_scorers()
    if scorers:
        print(f"[OK] Buteurs récupérés pour {len(scorers)} équipe(s) ; {len(scorers_top)} buteur(s) classés")
    payload=build_payload(results, scorers, datetimes, scorers_top)
    html=render_html(payload)
    out=os.path.join(ROOT,"index.html")
    with open(out,"w",encoding="utf-8") as f:
        f.write(html)
    # data.json : données structurées réutilisables (service worker pour les notifications, etc.)
    with open(os.path.join(ROOT,"data.json"),"w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    s=payload["stats"]
    print(f"[OK] index.html généré — {s['joue']} joués | {s['exact']} exacts, {s['bon']} bons, {s['rate']} ratés | {s['today']} match(s) aujourd'hui")

if __name__=="__main__":
    main()
