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
Pronostics IA — Coupe du Monde 2026
Récupère les scores réels via football-data.org, calcule la dynamique (momentum)
des sélections, met à jour les pronostics des matchs à venir et génère index.html.

Lancé quotidiennement par GitHub Actions. Fonctionne aussi sans clé API
(mode repli) en lisant data/results_manual.json.
"""

import os, json, sys, datetime, urllib.request, urllib.error, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
API_KEY = os.environ.get("FOOTBALLDATA_KEY", "").strip()
API_BASE = "https://api.football-data.org/v4"
WC_CODE = "WC"        # football-data.org : code compétition FIFA World Cup

# Version du modèle de pronostic (affichée dans le pied de page).
# Historique : 1.x base · 2.0 facteur qualification + dynamique · 2.1 règles 2026 (compression ciblée)
#             · 2.2 variation réaliste des scores (distribution CM 2010-2022, graine par affiche)
#             · 2.3 ajustement dynamique conservateur : forme off/déf réelle, tendance de buts du
#                   tournoi, pondération récence, blend force FIFA ↔ performances observées
MODEL_VERSION = "3.5"

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


# ─── RATINGS ELO RÉELS (Lot 1 — V3) ──────────────────────────────────────────
# Forces de base des pronos de PHASE FINALE issues des World Football Elo Ratings
# (eloratings.net), figées au coup d'envoi dans data/elo_snapshot.json (aucune
# dépendance réseau à l'exécution). La phase de groupes (notée, gelée) n'est PAS
# affectée : elle continue d'utiliser TEAM_DATA via compute().
def load_elo():
    try:
        with open(os.path.join(ROOT, "data", "elo_snapshot.json"), encoding="utf-8") as fh:
            return {k: float(v) for k, v in json.load(fh).get("elo", {}).items()}
    except Exception as e:
        print(f"[ELO] snapshot indisponible ({e}) — repli sur TEAM_DATA*180+1300", file=sys.stderr)
        return {}
ELO = load_elo()
def load_calibration():
    """Paramètres apprenables (auto-calibrés par learn.py). Repli sur les défauts actuels."""
    d = {"ko_sup_div":240.0,"ko_mu":[2.95,2.80,2.64],"ko_coinflip":0.025,
         "exp_w0":0.22,"exp_w1":0.18,"group_draw_band":0.0,
         # Surcouche « défense d'élite » (KO, matchs à venir uniquement). Bonus LÉGER, gradué :
         # buts encaissés/match sur les 10 derniers résultats de l'adversaire défensif.
         # def_elite_zero = seuil au-dessus duquel AUCUN bonus (≈ défense moyenne) ;
         # def_elite_full = seuil au/en-dessous duquel bonus MAXIMAL ; def_elite_k = réduction
         # maximale du lambda offensif de l'équipe qui AFFRONTE cette défense (ex. 0.15 = -15 %).
         "def_elite_zero":0.90,"def_elite_full":0.20,"def_elite_k":0.15}
    try:
        with open(os.path.join(ROOT,"data","calibration.json"),encoding="utf-8") as fh:
            j=json.load(fh)
            for k in d:
                if k in j: d[k]=j[k]
    except Exception as e:
        print(f"[CALIB] défauts ({e})", file=sys.stderr)
    return d
CALIB = load_calibration()
# Elo DYNAMIQUE : recalculé à chaque run depuis le snapshot figé + tous les vrais
# résultats du tournoi (groupes + phases finales jouées). Rempli par build_payload.
# Rend les projections KO auto-entretenues au fil des rencontres (déterministe/reproductible).
LIVE_ELO = {}
LIVE_FORM = {}   # forme (att/déf) mise à jour par les buts réels du tournoi
LIVE_MOM = {}    # surcouche momentum (récence + victoire de prestige), en points Elo
VENUES = {}      # {match_id(str): lieu (stade/ville)} récupéré de l'API football-data
ELO_DEFAULT = 1700.0
HOST_ELO_BONUS = 60.0   # avantage hôte exprimé en points Elo

def team_elo(team):
    """Elo de l'équipe : version LIVE (mise à jour par les résultats réels) si dispo,
    sinon snapshot figé, sinon repli déterministe dérivé de TEAM_DATA."""
    if team in LIVE_ELO: return LIVE_ELO[team]
    if team in ELO: return ELO[team]
    base = TEAM_DATA.get(team, (6.0,))[0]
    return 1300.0 + base * 90.0   # mappe ~3.8→1642 .. 9.1→2119 (ordre conservé)

# ─── FORME RÉCENTE (≈50 matchs) + CONFRONTATIONS DIRECTES (V3.1) ──────────────
# Profils offensifs/défensifs figés (data/team_form.json) et bilans des duels
# (data/h2h.json), committés, sans dépendance réseau. Régénérables via build_stats.py.
def _load_json(name, key):
    try:
        with open(os.path.join(ROOT, "data", name), encoding="utf-8") as fh:
            return json.load(fh).get(key, {})
    except Exception as e:
        print(f"[{name}] indisponible ({e})", file=sys.stderr)
        return {}
FORM = _load_json("team_form.json", "form")
H2H  = _load_json("h2h.json", "h2h")
AVG_FORM = 1.45   # buts/match de référence (attaque ET défense)

# ─── Pronos KO FIGÉS (stabilité) ──────────────────────────────────────────────
# Un prono de phase finale est calculé UNE fois (24 h avant le coup d'envoi) puis figé
# dans data/ko_pronos.json. Ensuite il ne bouge plus : le prono affiché la veille est
# EXACTEMENT celui qui sera noté (fini la dérive du score au fil des runs / de l'Elo live).
def _load_ko_frozen():                                # chargement SILENCIEUX (fichier optionnel)
    try:
        with open(os.path.join(ROOT, "data", "ko_pronos.json"), encoding="utf-8") as fh:
            return json.load(fh).get("pronos", {})
    except Exception:
        return {}                                     # absent tant qu'aucun match n'a encore été figé
KO_FROZEN = _load_ko_frozen()                         # {"102": {pred complet + home/away/frozen_at}}
_KO_FROZEN_OUT = dict(KO_FROZEN)                      # ré-écrit à chaque run (avec les nouveaux gels)
_KO_FROZEN_DIRTY = [False]                            # drapeau mutable : un nouveau gel a eu lieu
FREEZE_LEAD_H = 24                                    # on fige le prono 24 h avant le coup d'envoi

def team_form(team):
    fm = LIVE_FORM.get(team) or FORM.get(team)
    if fm: return fm.get("gf", AVG_FORM), fm.get("ga", AVG_FORM)
    # repli : dérive un profil de la force TEAM_DATA (fort -> marque +, encaisse -)
    base = TEAM_DATA.get(team, (6.0,))[0]
    return AVG_FORM * (0.75 + base/24.0), AVG_FORM * (1.25 - base/24.0)

def recent_ga(team):
    """Buts encaissés/match sur les 10 DERNIERS résultats (solidité défensive récente).
    Source : data/team_form.json (champ ga10, régénéré par build_stats.py depuis le dataset
    CC0 — régénérer pendant/après la CdM pour que la fenêtre inclue le tournoi). Renvoie None
    si la donnée n'est pas encore committée -> la surcouche « défense d'élite » reste alors
    INERTE (aucune modification des pronos), ce qui garantit un déploiement sans risque."""
    fm = FORM.get(team)
    if fm and isinstance(fm.get("ga10"), (int, float)):
        return float(fm["ga10"])
    return None

def elite_def_factor(defender):
    """Facteur multiplicatif (<= 1.0) appliqué au lambda offensif de l'équipe qui AFFRONTE
    `defender`, pour valoriser LÉGÈREMENT les défenses d'élite (celles que le plancher de forme
    à 0,78 sous-évalue). Gradué et borné : 1.0 (aucun effet) au-dessus de def_elite_zero,
    jusqu'à (1 - def_elite_k) au niveau de def_elite_full. Neutre si la donnée ga10 manque."""
    g = recent_ga(defender)
    if g is None: return 1.0
    zero = CALIB["def_elite_zero"]; full = CALIB["def_elite_full"]; k = CALIB["def_elite_k"]
    if g >= zero or zero <= full: return 1.0
    s = (zero - g) / (zero - full)            # 0 à def_elite_zero -> 1 à def_elite_full
    s = max(0.0, min(1.0, s))
    return 1.0 - k * s

def h2h_nudge(home, away):
    return H2H.get("|".join(sorted([home, away])))



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

# ─── Calendrier officiel des matchs à élimination directe (numérotation FIFA) ──
# utcDate officiel par numéro de match FIFA (M°73 → M°104, + M°103 = 3e place).
# Source : fifa.com (bracket Canada/Mexique/USA 2026). Les numéros FIFA ne sont PAS
# chronologiques : ce calendrier sert à (a) mapper chaque fixture de l'API au BON
# numéro de match (tri par heure officielle, pas par ordre numérique) et (b) afficher
# une date de repli si l'API ne renvoie pas encore l'horaire.
KO_KICKOFF_UTC = {
    73:"2026-06-28T19:00:00Z", 74:"2026-06-29T20:30:00Z", 75:"2026-06-30T01:00:00Z", 76:"2026-06-29T17:00:00Z",
    77:"2026-06-30T21:00:00Z", 78:"2026-06-30T17:00:00Z", 79:"2026-07-01T01:00:00Z", 80:"2026-07-01T16:00:00Z",
    81:"2026-07-02T00:00:00Z", 82:"2026-07-01T20:00:00Z", 83:"2026-07-02T23:00:00Z", 84:"2026-07-02T19:00:00Z",
    85:"2026-07-03T03:00:00Z", 86:"2026-07-03T22:00:00Z", 87:"2026-07-04T01:30:00Z", 88:"2026-07-03T18:00:00Z",
    89:"2026-07-04T21:00:00Z", 90:"2026-07-04T17:00:00Z", 91:"2026-07-05T20:00:00Z", 92:"2026-07-06T00:00:00Z",
    93:"2026-07-06T19:00:00Z", 94:"2026-07-07T00:00:00Z", 95:"2026-07-07T16:00:00Z", 96:"2026-07-07T20:00:00Z",
    97:"2026-07-09T20:00:00Z", 98:"2026-07-10T19:00:00Z", 99:"2026-07-11T21:00:00Z", 100:"2026-07-12T01:00:00Z",
    101:"2026-07-14T19:00:00Z",102:"2026-07-15T19:00:00Z",103:"2026-07-18T21:00:00Z",104:"2026-07-19T19:00:00Z",
}

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

# Ouverture du jeu par style (effet sur le total de buts attendu d'un match KO) :
# pressing/possession -> plus ouvert ; bloc bas/médian -> plus fermé.
STYLE_OPEN = {"pressing": 0.18, "possession": 0.12, "contre": 0.00, "bloc_moyen": -0.10, "bloc_bas": -0.20}

# Expérience des grands matchs (pedigree tournoi, 0..1) : compte surtout dans les tours
# décisifs (gestion de la pression, parcours profonds récents). Distinct de l'Elo courant
# (ex. Croatie / Maroc surperforment leur niveau dans les grands rendez-vous).
EXPERIENCE = {
    "Argentine":0.95,"Brésil":0.92,"Allemagne":0.92,"France":0.90,"Espagne":0.88,
    "Angleterre":0.85,"Pays-Bas":0.85,"Portugal":0.84,"Uruguay":0.82,"Croatie":0.85,
    "Belgique":0.78,"Mexique":0.75,"Maroc":0.78,"Suisse":0.70,"États-Unis":0.68,
    "Japon":0.68,"Corée du Sud":0.66,"Colombie":0.68,"Suède":0.64,"Sénégal":0.66,
    "Australie":0.62,"Ghana":0.62,"Norvège":0.55,"Autriche":0.60,"Écosse":0.55,
    "Turquie":0.60,"Égypte":0.60,"Algérie":0.60,"Côte d'Ivoire":0.62,"Iran":0.60,
    "Paraguay":0.58,"Équateur":0.60,"Tunisie":0.58,"Canada":0.52,"Tchéquie":0.62,
    "Cap-Vert":0.45,"RD Congo":0.50,"Ouzbékistan":0.42,"Afrique du Sud":0.52,
    "Arabie Saoudite":0.52,"Irak":0.48,"Jordanie":0.42,"Curaçao":0.40,"Haïti":0.40,
    "Nouvelle-Zélande":0.45,"Panama":0.45,"Bosnie-Herzégovine":0.55,"Qatar":0.48,
}
def experience(team): return EXPERIENCE.get(team, 0.55)

def _score_from_diff(diff, home, away, hs, as_, asur, ko=False, ko_tier=0):
    """Score réaliste AVEC variation, calé sur la distribution des scores des Coupes
    du Monde récentes (1-0, 2-1, 2-0, 1-1, 0-0, 3-1… cf. stats FIFA 2010-2022).
    Le résultat (vainqueur/nul) suit l'écart de force ; le SCORE exact est tiré d'un
    panier réaliste via une graine STABLE par affiche -> fini les 1-0 partout, on
    retrouve une vraie diversité (2-1, 2-0, 3-1, 0-0…) reproductible d'un run à l'autre.
    Paniers exprimés (buts favori, buts adverse)."""
    ad=abs(diff)
    if ko:
        # Phases finales : plus fermé, moins de buts (étude CM 2010-2022), se resserre par tour
        # (ko_tier : 0 = 16es/8es, 1 = quarts/demies, 2 = finale).
        if ko_tier>=2:
            if   ad>=2.4: pool=[(2,0),(1,0),(2,1)]
            elif ad>=1.2: pool=[(1,0),(2,1),(1,1),(0,0)]
            else:         pool=[(0,0),(1,1),(1,0)]
        elif ko_tier==1:
            if   ad>=2.4: pool=[(2,0),(2,1),(1,0),(3,1)]
            elif ad>=1.2: pool=[(1,0),(2,1),(2,0),(1,1)]
            elif ad>=0.45:pool=[(1,0),(1,1),(2,1),(0,0)]
            else:         pool=[(0,0),(1,1),(1,0)]
        else:
            if   ad>=2.8: pool=[(3,0),(2,0),(2,1),(3,1)]
            elif ad>=1.6: pool=[(2,0),(2,1),(1,0),(3,1)]
            elif ad>=0.9: pool=[(2,1),(1,0),(2,0),(1,1)]
            elif ad>=0.45:pool=[(1,0),(2,1),(1,1),(0,0)]
            else:         pool=[(1,0),(1,1),(0,0),(2,1)]
    elif   ad>=3.2: pool=[(4,0),(3,0),(3,1),(5,0),(4,1),(2,0)]   # écrasant
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

def _adjust_goals(h, a, diff, home, away, dyn):
    """v2.3 — Ajustement CONSERVATEUR du score à venir selon la forme observée :
    forme offensive/défensive réelle des deux équipes + tendance de buts du tournoi.
    Au plus 1 but de variation, en PRÉSERVANT le vainqueur (ou le nul). N'agit qu'après
    quelques matchs disputés (assez de données)."""
    if not dyn or dyn.get("n", 0) < 4:
        return h, a
    off = dyn.get("off", {}); dfn = dyn.get("def_", {}); tg = dyn.get("tg") or 2.4
    base = 1.20
    env = max(0.85, min(1.15, tg / 2.4))          # environnement de scoring (±15 % max)
    eh = (0.6 * base + 0.2 * off.get(home, base) + 0.2 * dfn.get(away, base)) * env
    ea = (0.6 * base + 0.2 * off.get(away, base) + 0.2 * dfn.get(home, base)) * env
    gap = (eh + ea) - (h + a)
    seed = 0
    for ch in (home + "#" + away): seed = (seed * 31 + ord(ch)) & 0xffffffff
    if gap >= 1.0 and seed % 2 == 0:              # match attendu plus prolifique : +1 but
        if h > a: h += 1
        elif a > h: a += 1
        elif gap >= 2.0: h += 1; a += 1           # nul : ne s'ouvre que si écart marqué
    elif gap <= -1.0 and seed % 2 == 1:           # attendu plus fermé : -1 but (préserve le signe)
        if h > a and a >= 1: a -= 1
        elif a > h and h >= 1: h -= 1
        elif h == a and h >= 1: h -= 1; a -= 1
    return h, a

def compute(home,away,momentum=None,qualif=None,dyn=None,ko=False,ko_tier=0):
    mo=momentum or {}; qz=qualif or {}; dy=dyn or {}
    hf0,ht,hs,hsur=TEAM_DATA[home]; af0,at,as_,asur=TEAM_DATA[away]
    tb={"up":0.4,"down":-0.4,"stable":0}
    hF=hf0+tb[ht]+mo.get(home,0.0); aF=af0+tb[at]+mo.get(away,0.0)
    if home in HOST_NATIONS: hF+=HOST_BONUS
    if away in HOST_NATIONS: aF+=HOST_BONUS
    # Facteur qualification (3e match de poule) : une équipe déjà qualifiée lève le pied (turnover),
    # une équipe qui joue sa survie est galvanisée, une équipe éliminée est démobilisée.
    qb={"qualified":-0.35,"alive":0.20,"eliminated":-0.25,None:0.0}
    hF+=qb.get(qz.get(home),0.0); aF+=qb.get(qz.get(away),0.0)
    # Tactiques OBSERVÉES en phase de groupe (proxy buts marqués/encaissés) : si disponibles,
    # elles priment sur le style théorique pour le clash tactique.
    sty=dy.get("styles",{})
    hs_eff=sty.get(home) or hs; as_eff=sty.get(away) or as_
    sbh,sba=style_bonus(hs_eff,as_eff); hF+=sbh; aF+=sba
    # v2.3 — blend force FIFA <-> niveau réel observé (conservateur, plafonné dans compute_form)
    lvl=dy.get("level",{})
    hF+=lvl.get(home,0.0); aF+=lvl.get(away,0.0)
    diff=hF-aF
    h,a=_score_from_diff(diff, home, away, hs, as_, asur, ko, ko_tier)
    h,a=_adjust_goals(h, a, diff, home, away, dy)
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

def match_summary(home, away, rh, ra, statut, mom_after, scorers_by_team, tab=False, pred_draw=False):
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
        verdict = ("Nul exactement anticipé et bon qualifié désigné ; départage aux tirs au but."
                   if tab else "Résultat exactement conforme au pronostic IA.")
    elif statut == "bon":
        verdict = ("Le nul (temps réglementaire + prolongation) et le bon qualifié avaient été anticipés, à un score près ; départage aux tirs au but."
                   if tab else "Le bon vainqueur avait été anticipé, mais pas le score exact.")
    elif tab and pred_draw:
        verdict = "Nul bien anticipé, mais le mauvais qualifié a été désigné : les tirs au but ont fait passer l'autre équipe — pronostic non validé."
    elif tab:
        verdict = "Match nul, décidé aux tirs au but : le pronostic annonçait une issue nette — le match serré n'avait pas été anticipé."
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
    # Résumé complet (mode Prono de Nono) : factuel + verdict + dynamique
    parts = list(reel_parts)
    parts.append(verdict + dyn)
    return " ".join(parts).strip(), resume_reel

def compute_momentum(results, ko_fixtures=None, datetimes=None):
    """Dynamique (forme V/N/D) avec PONDÉRATION RÉCENCE (v2.3) : les derniers matchs
    d'une équipe pèsent un peu plus (rampe douce 0.85 -> 1.15). Plafonné ±1.2.
    Inclut la phase de groupes ET les phases finales jouées (la dynamique continue)."""
    from collections import defaultdict
    by_id={m[0]:m for m in GROUP_MATCHES}
    per_team=defaultdict(list)
    def _add_event(sort_date, ord_key, home, away, rh, ra):
        hf=TEAM_DATA.get(home,(6.0,))[0]; af=TEAM_DATA.get(away,(6.0,))[0]
        for team,gf,ga,opp_f in [(home,rh,ra,af),(away,ra,rh,hf)]:
            if team not in TEAM_DATA: continue
            if gf>ga: base=0.30; tag="V"
            elif gf<ga: base=-0.30; tag="D"
            else: base=0.0; tag="N"
            margin_bonus=max(-3,min(3,gf-ga))*0.07
            gap=opp_f-TEAM_DATA[team][0]; surprise=0.0
            if gf>ga and gap>0: surprise=gap*0.10
            elif gf<ga and gap<0: surprise=gap*0.10
            elif gf==ga and gap>0: surprise=gap*0.05
            per_team[team].append((sort_date, ord_key, base+margin_bonus+surprise, f"{tag} {gf}-{ga}"))
    # Phase de groupes
    for mid,sc in results.items():
        mid=int(mid)
        if mid not in by_id: continue
        _,grp,date,home,away=by_id[mid]
        _add_event(date, mid, home, away, sc["h"], sc["a"])
    # Phases finales jouées (clé de tri "zzz###" -> toujours APRÈS les poules)
    for mid_s,fx in (ko_fixtures or {}).items():
        if not (fx.get("home") and fx.get("away") and fx.get("hs") is not None
                and fx.get("as") is not None and fx.get("status") in ("FINISHED","AWARDED")):
            continue
        try: mk=int(mid_s)
        except Exception: continue
        _add_event("zzz%03d"%mk, 1000+mk, fx["home"], fx["away"], int(fx["hs"]), int(fx["as"]))
    momentum={}; detail={}
    for team,lst in per_team.items():
        lst.sort(key=lambda x:(x[0],x[1]))            # chronologique
        k=len(lst); s=0.0
        for i,(d,mid,contrib,tg) in enumerate(lst):
            w=1.0 if k==1 else (0.85+0.30*(i/(k-1)))   # récence : le dernier match pèse +
            s+=contrib*w
        momentum[team]=max(-1.2,min(1.2,s))
        detail[team]=[x[3] for x in lst]
    return momentum, detail

def compute_form(results):
    """v2.3 — Forme OBSERVÉE à partir des vrais résultats :
       off[team]   = buts marqués / match      def_[team] = buts encaissés / match
       level[team] = niveau réel (pts/match + diff de buts), plafonné ±0.35, montée en confiance
       tg          = buts moyens / match du tournoi (tendance de scoring)
       n           = nombre de matchs joués."""
    from collections import defaultdict
    by_id={m[0]:m for m in GROUP_MATCHES}
    gs=defaultdict(int); gc=defaultdict(int); pts=defaultdict(int); pl=defaultdict(int)
    tot_goals=0; tot_matches=0
    for mid,sc in results.items():
        mid=int(mid)
        if mid not in by_id: continue
        _,grp,date,home,away=by_id[mid]
        rh,ra=sc["h"],sc["a"]; tot_goals+=rh+ra; tot_matches+=1
        for team,gf,ga in [(home,rh,ra),(away,ra,rh)]:
            gs[team]+=gf; gc[team]+=ga; pl[team]+=1
            if gf>ga: pts[team]+=3
            elif gf==ga: pts[team]+=1
    off={}; dfn={}; level={}
    for t in pl:
        n=pl[t]; off[t]=gs[t]/n; dfn[t]=gc[t]/n
        raw=((pts[t]/n)-1.0)*0.20 + ((gs[t]-gc[t])/n)*0.10
        level[t]=max(-0.35,min(0.35,raw))*min(1.0,n/2.0)
    styles={}
    for t in pl:
        if pl[t]>=2:                      # assez de matchs pour lire la tactique
            gf=off[t]; ga=dfn[t]
            if   gf<1.1 and ga<1.0:  styles[t]="bloc_bas"     # ferme, peu de buts des deux cotes
            elif gf>=1.7 and ga<=1.0: styles[t]="possession"  # domine et controle
            elif gf>=1.6 and ga>=1.3: styles[t]="pressing"    # joue haut, match ouvert
            elif gf<=1.2 and ga>=1.4: styles[t]="contre"      # subit, joue en contre
    tg=(tot_goals/tot_matches) if tot_matches else 0.0
    return {"off":off,"def_":dfn,"level":level,"tg":tg,"n":tot_matches,"styles":styles}

# ─── RÉCUPÉRATION DES RÉSULTATS ──────────────────────────────────────────────
def _ko_score_from_api(home, away, row):
    """Construit l'entrée ko_fixtures à partir d'une fixture API football-data.

    Règle football-data : score.fullTime INCLUT les buts des tirs au but.
    On affiche donc le score AVANT t.a.b. (fin du temps réglementaire / prolongation),
    on garde le score des t.a.b. à part, et on désigne le qualifié via score.winner
    (repli sur le score des t.a.b. puis sur le score réglementaire)."""
    ft_h, ft_a = row.get("ft_h"), row.get("ft_a")
    rt_h, rt_a = row.get("rt_h"), row.get("rt_a")
    et_h, et_a = row.get("et_h"), row.get("et_a")
    pen_h, pen_a = row.get("pen_h"), row.get("pen_a")
    duration = row.get("duration")
    shootout = (duration == "PENALTY_SHOOTOUT") or (pen_h is not None and pen_a is not None)
    # Score AFFICHÉ = score « sur le terrain », hors t.a.b.
    #  1) score réglementaire (+ prolongation) si l'API le fournit (le plus fiable) ;
    #  2) sinon fullTime − t.a.b. (football-data : fullTime INCLUT les t.a.b.) ;
    #  3) sinon fullTime brut.
    if rt_h is not None and rt_a is not None:
        disp_h = rt_h + (et_h or 0); disp_a = rt_a + (et_a or 0)
    elif shootout and None not in (ft_h, ft_a, pen_h, pen_a):
        disp_h, disp_a = ft_h - pen_h, ft_a - pen_a
    else:
        disp_h, disp_a = ft_h, ft_a
    # t.a.b. décisifs (un vrai vainqueur aux tirs : scores différents) ?
    pen_decisive = (pen_h is not None and pen_a is not None and pen_h != pen_a)
    on_pitch_draw = (disp_h is not None and disp_h == disp_a)
    # On ne signale « t.a.b. » que si la séance a un sens affichable :
    # match nul sur le terrain, OU séance de tirs décisive.
    tab = bool(shootout and (on_pitch_draw or pen_decisive))
    # Qualifié : champ winner de l'API d'abord, puis t.a.b. décisifs, puis score affiché.
    winner = row.get("winner")
    if winner not in ("HOME_TEAM", "AWAY_TEAM"):
        if pen_decisive:
            winner = "HOME_TEAM" if pen_h > pen_a else "AWAY_TEAM"
        elif disp_h is not None and disp_a is not None and disp_h != disp_a:
            winner = "HOME_TEAM" if disp_h > disp_a else "AWAY_TEAM"
        else:
            winner = None
    # On n'expose le score des t.a.b. que s'il est décisif (sinon valeur non fiable).
    show_penh = int(pen_h) if (tab and pen_decisive) else None
    show_pena = int(pen_a) if (tab and pen_decisive) else None
    return {"home":home, "away":away,
            "hs":(int(disp_h) if disp_h is not None else None),
            "as":(int(disp_a) if disp_a is not None else None),
            "penh":show_penh, "pena":show_pena, "tab":tab,
            "status":row.get("status",""), "winner":winner}

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
    VENUES.clear()
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
        _v=fx.get("venue")
        if _v: VENUES[str(mid)]=_v
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
            sc=fx.get("score") or {}
            ft=sc.get("fullTime") or {}; rt=sc.get("regularTime") or {}
            et=sc.get("extraTime") or {}; pen=sc.get("penalties") or {}
            hn=map_team((fx.get("homeTeam") or {}).get("name"), (fx.get("homeTeam") or {}).get("tla"))
            an=map_team((fx.get("awayTeam") or {}).get("name"), (fx.get("awayTeam") or {}).get("tla"))
            by_stage.setdefault(st,[]).append({
                "utc":fx["utcDate"], "id":fx.get("id") or 0, "hn":hn, "an":an,
                "ft_h":ft.get("home"), "ft_a":ft.get("away"),
                "rt_h":rt.get("home"), "rt_a":rt.get("away"),
                "et_h":et.get("home"), "et_a":et.get("away"),
                "pen_h":pen.get("home"), "pen_a":pen.get("away"),
                "duration":sc.get("duration"), "status":fx.get("status",""),
                "winner":sc.get("winner"), "venue":fx.get("venue")})
    ko_fixtures={}
    for st,ids in KO_STAGE_IDS.items():
        # IMPORTANT : les numéros de match FIFA ne sont PAS chronologiques.
        # On apparie donc les fixtures triées par heure réelle (API) aux ids du
        # tour eux-mêmes triés par heure officielle (KO_KICKOFF_UTC) -> chaque
        # fixture tombe sur le BON numéro de match FIFA.
        ids_by_time=sorted(ids, key=lambda m: KO_KICKOFF_UTC.get(m, "9999"))
        rows_by_time=sorted(by_stage.get(st,[]), key=lambda r:(r["utc"], r["id"]))
        for i,row in enumerate(rows_by_time):
            if i>=len(ids_by_time): break
            mid=str(ids_by_time[i]); datetimes[mid]=row["utc"]
            ko_fixtures[mid]=_ko_score_from_api(row["hn"], row["an"], row)
            if row.get("venue"): VENUES[mid]=row["venue"]

    return results, datetimes, ko_fixtures

def fetch_scorers():
    """Récupère les meilleurs buteurs du tournoi (endpoint /scorers, dispo en gratuit).
    Retourne (by_team, top_list) :
      - by_team : {nom_equipe_FR: [noms_joueurs]} (utilisé dans les résumés de match)
      - top_list : [{'player','team','code','goals','assists'}] trié par buts décroissant
    (..., []) si indisponible."""
    if not API_KEY:
        return {}, [], []
    # L'affichage montre le TOP 5 buteurs (les passeurs sont masqués, cf. render_html) :
    # on se limite au top 10, largement suffisant, et on allège fortement le payload
    # (on était monté à 300 pour les passeurs, devenu inutile depuis le masquage).
    payload=None
    for lim in (10,):
        try:
            url=f"{API_BASE}/competitions/{WC_CODE}/scorers?limit={lim}"
            req=urllib.request.Request(url, headers={"X-Auth-Token":API_KEY})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload=json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            print(f"[INFO] Buteurs limit={lim} indisponible : {e}", file=sys.stderr)
    if payload is None:
        return {}, [], []
    by_team={}; top_list=[]; assists_list=[]
    for sc in payload.get("scorers", []):
        player=(sc.get("player") or {}).get("name")
        team_obj=sc.get("team") or {}
        team=map_team(team_obj.get("name"), team_obj.get("tla"))
        goals=sc.get("goals") or 0
        assists=sc.get("assists") or 0
        if not (player and team):
            continue
        if goals:
            by_team.setdefault(team, []).append(player)
            top_list.append({"player":player,"team":team,"code":FLAG_CODES.get(team,""),
                             "goals":int(goals),"assists":int(assists)})
        if assists:
            assists_list.append({"player":player,"team":team,"code":FLAG_CODES.get(team,""),
                                 "assists":int(assists),"goals":int(goals)})
    # buteurs : buts décroissants ; passeurs : passes décisives décroissantes
    top_list.sort(key=lambda x:(-x["goals"], -x["assists"], x["player"]))
    assists_list.sort(key=lambda x:(-x["assists"], -x["goals"], x["player"]))
    return by_team, top_list, assists_list

def load_results():
    """API en priorité, repli sur data/results_manual.json.
    Retourne (results, datetimes)."""
    out=fetch_from_api()
    if out is not None:
        api, datetimes, ko_fixtures = out
        if len(api)>0 or len(datetimes)>0:
            if len(api)>0:
                print(f"[OK] {len(api)} résultat(s) récupéré(s) via football-data.org")
            if len(datetimes)>0:
                print(f"[OK] {len(datetimes)} horaire(s) officiel(s) récupéré(s)")
            manual=load_manual()
            merged=dict(manual); merged.update(api)
            save_manual(merged, datetimes, ko_fixtures)
            return merged, load_datetimes(datetimes), load_ko_fixtures(ko_fixtures)
    print("[INFO] API indisponible ou vide → repli sur les données locales")
    return load_manual(), load_datetimes({}), load_ko_fixtures({})

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

def load_ko_fixtures(fresh):
    """Fusionne les affiches de phase finale fraîchement récupérées avec celles stockées."""
    stored={}
    p=os.path.join(ROOT,"data","results_manual.json")
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f:
            stored=json.load(f).get("ko_affiches",{})
    merged=dict(stored); merged.update(fresh or {})
    return merged

def load_ko_overrides():
    """Overrides manuels de phases finales pour les cas où football-data ne fournit pas
    le qualifié / le score des t.a.b. (fréquent en plan gratuit sur séances de tirs au but).
    Format dans data/results_manual.json :
        "ko_resultats": { "74": {"pen_h":3,"pen_a":4}, "75": {"pen_h":2,"pen_a":3} }
    Clés optionnelles : "h","a" (score réglementaire si l'API ne l'a pas), "winner":"home"/"away"."""
    p=os.path.join(ROOT,"data","results_manual.json")
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as fh:
            return json.load(fh).get("ko_resultats",{}) or {}
    return {}

def load_af_fixtures():
    """Cache d'enrichissement API-Football (Lot 1) : {numéro FIFA(str): champs}.
    Renvoie {} si absent (le site continue normalement sur football-data)."""
    p=os.path.join(ROOT,"data","af_fixtures.json")
    if os.path.exists(p):
        try:
            with open(p,encoding="utf-8") as fh:
                d=json.load(fh); d.pop("_meta",None); return d
        except Exception: return {}
    return {}

def apply_af_enrichment(ko_fixtures):
    """Lot 1 — quick wins API-Football : lieu (stade/ville) fiable + tirs au but fiables.
    L'enrichissement PRIME sur football-data quand il est présent."""
    af=load_af_fixtures()
    for mid,rec in af.items():
        # Lieu : alimente VENUES pour TOUS les matchs (groupes + phases finales)
        ven=rec.get("venue"); city=rec.get("city")
        if ven or city:
            VENUES[str(mid)]=", ".join([x for x in (ven,city) if x])
        # Tirs au but : pour les matchs KO présents dans ko_fixtures
        fx=ko_fixtures.get(str(mid))
        if not fx: continue
        ph,pa=rec.get("penh"),rec.get("pena")
        if ph is not None and pa is not None:
            fx["penh"]=int(ph); fx["pena"]=int(pa); fx["tab"]=True
            if ph!=pa: fx["winner"]="HOME_TEAM" if ph>pa else "AWAY_TEAM"
        w=rec.get("winner")
        if w in ("home","away"):
            fx["winner"]="HOME_TEAM" if w=="home" else "AWAY_TEAM"
        # Score "sur le terrain" (hors t.a.b.) plus fiable que football-data
        if rec.get("sh") is not None and rec.get("sa") is not None:
            fx["hs"]=int(rec["sh"]); fx["as"]=int(rec["sa"])
    return ko_fixtures

def apply_ko_overrides(ko_fixtures):
    """Complète ko_fixtures avec les overrides manuels (qualifié + t.a.b.) — l'override
    PRIME sur l'API pour le vainqueur, car le flux gratuit perd parfois ce champ."""
    ovr=load_ko_overrides()
    for mid,o in (ovr or {}).items():
        fx=ko_fixtures.get(str(mid))
        if not fx:
            continue
        ph,pa=o.get("pen_h"),o.get("pen_a")
        if "h" in o and fx.get("hs") is None: fx["hs"]=int(o["h"])
        if "a" in o and fx.get("as") is None: fx["as"]=int(o["a"])
        if ph is not None and pa is not None:
            fx["penh"]=int(ph); fx["pena"]=int(pa); fx["tab"]=True
            if ph!=pa: fx["winner"]="HOME_TEAM" if ph>pa else "AWAY_TEAM"
        w=o.get("winner")
        if w in ("home","away"):
            fx["winner"]="HOME_TEAM" if w=="home" else "AWAY_TEAM"
    return ko_fixtures

def save_manual(results, datetimes=None, ko_fixtures=None):
    p=os.path.join(ROOT,"data","results_manual.json")
    os.makedirs(os.path.dirname(p),exist_ok=True)
    prev_h={}; prev_k={}; prev_ko_res={}
    if os.path.exists(p):
        with open(p,"r",encoding="utf-8") as f:
            _d=json.load(f); prev_h=_d.get("horaires",{}); prev_k=_d.get("ko_affiches",{})
            prev_ko_res=_d.get("ko_resultats",{})   # overrides manuels t.a.b. : à PRÉSERVER
    horaires=dict(prev_h); horaires.update(datetimes or {})
    ko=dict(prev_k); ko.update(ko_fixtures or {})
    out={"derniere_maj":datetime.date.today().isoformat(),
         "resultats":results,"horaires":horaires,"ko_affiches":ko}
    if prev_ko_res: out["ko_resultats"]=prev_ko_res
    with open(p,"w",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False,indent=2)

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

# ─── MODÈLE DE BUTS DIXON-COLES (Lot 3 — V3) — pronos de PHASE FINALE ─────────
# λ d'attaque/défense initialisés depuis l'Elo (prior fort), avantage hôte limité,
# correction τ de Dixon-Coles sur les faibles scores (0-0,1-0,0-1,1-1). Sortie :
# probabilités V/N/D, distribution de scores, score le plus probable, et la
# probabilité de QUALIFICATION (issue régulière + 50 % des nuls -> tirs au but).
_DC_RHO = -0.13   # corrélation faible-score (Dixon-Coles)

def _ko_lambdas(home, away, tier=0, elite_def=False):
    # Elo live + surcouche MOMENTUM (récence + prestige)
    eh = team_elo(home) + LIVE_MOM.get(home, 0.0)
    ea = team_elo(away) + LIVE_MOM.get(away, 0.0)
    if home in HOST_NATIONS: eh += HOST_ELO_BONUS
    if away in HOST_NATIONS: ea += HOST_ELO_BONUS
    d = eh - ea
    sup = max(-2.0, min(2.0, d / 240.0))
    # EXPÉRIENCE des grands matchs : nudge croissant avec l'enjeu du tour (R32 -> finale)
    sup += (experience(home) - experience(away)) * (CALIB["exp_w0"] + CALIB["exp_w1"] * min(max(tier, 0), 2))          # suprématie bornée (évite les blowouts irréalistes en KO)
    # Total de buts attendu CALIBRÉ sur les CdM récentes (~2.7/match ; phase finale 2018/2022 ~2.8),
    # se resserre par tour. Relevé vs v3.0 pour réduire l'excès de 1-0 (plus de 2-1/2-0/3-1).
    mu = CALIB["ko_mu"][min(max(tier,0),2)]
    # Confrontations directes : nudge LÉGER sur la suprématie (vers le favori du duel) et le total.
    hh = h2h_nudge(home, away)
    if hh:
        e = hh.get("edge", 0.0)
        if hh.get("fav") == home: sup += e
        elif hh.get("fav") == away: sup -= e
        mu += hh.get("goals", 0.0)
    # Style tactique (général) : avantage de confrontation + ouverture du match.
    hs_st = TEAM_DATA.get(home, (0,0,"bloc_moyen"))[2]
    as_st = TEAM_DATA.get(away, (0,0,"bloc_moyen"))[2]
    sbh, sba = style_bonus(hs_st, as_st)
    sup += (sbh - sba) * 0.5                                  # l'edge tactique pèse sur la suprématie
    mu  += STYLE_OPEN.get(hs_st, 0.0) + STYLE_OPEN.get(as_st, 0.0)   # match ouvert/fermé selon les styles
    mu   = max(2.0, mu)
    sup = max(-2.8, min(2.8, sup))
    # Forme récente : module la prolificité de chaque équipe (attaque propre × faille défensive adverse).
    gf_h, ga_h = team_form(home); gf_a, ga_a = team_form(away)
    mult_h = max(0.78, min(1.32, ((gf_h / AVG_FORM) * (ga_a / AVG_FORM)) ** 0.5))
    mult_a = max(0.78, min(1.32, ((gf_a / AVG_FORM) * (ga_h / AVG_FORM)) ** 0.5))
    # Surcouche « défense d'élite » (matchs À VENIR uniquement) : au-delà du plancher de forme
    # à 0,78, on réduit LÉGÈREMENT le lambda offensif de chaque équipe face à un bloc d'élite
    # (buts encaissés/match très bas sur les 10 derniers résultats de l'adversaire). Inerte tant
    # que la donnée ga10 n'est pas committée. Réservé aux pronos futurs (le passé n'est pas réécrit).
    if elite_def:
        mult_h *= elite_def_factor(away)   # ce que HOME peut marquer dépend du bloc de AWAY
        mult_a *= elite_def_factor(home)   # et réciproquement
    lam_h = min(2.85, max(0.30, (mu + sup) / 2.0 * mult_h))   # plafond : pas de 4-0/5-0 systématiques en KO
    lam_a = min(2.85, max(0.30, (mu - sup) / 2.0 * mult_a))
    return lam_h, lam_a

def _pois(k, lam):
    return math.exp(-lam) * (lam ** k) / math.factorial(k)

def _dc_tau(x, y, lh, la, rho=_DC_RHO):
    if x == 0 and y == 0: return 1.0 - lh * la * rho
    if x == 0 and y == 1: return 1.0 + lh * rho
    if x == 1 and y == 0: return 1.0 + la * rho
    if x == 1 and y == 1: return 1.0 - rho
    return 1.0

def _dc_grid(lh, la, maxg=8):
    g = {}
    for x in range(maxg + 1):
        for y in range(maxg + 1):
            g[(x, y)] = _pois(x, lh) * _pois(y, la) * _dc_tau(x, y, lh, la)
    tot = sum(g.values()) or 1.0
    for k in g: g[k] /= tot
    return g

def _unit(key):
    """Tirage déterministe uniforme dans [0,1) à partir d'une chaîne (hash stable)."""
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF

def _pick_score(cands, seed):
    """Tirage DÉTERMINISTE pondéré par la probabilité Dixon-Coles parmi les scores
    plausibles (top 5). Reproduit la VARIÉTÉ réelle des scores (2-1, 3-1, 2-0, 1-0…)
    au lieu de toujours renvoyer le score modal -> évite la monotonie des 2-0/1-0."""
    items = sorted(cands.items(), key=lambda kv: kv[1], reverse=True)[:5]
    total = sum(v for _, v in items) or 1.0
    r = (seed % 100000) / 100000.0 * total
    acc = 0.0
    for sc, v in items:
        acc += v
        if r <= acc:
            return sc
    return items[0][0]

def _ko_predict(home, away, tier=0, elite_def=False):
    """Renvoie un dict complet de prédiction KO Elo+Dixon-Coles."""
    lh, la = _ko_lambdas(home, away, tier, elite_def)
    g = _dc_grid(lh, la)
    pV = sum(p for (x, y), p in g.items() if x > y)
    pN = sum(p for (x, y), p in g.items() if x == y)
    pD = sum(p for (x, y), p in g.items() if x < y)
    # Probabilité de QUALIFICATION (les nuls se décident aux t.a.b. ~50/50)
    advH = pV + 0.5 * pN
    advA = pD + 0.5 * pN
    # Le qualifié PRINCIPAL est TOUJOURS le plus probable (plus haute confiance) : pas de
    # paradoxe "2e scénario meilleur que le 1er". La surprise est portée par le 2e scénario
    # et un indice de confiance bas (la dynamique du sport reste lisible sans tromper).
    fav = home if advH >= advA else away
    winner = fav
    conf = int(round(100 * max(advH, advA)))      # >= 50 % par construction
    upset = False
    seed = int(_unit(away + "#" + home) * 100000)                 # graine (découplée) pour le score
    # Score : le qualifié tiré l'emporte de façon DÉCISIVE ; le nul + t.a.b. n'est montré
    # que pour un vrai 50/50 (match couperet), indépendamment de QUI est tiré.
    coinflip = abs(advH - 0.5) < CALIB["ko_coinflip"]   # KO : t.a.b. réservé aux vrais 50/50 (calibré)
    draws = {k: v for k, v in g.items() if k[0] == k[1]}
    if coinflip and draws:
        (sx, sy) = _pick_score(draws, seed); tab = True
    else:
        if winner == home:
            decisive = {k: v for k, v in g.items() if k[0] > k[1]}
        else:
            decisive = {k: v for k, v in g.items() if k[0] < k[1]}
        (sx, sy) = _pick_score(decisive, seed); tab = False
    # 2e SCÉNARIO (mécanique "second choix") quand la confiance < 65 % : on présente le
    # qualifié ALTERNATIF (l'autre équipe) avec un score décisif plausible et sa proba.
    second = None
    if conf < 65:
        other = away if winner == home else home
        if other == home:
            oc = {k: v for k, v in g.items() if k[0] > k[1]}
        else:
            oc = {k: v for k, v in g.items() if k[0] < k[1]}
        if oc:
            ox, oy = _pick_score(oc, int(_unit(home + "@" + away) * 100000))
            second = {"team": other, "sh": ox, "sa": oy, "p": 100 - conf,
                      "code": FLAG_CODES.get(other, "")}
    # Distribution : top 4 scores (orientés home-away) pour l'affichage
    dist = [{"s": [x, y], "p": int(round(p * 100))}
            for (x, y), p in sorted(g.items(), key=lambda kv: kv[1], reverse=True)[:4]]
    return {"home": home, "away": away, "sh": sx, "sa": sy, "winner": winner, "tab": tab,
            "conf": conf, "fav": fav, "upset": upset, "second": second,
            "proba": {"v": int(round(pV*100)), "n": int(round(pN*100)), "d": int(round(pD*100))},
            "dist": dist, "lh": round(lh, 2), "la": round(la, 2),
            "eh": int(round(team_elo(home))), "ea": int(round(team_elo(away)))}

def _ko_match(home, away, momentum, form=None, tier=0, elite_def=False):
    # V3 : pronostic de phase finale piloté par l'Elo réel + Dixon-Coles
    # (remplace l'ancien chemin compute()/paniers ; la phase de groupes n'est pas touchée).
    # elite_def=True n'est passé que pour les matchs À VENIR (surcouche défense d'élite).
    if not home or not away: return {"home":home,"away":away,"sh":None,"sa":None,"winner":None,"tab":False}
    return _ko_predict(home, away, tier, elite_def)

def _ko_kickoff_dt(mid, datetimes):
    """Coup d'envoi (datetime UTC aware) d'un match KO : horaire réel de l'API si dispo,
    sinon calendrier officiel KO_KICKOFF_UTC. None si inconnu."""
    iso=(datetimes or {}).get(str(mid))
    if not iso:
        try: iso=KO_KICKOFF_UTC.get(int(mid))
        except Exception: iso=None
    if not iso: return None
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z","+00:00"))
    except Exception:
        return None

def _freeze_or_get(mid, home, away, momentum, form, tier, datetimes, played):
    """Prono KO STABLE. Règle : on fige le prono 24 h avant le coup d'envoi, puis on le
    réutilise tel quel pour l'AFFICHAGE **et** la NOTATION -> le prono montré la veille est
    exactement celui qui sera noté (plus de score qui change à l'actualisation).
      • déjà figé pour cette affiche -> on renvoie le prono figé (jamais recalculé) ;
      • pas encore figé + match à venir dans la fenêtre de 24 h -> on le fige maintenant ;
      • sinon (match lointain, ou match joué sans gel antérieur) -> calcul à la volée (repli
        = comportement historique). La surcouche défense d'élite est incluse dans le gel."""
    key=str(mid)
    fr=KO_FROZEN.get(key)
    if fr and fr.get("home")==home and fr.get("away")==away and fr.get("sh") is not None:
        return dict(fr)                      # prono figé pour CETTE affiche -> stable, aucun recalcul
    if (not played) and home and away:
        ko=_ko_kickoff_dt(mid, datetimes)
        now=datetime.datetime.now(datetime.timezone.utc)
        # Fenêtre de gel = STRICTEMENT avant le coup d'envoi, [coup d'envoi − 24 h ; coup d'envoi[.
        # L'app tourne toutes les ~25 min : tout match a de nombreuses occasions d'être figé dans
        # ses 24 h. Ne jamais figer APRÈS le coup d'envoi évite qu'une panne API (matchs passés vus
        # « non joués ») ne gèle en masse des matchs déjà terminés.
        if ko and (ko - datetime.timedelta(hours=FREEZE_LEAD_H)) <= now < ko:
            pred=_ko_match(home, away, momentum, form, tier, elite_def=True)
            if pred.get("sh") is not None:
                rec=dict(pred); rec["home"]=home; rec["away"]=away
                rec["frozen_at"]=now.strftime("%Y-%m-%dT%H:%M:%SZ")
                _KO_FROZEN_OUT[key]=rec; _KO_FROZEN_DIRTY[0]=True
            return dict(pred)
    # Repli : hors fenêtre de gel, ou match déjà joué sans prono figé (héritage) -> pas de
    # surcouche défense sur un match joué (le passé n'est pas réécrit).
    return _ko_match(home, away, momentum, form, tier, elite_def=(not played))

KO_NAMES={"r32":"16es de finale","r16":"8es de finale","qf":"Quarts de finale","sf":"Demi-finales","third":"Match pour la 3e place","final":"Finale"}

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
    """(date_fr_courte, heure_paris) pour un match KO depuis son utcDate, sinon repli
    sur le calendrier officiel KO_KICKOFF_UTC, sinon ('','')."""
    iso=(datetimes or {}).get(str(mid))
    if not iso:
        try: iso=KO_KICKOFF_UTC.get(int(mid))
        except Exception: iso=None
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

def _ko_real(mid, ko_fixtures, datetimes, fb_home=None, fb_away=None):
    """Construit un match KO en privilegiant l'AFFICHE REELLE de l'API (ko_fixtures) ;
    repli sur fb_home/fb_away (reconstruction) si l'equipe n'est pas encore connue.
    Renvoie aussi (sh,sa,winner_side,tab) si le match est reellement termine."""
    fx=(ko_fixtures or {}).get(str(mid)) or {}
    home=fx.get("home") or fb_home
    away=fx.get("away") or fb_away
    played=fx.get("status") in ("FINISHED","AWARDED") and fx.get("hs") is not None and fx.get("as") is not None
    sh=sa=None; rwin=None; tab=False; penh=pena=None
    if home and away and played:
        sh,sa=fx["hs"],fx["as"]
        w=fx.get("winner")
        rwin = home if w=="HOME_TEAM" else (away if w=="AWAY_TEAM" else None)
        # t.a.b. : drapeau fourni par l'ingestion (ou repli sur l'égalité au score affiché)
        tab = bool(fx.get("tab")) or (sh is not None and sh==sa)
        penh, pena = fx.get("penh"), fx.get("pena")
    d,h=_ko_date_fr(datetimes,mid)
    return home,away,sh,sa,rwin,tab,played,d,h,penh,pena

def build_knockout_real(real_standings, datetimes=None, ko_fixtures=None):
    """Bracket 'Reel' : affiches et scores REELS de l'API quand disponibles ; sinon 16es
    provisoires d'apres le classement reel, tours suivants a definir."""
    thirds_sorted, qual_groups, slot_team = _assign_thirds(real_standings)
    feeders={mid:(a,b) for mid,a,b in KO_NEXT}
    real_winners={}   # PROPAGATION : dès qu'une équipe gagne réellement, elle alimente le tour suivant
    real_losers={}    # perdants réels (pour la petite finale : perdants des deux demi-finales)
    def mk(mid, fb_home=None, fb_away=None):
        home,away,sh,sa,rwin,tab,played,d,h,penh,pena=_ko_real(mid,ko_fixtures,datetimes,fb_home,fb_away)
        if rwin: real_winners[mid]=rwin
        if rwin and home and away:
            real_losers[mid]=(away if rwin==home else (home if rwin==away else None))
        return {"id":mid,"home":home,"away":away,"sh":sh,"sa":sa,"winner":rwin,"tab":tab,
                "penh":penh,"pena":pena,
                "ch":FLAG_CODES.get(home,""),"ca":FLAG_CODES.get(away,""),"date":d,"heure":h}
    r32=[]
    for mid,ra,rb in KO_R32:
        fbh=_resolve_ref(ra,real_standings,slot_team); fba=_resolve_ref(rb,real_standings,slot_team)
        r32.append(mk(mid,fbh,fba))
    # Tours suivants : on remplit chaque slot avec le VAINQUEUR RÉEL du match précédent
    # (si déjà joué) -> ex. Canada bat son 16e -> apparaît immédiatement en 8e.
    def later(ids,key):
        arr=[]
        for i in ids:
            a,b=feeders.get(i,(None,None))
            arr.append(mk(i, real_winners.get(a), real_winners.get(b)))
        return {"key":key,"name":KO_NAMES[key],"matches":arr}
    # On construit dans l'ordre pour que les perdants des demies soient connus avant la petite finale.
    r16r=later([89,90,91,92,93,94,95,96],"r16")
    qfr=later([97,98,99,100],"qf")
    sfr=later([101,102],"sf")   # peuple real_losers[101], real_losers[102]
    thirdr={"key":"third","name":KO_NAMES["third"],
            "matches":[mk(103, real_losers.get(101), real_losers.get(102))]}
    finalr=later([104],"final")
    rounds=[{"key":"r32","name":KO_NAMES["r32"],"matches":r32}, r16r, qfr, sfr, thirdr, finalr]
    order_map=_bracket_orders()
    for rd in rounds:
        om=order_map.get(rd["key"])
        if om:
            pos={m:i for i,m in enumerate(om)}
            rd["matches"].sort(key=lambda x:pos.get(x["id"],999))
    thirds_rank=[{"team":t[4],"code":FLAG_CODES.get(t[4],""),"grp":t[0],"Pts":t[1],"GD":t[2],"GF":t[3],
                  "qualified":t[0] in qual_groups} for t in thirds_sorted]
    return {"rounds":rounds,"thirds":thirds_rank}

# ── Override MANUEL de pronostic KO (choix perso de Nono pour un match précis) ──
# Prime sur le modèle : force le prono AFFICHÉ, la NOTATION une fois le match joué, ET la
# PROPAGATION du bracket (vainqueur → tour suivant, perdant → petite finale). Ne s'applique
# qu'au mode Prono (le mode Réel reste 100 % officiel). Clé = numéro FIFA ; sh/sa = score
# home-away ; winner = équipe qualifiée (doit correspondre à home ou away du match).
# Cas rare et assumé (choix humain > modèle). Justification 101 (Nono) : le bloc bas espagnol
# neutralise les individualités françaises → Espagne 0-2, confiance mesurée à 55 %.
KO_PRONO_OVERRIDE = {
    101: {"sh": 0, "sa": 2, "winner": "Espagne", "conf": 55},  # Demi 14/07 : France 0 - 2 Espagne
}
def _prono_override(mid, p):
    ov = KO_PRONO_OVERRIDE.get(mid)
    if not ov:
        return
    p["sh"], p["sa"] = ov["sh"], ov["sa"]
    p["winner"] = p["fav"] = ov["winner"]
    if "conf" in ov:
        p["conf"] = ov["conf"]
    p["second"] = None    # choix net : pas de 2e scénario
    p["serre_off"] = True # score décisif imposé : on masque le badge « match serré · t.a.b. probable »

def build_knockout(standings, momentum, datetimes=None, form=None, ko_fixtures=None):
    thirds_sorted, qual_groups, slot_team = _assign_thirds(standings)
    winners={}; losers={}; rounds=[]
    def make(mid, fb_home, fb_away, tier=0):
        home,away,sh,sa,rwin,tab,played,d,h,penh,pena=_ko_real(mid,ko_fixtures,datetimes,fb_home,fb_away)
        if not home or not away:
            res={"home":home,"away":away,"sh":None,"sa":None,"winner":None,"tab":False}
        elif played:
            # match reellement joue : on affiche le vrai resultat.
            # IMPORTANT : on NE fabrique JAMAIS un vainqueur via l'Elo si le résultat
            # réel ne le donne pas encore (ex. t.a.b. non finalisés dans le flux API).
            # Sinon une équipe réellement éliminée pourrait « avancer » dans l'arbre.
            winner=rwin   # peut être None tant que le qualifié réel n'est pas connu
            # justesse du prono KO (cote Prono uniquement) : vainqueur predit vs vainqueur reel.
            # On note sur le prono FIGÉ (celui affiché avant le match), pas sur un recalcul.
            pred=_freeze_or_get(mid,home,away,momentum,form,tier,datetimes,played=True)
            _prono_override(mid, pred)   # choix perso éventuel → notation sur CE prono
            pred_fav=pred.get("fav") or pred.get("winner")
            res={"home":home,"away":away,"sh":sh,"sa":sa,"winner":winner,"tab":tab,
                 "penh":penh,"pena":pena,
                 # « au moins bon » = BON QUALIFIÉ désigné ET, si le match est allé aux t.a.b.
                 # (nul en 90/120 min), le NUL devait AUSSI avoir été prédit. Autrement dit, pour
                 # un match à t.a.b. le pronostic doit avoir vu le nul ET le bon qualifié : un nul
                 # bien anticipé mais avec le mauvais qualifié = raté (les t.a.b. ont désigné
                 # l'autre équipe). Le t.a.b. tranche le qualifié → propagation du bracket.
                 # Cohérent avec le feed et le compteur.
                 "hit":(None if not winner else
                        ((pred_fav==winner) and (not (tab or sh==sa) or pred.get("sh")==pred.get("sa")))),
                 "conf":pred.get("conf"),"proba":pred.get("proba"),"pred_winner":pred_fav,
                 "pred_score":[pred.get("sh"),pred.get("sa")]}
        else:
            # affiche reelle (ou reconstruite) mais match a venir : on PREDIT le score.
            # Prono figé 24 h avant le coup d'envoi (stable ensuite) ; la surcouche défense
            # d'élite (elite_def=True) est incluse dans le calcul au moment du gel.
            res=_freeze_or_get(mid,home,away,momentum,form,tier,datetimes,played=False)
            _prono_override(mid, res)   # choix perso éventuel (prime sur le modèle)
        res["id"]=mid; res["ch"]=FLAG_CODES.get(res["home"],""); res["ca"]=FLAG_CODES.get(res["away"],"")
        winners[mid]=res["winner"]
        _w=res.get("winner"); _h=res.get("home"); _a=res.get("away")
        losers[mid]=(_a if _w==_h else (_h if _w==_a else None)) if (_w and _h and _a) else None
        return res
    r32=[]
    for mid,ra,rb in KO_R32:
        r32.append(make(mid,_resolve_ref(ra,standings,slot_team),_resolve_ref(rb,standings,slot_team),0))
    rounds.append({"key":"r32","name":KO_NAMES["r32"],"matches":r32})
    def play(idset,key,tier=0):
        arr=[]
        for mid,a,b in KO_NEXT:
            if mid not in idset: continue
            arr.append(make(mid, winners.get(a), winners.get(b), tier))
        rounds.append({"key":key,"name":KO_NAMES[key],"matches":arr})
    play({89,90,91,92,93,94,95,96},"r16",0)
    play({97,98,99,100},"qf",1)
    play({101,102},"sf",1)
    # Match pour la 3e place (M°103) : oppose les PERDANTS des deux demi-finales (petite finale).
    third=make(103, losers.get(101), losers.get(102), 2)
    rounds.append({"key":"third","name":KO_NAMES["third"],"matches":[third]})
    play({104},"final",2)
    order_map=_bracket_orders()
    for rd in rounds:
        om=order_map.get(rd["key"])
        if om:
            pos={mid:i for i,mid in enumerate(om)}
            rd["matches"].sort(key=lambda m: pos.get(m["id"], 999))
        for m in rd["matches"]:
            if not m.get("date"): m["date"],m["heure"]=_ko_date_fr(datetimes, m["id"])
    champion = winners.get(104)
    thirds_rank=[{"team":t[4],"code":FLAG_CODES.get(t[4],""),"grp":t[0],"Pts":t[1],"GD":t[2],"GF":t[3],
                  "qualified":t[0] in qual_groups} for t in thirds_sorted]
    return {"rounds":rounds,"thirds":thirds_rank,"champion":champion,
            "champion_code":FLAG_CODES.get(champion,"")}

# ─── CONSTRUCTION DES DONNÉES DE LA PAGE ─────────────────────────────────────
def compute_momentum_overlay(results, ko_fixtures, datetimes=None):
    """Surcouche MOMENTUM (en points Elo, bornée) ajoutée à l'Elo live pour les
    projections KO. Capte ce que l'Elo « plat » lisse mal :
      • RÉCENCE : le dernier match pèse plus (le début de compétition est du rodage) ;
      • VICTOIRE DE PRESTIGE : battre un adversaire nettement mieux classé est amplifié
        (un exploit en J3 lance une vraie dynamique) ; mal finir pénalise.
    Bornée (-32..+42) pour rester une nuance, pas un bouleversement du niveau réel."""
    ev = _tournament_events(results, ko_fixtures, datetimes)
    per = {}
    for iso, h, a, hs, as_ in ev:
        per.setdefault(h, []).append((iso, _base_elo(h), _base_elo(a), hs, as_))
        per.setdefault(a, []).append((iso, _base_elo(a), _base_elo(h), as_, hs))
    out = {}
    for team, lst in per.items():
        lst.sort(key=lambda x: x[0])
        n = len(lst)
        if n == 0: continue
        num = den = 0.0
        for i, (iso, own, opp, gf, ga) in enumerate(lst):
            recency = 0.5 + 0.5 * (i / (n - 1) if n > 1 else 1)   # 0.5 (J1) -> 1.0 (dernier)
            we = 1.0 / (1.0 + 10 ** (-(own - opp) / 400.0))
            res = 1.0 if gf > ga else (0.5 if gf == ga else 0.0)
            perf = res - we
            amp = 1.0
            if res == 1.0 and opp > own:                          # victoire de prestige (upset)
                amp = 1.0 + min(0.9, (opp - own) / 250.0)
            num += recency * perf * amp; den += recency
        avg = num / den if den else 0.0
        out[team] = max(-32.0, min(42.0, avg * 135.0))
    return out

def _base_elo(team):
    if team in ELO: return ELO[team]
    base = TEAM_DATA.get(team, (6.0,))[0]
    return 1300.0 + base * 90.0

def _elo_mov(gd):
    gd = abs(gd)
    if gd <= 1: return 1.0
    if gd == 2: return 1.5
    return (11.0 + gd) / 8.0

def _tournament_events(results, ko_fixtures, datetimes=None):
    """Liste chronologique (iso, home, away, hs, as) de TOUS les vrais résultats du
    tournoi : phase de groupes + phases finales jouées."""
    ev = []
    for mid, grp, date, h, a in GROUP_MATCHES:
        r = results.get(str(mid))
        if r is not None:
            iso = (datetimes or {}).get(str(mid)) or (date + "T00:00:00Z")
            ev.append((iso, h, a, int(r["h"]), int(r["a"])))
    for mid, fx in (ko_fixtures or {}).items():
        if (fx.get("home") and fx.get("away") and fx.get("hs") is not None
                and fx.get("as") is not None and fx.get("status") in ("FINISHED", "AWARDED")):
            try: iso = (datetimes or {}).get(str(mid)) or KO_KICKOFF_UTC.get(int(mid), "2026-07-01T00:00:00Z")
            except Exception: iso = "2026-07-01T00:00:00Z"
            ev.append((iso, fx["home"], fx["away"], int(fx["hs"]), int(fx["as"])))
    ev.sort(key=lambda e: e[0])
    return ev

def compute_live_elo(results, ko_fixtures, datetimes=None):
    """Elo VIVANT : repart du snapshot Elo figé puis rejoue chronologiquement tous les
    vrais résultats du tournoi (mise à jour Elo standard : poids tournoi + marge de
    victoire). DÉTERMINISTE (reproductible) et AUTO-ENTRETENU : chaque nouveau résultat
    fait évoluer les ratings utilisés pour les projections des tours suivants.
    N'affecte pas la phase de groupes notée (qui reste figée sur TEAM_DATA)."""
    elo = {}
    def E(t):
        if t not in elo: elo[t] = _base_elo(t)
        return elo[t]
    K = 50.0
    for iso, h, a, hs, as_ in _tournament_events(results, ko_fixtures, datetimes):
        if h not in TEAM_DATA or a not in TEAM_DATA: continue
        eh, ea = E(h), E(a)
        we = 1.0 / (1.0 + 10 ** (-(eh - ea) / 400.0))
        res = 1.0 if hs > as_ else (0.5 if hs == as_ else 0.0)
        delta = K * _elo_mov(hs - as_) * (res - we)
        elo[h] = eh + delta; elo[a] = ea - delta
    return elo

def compute_live_form(results, ko_fixtures, datetimes=None):
    """Forme VIVANTE : blende la forme figée (≈50 derniers matchs) avec les buts
    RÉELS marqués/encaissés dans le tournoi (poids croissant avec le nb de matchs joués)."""
    agg = {}
    for iso, h, a, hs, as_ in _tournament_events(results, ko_fixtures, datetimes):
        for t, gf, ga in ((h, hs, as_), (a, as_, hs)):
            d = agg.setdefault(t, {"gf": 0, "ga": 0, "n": 0})
            d["gf"] += gf; d["ga"] += ga; d["n"] += 1
    live = {}
    for t, d in agg.items():
        n = d["n"]
        if n == 0: continue
        base = FORM.get(t, {"gf": AVG_FORM, "ga": AVG_FORM})
        w = n / (n + 4.0)   # 3 matchs -> 0.43 ; 6 -> 0.60 (le tournoi prend le dessus progressivement)
        gf = (1 - w) * base.get("gf", AVG_FORM) + w * (d["gf"] / n)
        ga = (1 - w) * base.get("ga", AVG_FORM) + w * (d["ga"] / n)
        live[t] = {"gf": round(gf, 2), "ga": round(ga, 2)}
    return live

# Résultat RÉEL saisi à la main quand football-data ne l'a JAMAIS remonté (ex. petite finale
# non couverte par le flux gratuit). Score en temps réglementaire+prolongation ; winner "home"/"away" ;
# pen_h/pen_a si t.a.b. Le match est alors marqué TERMINÉ et noté normalement (comme un vrai résultat).
KO_REAL_OVERRIDE = {
    103: {"h": 4, "a": 6, "winner": "away"},   # France 4-6 Angleterre (match pour la 3e place) — source FIFA
}
def apply_ko_real_override(ko_fixtures):
    for mid, o in KO_REAL_OVERRIDE.items():
        fx = ko_fixtures.get(str(mid)) or {}
        if o.get("h") is not None: fx["hs"] = int(o["h"])
        if o.get("a") is not None: fx["as"] = int(o["a"])
        ph, pa = o.get("pen_h"), o.get("pen_a")
        if ph is not None and pa is not None:
            fx["penh"] = int(ph); fx["pena"] = int(pa); fx["tab"] = True
        w = o.get("winner")
        if w in ("home", "away"):
            fx["winner"] = "HOME_TEAM" if w == "home" else "AWAY_TEAM"
        fx["status"] = "FINISHED"            # force la prise en compte comme match JOUÉ + noté
        ko_fixtures[str(mid)] = fx
    return ko_fixtures

def build_payload(results, scorers_by_team=None, datetimes=None, scorers_top=None, assists_top=None, ko_fixtures=None):
    from collections import defaultdict
    scorers_by_team = scorers_by_team or {}
    scorers_top = scorers_top or []
    assists_top = assists_top or []
    ko_fixtures = apply_ko_overrides(ko_fixtures or {})
    ko_fixtures = apply_af_enrichment(ko_fixtures)   # Lot 1 : lieu + t.a.b. fiables (API-Football)
    ko_fixtures = apply_ko_real_override(ko_fixtures)   # résultat réel manuel (petite finale) → TERMINÉ
    datetimes = datetimes or {}
    results={str(k):v for k,v in results.items()}
    momentum,detail=compute_momentum(results, ko_fixtures, datetimes)
    form=compute_form(results)   # v2.3 : forme observée (off/déf, niveau réel, tendance de buts)
    # V3.2 — MODÈLE DYNAMIQUE : Elo + forme RECALCULÉS depuis les vrais résultats du
    # tournoi (auto-entretenu à chaque run). Pilote les projections de phase finale.
    LIVE_ELO.clear();  LIVE_ELO.update(compute_live_elo(results, ko_fixtures, datetimes))
    LIVE_FORM.clear(); LIVE_FORM.update(compute_live_form(results, ko_fixtures, datetimes))
    LIVE_MOM.clear();  LIVE_MOM.update(compute_momentum_overlay(results, ko_fixtures, datetimes))
    qualif_states=compute_qualif_states(results)
    rint={int(k):v for k,v in results.items()}
    # "Aujourd'hui" dans le fuseau du LIEU de la compétition (Amériques). Tous les
    # stades CdM 2026 sont en UTC-4..-7 et les coups d'envoi sont l'après-midi/le soir
    # local : (UTC - 7h) donne donc le bon jour calendaire local pour chaque match.
    today_iso = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(hours=7)).date().isoformat()

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
        pah,paa,diffaj=compute(home,away,momentum,qz,form)
        joue=mid in rint
        # Bande de nul calibrée (apprise) : sur un match de groupe À VENIR très serré,
        # on penche pour le nul (issue la plus probable). N'affecte PAS le prono noté figé
        # ni les matchs déjà joués -> les grades passés restent intacts.
        if (not joue) and CALIB["group_draw_band"]>0 and abs(diffaj)<CALIB["group_draw_band"] and pah!=paa:
            nn=[1,0,2][(sum(ord(c) for c in home+away))%3]; pah=paa=nn
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
        # Surprise : favori net (>85 %) donné vainqueur mais qui NE GAGNE PAS
        # (battu OU accroché sur un nul) — ex. un nul d'une grosse équipe face à un outsider
        surprise = bool(joue and conf > 85 and po in (0, 1) and ro != po)
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
            "venue":VENUES.get(str(mid)),
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

    knockout=build_knockout(standings, momentum, datetimes, form, ko_fixtures)
    real_standings=build_real_standings(rint)
    knockout_real=build_knockout_real(real_standings, datetimes, ko_fixtures)

    # ── Compteur : INCLURE les phases finales jouées (pas seulement les poules) ──
    # Pour chaque match KO réellement joué, on confronte le prono du modèle au réel
    # (même logique exact / bon / raté que les poules), à partir du bracket Prono.
    ko_joue=0
    for rd in knockout["rounds"]:
        for m in rd["matches"]:
            if m.get("hit") is None: continue          # uniquement les matchs KO joués
            ko_joue+=1
            ps=m.get("pred_score") or [None,None]
            if ps[0] is not None and ps[0]==m.get("sh") and ps[1]==m.get("sa"):
                n_exact+=1
            elif m.get("hit"):
                n_bon+=1
            else:
                n_rate+=1
    n_joue_total=len(rint)+ko_joue

    # ── Matchs de phase finale pour le LIVE FEED (affiches réelles : du jour + à venir + joués)
    def _iso_paris(utc):
        # Renvoie (jour officiel "local Amériques" pour le regroupement/"match du jour",
        #          clé de tri chronologique UTC). L'affichage date/heure reste en heure de Paris.
        try:
            dt_utc=datetime.datetime.fromisoformat(utc.replace("Z","+00:00"))
            matchday=(dt_utc - datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
            return matchday, dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None,None
    ko_feed=[]
    PREV_ROUND={"r16":"16es de finale","qf":"8es de finale","sf":"quarts de finale","final":"demi-finales"}
    KO_FEEDERS={mid:(a,b) for mid,a,b in KO_NEXT}   # match -> (match nourricier dom, ext)
    realmap={m["id"]:m for rd in knockout_real["rounds"] for m in rd["matches"]}
    for rd in knockout["rounds"]:
        prevlbl=PREV_ROUND.get(rd.get("key"),"")
        for m in rd["matches"]:
            if not m.get("home") or not m.get("away"): continue
            # Fallback sur l'horaire officiel figé (KO_KICKOFF_UTC) si l'API n'a pas encore
            # la date du match (ex. M°103, 3e place) : sinon la clé de tri retombe sur la
            # date FR ("18 juil.~") qui se classe avant les dates ISO → match mal ordonné.
            mid=m["id"]; utc=datetimes.get(str(mid)) or KO_KICKOFF_UTC.get(mid); iso,sort_key=_iso_paris(utc)
            rm=realmap.get(mid,{}); played=rm.get("sh") is not None
            fx=(ko_fixtures or {}).get(str(mid)) or {}
            is_real=bool(fx.get("home") and fx.get("away"))   # affiche réellement connue (tirage)
            fa,fb=KO_FEEDERS.get(mid,(None,None))
            # ── Enrichissement (mêmes infos que les cartes de groupe) ──
            ko_style_label, ko_style_note = style_analysis(m["home"], m["away"])
            ko_pred = m.get("pred_score") if played else (
                [m["sh"],m["sa"]] if m.get("sh") is not None else None)
            ko_statut = "avenir"
            if played:
                ps = m.get("pred_score") or [None,None]
                # Match décidé aux t.a.b. = nul en temps réglementaire/prolongation. Le prono
                # doit avoir vu le NUL (score prédit nul) ET désigné le BON QUALIFIÉ (m.hit) pour
                # être crédité. Un nul bien anticipé mais avec le mauvais qualifié = raté (les
                # t.a.b. ont fait passer l'autre équipe) ; une victoire nette annoncée = raté
                # aussi (match serré non vu). Le t.a.b. ne sert qu'à trancher le qualifié/bracket.
                is_tab = bool(rm.get("tab")) or (rm.get("sh") is not None and rm.get("sh")==rm.get("sa"))
                pred_draw   = (ps[0] is not None and ps[0]==ps[1])
                score_exact = (ps[0] is not None and ps[0]==rm.get("sh") and ps[1]==rm.get("sa"))
                if is_tab:
                    if pred_draw and m.get("hit") and score_exact:
                        ko_statut = "exact"
                    elif pred_draw and m.get("hit"):
                        ko_statut = "bon"
                    else:
                        ko_statut = "rate"
                elif score_exact:
                    ko_statut = "exact"
                elif m.get("hit"):
                    ko_statut = "bon"
                else:
                    ko_statut = "rate"
            ko_resume = ko_resume_reel = ""
            if played:
                ko_resume, ko_resume_reel = match_summary(
                    rm.get("home") or m["home"], rm.get("away") or m["away"],
                    rm["sh"], rm["sa"], ko_statut, momentum, scorers_by_team or {}, tab=is_tab, pred_draw=pred_draw)
            ko_feed.append({
                "id":mid,"num":mid,"phase":rd["name"],"date":m.get("date",""),"heure":m.get("heure",""),
                "iso":iso or "","sort":sort_key or (m.get("date","")+"~"),
                "today":(iso==today_iso) if iso else False,
                "home":m["home"],"away":m["away"],"ch":m.get("ch",""),"ca":m.get("ca",""),
                "real":is_real,"prev":prevlbl,"prevA":fa,"prevB":fb,
                # affiche RÉELLE propagée (équipe déjà qualifiée pour ce tour), sinon None
                "reel_home":rm.get("home"),"reel_away":rm.get("away"),
                "rch":rm.get("ch",""),"rca":rm.get("ca",""),
                "reel":[rm["sh"],rm["sa"]] if played else None,
                "tab":bool(rm.get("tab")) if played else False,
                "penh":rm.get("penh") if played else None,
                "pena":rm.get("pena") if played else None,
                "prono":[m["sh"],m["sa"]] if (not played and m.get("sh") is not None) else None,
                # — infos enrichies (confiance, prono vs réel, style, 2e choix, résumé) —
                "conf":m.get("conf"),"pred_score":ko_pred,"statut":ko_statut,
                "second":m.get("second"),"serre_off":m.get("serre_off"),
                "style_label":ko_style_label,"style_note":ko_style_note,
                "resume":ko_resume,"resume_reel":ko_resume_reel,
                "mom_h":round(momentum.get(m["home"],0.0),2),
                "mom_a":round(momentum.get(m["away"],0.0),2),
                "winner":rm.get("winner") if played else None,
                "venue":VENUES.get(str(mid)),
                "host_h":m["home"] in HOST_NATIONS,"host_a":m["away"] in HOST_NATIONS})

    # ── "Match du jour" = journée ACTIVE ──────────────────────────────────────
    # Tant que le jour courant (fuseau du lieu) a encore un match non joué, c'est lui.
    # Dès que TOUS les matchs du jour sont passés en "Anciens", le badge bascule
    # automatiquement sur la prochaine journée à jouer (les nouveaux matchs).
    _unplayed_iso=[m["iso"] for m in matches if not m.get("reel") and m.get("iso")]
    _unplayed_iso+=[m["iso"] for m in ko_feed if not m.get("reel") and m.get("iso")]
    if any(i==today_iso for i in _unplayed_iso):
        active_day=today_iso
    elif _unplayed_iso:
        active_day=min(_unplayed_iso)
    else:
        active_day=today_iso
    # La journée active est-elle réellement aujourd'hui ? Si non (aucun match aujourd'hui →
    # bascule sur la prochaine journée), le badge doit dire « Prochaine journée », pas
    # « Match du jour » (sinon on affiche « Match du jour » sur un match de demain).
    active_is_today = (active_day == today_iso)
    n_today=0
    for _m in matches:
        _m["today"]=(_m.get("iso")==active_day); n_today+=1 if _m["today"] else 0
    for _m in ko_feed:
        _m["today"]=(_m.get("iso")==active_day); n_today+=1 if _m["today"] else 0

    return {
        "maj":(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).strftime("%d/%m/%Y à %H:%M")+" (Paris)",
        "today":datetime.date.today().isoformat(),
        "active_is_today":active_is_today,
        "version":MODEL_VERSION,
        "stats":{"joue":n_joue_total,"exact":n_exact,"bon":n_bon,"rate":n_rate,"total":104,"today":n_today},
        "matches":matches,"standings":standings,"momentum":mom_list,"knockout":knockout,
        "knockout_real":knockout_real,
        "ko_feed":ko_feed,
        "scorers":scorers_top,
        "assists":assists_top,
    }

# ─── GÉNÉRATION HTML ─────────────────────────────────────────────────────────
def render_html(payload):
    tpl=open(os.path.join(ROOT,"template.html"),"r",encoding="utf-8").read()
    # Empreinte du CODE = template.html + générateur (update.py). Stable tant que le code ne
    # change pas (indépendante des données : résultats et API n'altèrent pas ces fichiers).
    # Sert à détecter côté client une nouvelle version de l'app et à recharger l'onglet ouvert.
    try:
        _own=open(os.path.abspath(__file__),encoding="utf-8").read()
    except Exception:
        _own=""
    # sw.js fait partie du CODE de l'app : l'inclure dans l'empreinte pour qu'une modif
    # du service worker change app_version → déclenche le déploiement conditionnel (content.sig)
    # ET l'auto-reload client. Sans ça, un sw.js modifié ne serait jamais republié.
    try:
        _sw=open(os.path.join(ROOT,"sw.js"),encoding="utf-8").read()
    except Exception:
        _sw=""
    app_ver=hashlib.md5((tpl+_own+_sw).encode("utf-8")).hexdigest()[:8]
    payload["app_version"]=app_ver   # embarquée dans index.html ET dans data.json (écrit ensuite)
    data_json=json.dumps(payload,ensure_ascii=False)
    html=tpl.replace("/*__DATA__*/null", data_json)
    # Masquer la carte « Meilleurs passeurs » : la source gratuite (football-data /scorers,
    # classée par buts) ne peut pas produire un vrai classement passeurs — un passeur qui n'a
    # pas marqué (ex. Olise, Bruno Guimarães) est invisible. Mieux vaut pas de carte qu'un
    # classement trompeur. Réactivable en v2 avec une source dédiée (API-Football Pro).
    # No-op si le motif change dans template.html (aucun risque de casse).
    html=html.replace(
        "renderScorers())\n       + collapsible('assists','🎯 Meilleurs passeurs (toute la compétition)', renderAssists());",
        "renderScorers());")
    # Badge « Match du jour » : n'afficher ce libellé que si la journée active est réellement
    # AUJOURD'HUI. En cas de bascule sur la prochaine journée (aucun match aujourd'hui), afficher
    # « Prochaine journée » pour ne pas prétendre qu'un match de demain est « du jour ».
    # (Les 3 badges du template ont exactement ces chaînes ; no-op si elles changent.)
    _lbl = "'+(DATA.active_is_today===false?'Prochaine journée':'Match du jour')+'"
    html=html.replace('<span class="b-today">● Match du jour</span>',
                      '<span class="b-today">● %s</span>' % _lbl)
    html=html.replace('<span class="b-today">\\u25CF Match du jour</span>',
                      '<span class="b-today">\\u25CF %s</span>' % _lbl)
    # En-tête de journée du live feed : « · aujourd'hui » seulement si la journée active est
    # réellement aujourd'hui ; sinon « · prochaine journée » (cohérent avec le badge).
    html=html.replace("x.today?' · aujourd\\'hui':''",
                      "x.today?' · '+(DATA.active_is_today===false?'prochaine journée':'aujourd\\'hui'):''")
    # Match pour la 3e place : bracketFifa n'affiche que r32/r16/qf/sf + finale ; le round "third"
    # serait sinon ignoré. On l'injecte explicitement au centre, juste sous la finale (Prono + Réel).
    _third_card=("((byKey['third']&&byKey['third'].matches&&byKey['third'].matches[0])"
                 "?'<div class=\"ko-third\" style=\"margin-top:14px\">"
                 "<div class=\"ko-rname\">\\uD83E\\uDD49 Match pour la 3e place"
                 "<span class=\"per\">18 juil.</span></div>"
                 "<div class=\"ko-matches\"><div class=\"ko-cell\">'"
                 "+koMatch(byKey['third'].matches[0])+'</div></div></div>':'')")
    html=html.replace("(champHtml||'') + '</div>';",
                      "(champHtml||'') + " + _third_card + " + '</div>';")
    # Choix perso « net » (override de prono) : masquer le badge « match serré · t.a.b. probable »
    # même si la confiance < 60 %, car un score décisif est imposé (flag serre_off).
    html=html.replace("!m.reel && m.conf!=null && m.conf<60)",
                      "!m.reel && m.conf!=null && m.conf<60 && !m.serre_off)")
    html=html.replace("m.hit==null && m.conf && m.conf<60)",
                      "m.hit==null && m.conf && m.conf<60 && !m.serre_off)")
    # ── CLÔTURE CdM : bandeau « vainqueur » animé + onglet « Bilan » (récap complet).
    # Injectés 100 % en JS via l'unique ancre fiable </body> (pas de chirurgie HTML fragile) :
    #  • bouton d'onglet ajouté au <nav> (système générique data-v) ;
    #  • render() monkeypatché pour peupler #content quand view==='bilan' ;
    #  • bandeau champion (données RÉELLES : DATA.knockout_real) en tête de .wrap.
    # Tout est encapsulé + try/catch → aucune régression possible sur le reste de l'app.
    bilan_js = """<script>(function(){
try{
if(typeof DATA==='undefined'||!DATA) return;
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function fimg(code){try{if(typeof flagImg==='function')return flagImg(code,'sm');}catch(e){}return '';}
function koReal(){return (DATA.knockout_real&&DATA.knockout_real.rounds)?DATA.knockout_real:(DATA.knockout||{});}
function mOf(ko,key){var r=(ko.rounds||[]).filter(function(x){return x.key===key;})[0];return (r&&r.matches&&r.matches[0])?r.matches[0]:null;}
function codeOf(m,team){return team===m.home?m.ch:m.ca;}
function loserOf(m){if(!m||!m.winner)return null;return m.winner===m.home?m.away:m.home;}
var KO=koReal();
var FIN=mOf(KO,'final'), THIRD=mOf(KO,'third');
var CH = (FIN&&FIN.winner)?FIN.winner:(KO.champion||null);
var CHC= (FIN&&FIN.winner)?codeOf(FIN,FIN.winner):(KO.champion_code||'');

if(!document.getElementById('champ-css')){var st=document.createElement('style');st.id='champ-css';
st.textContent='#champbar{margin:10px 0 2px;border-radius:16px;padding:15px 18px;text-align:center;position:relative;overflow:hidden;background:linear-gradient(135deg,#f6c453,#e8a20c 55%,#f6c453);color:#3a2a00;box-shadow:0 6px 20px rgba(232,162,12,.35)}'
+'#champbar .cl{font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;opacity:.85}'
+'#champbar .cn{font-size:22px;font-weight:900;margin-top:3px;display:flex;align-items:center;justify-content:center;gap:9px;flex-wrap:wrap}'
+'#champbar .tr{display:inline-block;font-size:24px;animation:champpop 1.7s ease-in-out infinite}'
+'#champbar::after{content:"";position:absolute;top:0;left:-60%;width:45%;height:100%;background:linear-gradient(120deg,transparent,rgba(255,255,255,.7),transparent);transform:skewX(-20deg);animation:champshine 3.6s linear infinite;pointer-events:none}'
+'@keyframes champshine{0%{left:-60%}60%{left:130%}100%{left:130%}}'
+'@keyframes champpop{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-3px) scale(1.14)}}';
document.head.appendChild(st);}

function ensureChampBar(){try{
var wrap=document.querySelector('.wrap');if(!wrap)return;
var el=document.getElementById('champbar');
if(!CH){if(el)el.remove();return;}
if(!el){el=document.createElement('div');el.id='champbar';wrap.insertBefore(el,wrap.firstChild);}
el.innerHTML='<div class="cl"><span class="tr">🏆</span> Champion du monde 2026</div><div class="cn">'+fimg(CHC)+' '+esc(CH)+'</div>';
}catch(e){}}

if(!document.getElementById('bilan-css')){var s2=document.createElement('style');s2.id='bilan-css';
s2.textContent='.bilan-hero{margin:2px 0 14px;padding:18px 16px;border-radius:16px;text-align:center;background:linear-gradient(135deg,rgba(246,196,83,.20),rgba(232,162,12,.10));border:1px solid rgba(232,162,12,.35)}'
+'.bilan-hero h2{margin:0;font-size:20px;font-weight:900}.bilan-hero .sub{opacity:.75;font-size:12px;margin-top:4px}'
+'.b-sec{display:flex;align-items:center;gap:9px;margin:0 0 12px}'
+'.b-sec .ic{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px;background:linear-gradient(135deg,#f6c453,#e8a20c);flex:none}'
+'.b-sec h3{margin:0;font-size:15px;font-weight:800}'
+'.bilan-podium{display:flex;gap:10px;justify-content:center;align-items:flex-end;flex-wrap:wrap;margin:4px 0 10px}'
+'.bilan-podium .pod{display:flex;flex-direction:column;align-items:center;gap:3px;padding:12px 16px;border-radius:14px;background:rgba(127,127,127,.10);min-width:104px}'
+'.bilan-podium .pod1{background:linear-gradient(135deg,#f6c453,#e8a20c);color:#3a2a00;order:2;transform:translateY(-10px);box-shadow:0 6px 18px rgba(232,162,12,.35)}'
+'.bilan-podium .pod2{order:1}.bilan-podium .pod3{order:3}'
+'.bilan-podium .medal{font-size:26px;line-height:1}.bilan-podium .pn{font-size:15px;font-weight:800}.bilan-podium .pr{font-size:11px;opacity:.82;text-transform:uppercase;letter-spacing:.04em}'
+'.bilan-final{text-align:center;margin-top:4px;opacity:.85;font-size:13px}'
+'.bstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(86px,1fr));gap:8px}'
+'.bstat{text-align:center;padding:12px 6px;border-radius:14px;background:rgba(127,127,127,.10)}'
+'.bstat .bi{font-size:16px}.bstat .bv{font-size:22px;font-weight:900;line-height:1.15}.bstat .bl{font-size:10.5px;opacity:.72;text-transform:uppercase;letter-spacing:.03em}'
+'.bstat.ok .bv{color:#16a34a}.bstat.ko .bv{color:#dc2626}'
+'.b-row{display:flex;align-items:center;gap:10px;padding:7px 2px}.b-row+.b-row{border-top:1px solid rgba(127,127,127,.14)}'
+'.b-rk{width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;background:rgba(127,127,127,.16);flex:none}'
+'.b-rk.r1{background:linear-gradient(135deg,#f6c453,#e8a20c);color:#3a2a00}.b-rk.r2{background:linear-gradient(135deg,#e5e7eb,#b6bcc6);color:#333}.b-rk.r3{background:linear-gradient(135deg,#e8b483,#cd7f32);color:#3a2100}'
+'.b-fl{flex:none;display:flex}.b-mid{flex:1;min-width:0}.b-top{display:flex;align-items:baseline;gap:6px}'
+'.b-nm{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.b-tm{font-size:11px;opacity:.6;white-space:nowrap}.b-val{margin-left:auto;font-weight:900;font-size:15px;flex:none}'
+'.b-track{height:7px;border-radius:5px;background:rgba(127,127,127,.14);margin-top:4px;overflow:hidden}.b-bar{display:block;height:100%;border-radius:5px;background:linear-gradient(90deg,#f6c453,#e8a20c)}'
+'.b-fiab{text-align:center;margin-bottom:12px}.b-fiab .fv{font-size:30px;font-weight:900;color:#e8a20c;line-height:1}.b-fiab .fl{font-size:12px;opacity:.8;margin-top:2px}'
+'.b-note{text-align:center;margin-top:12px;font-weight:800;color:#16a34a}.bmuted{opacity:.62;font-size:11px}'
+'.bilan .card{margin-bottom:18px;padding:18px 16px}.bilan .card:last-child{margin-bottom:0}'
+'.bilan-hero{margin:2px 0 18px;padding:22px 16px}'
+'.b-sec{margin:0 0 16px}'
+'.bstats{gap:12px}.bstat{padding:16px 8px}'
+'.b-row{padding:12px 2px}.b-row+.b-row{border-top:1px solid rgba(127,127,127,.12)}'
+'.b-track{margin-top:7px}.b-top{gap:8px}'
+'.bilan-podium{gap:16px;margin:8px 0 16px}.bilan-podium .pod{padding:16px 20px;gap:5px}'
+'.b-fiab{margin-bottom:16px}';
document.head.appendChild(s2);}

function podiumHtml(){if(!FIN)return '<div class="bmuted">Tableau final indisponible.</div>';
var fs=loserOf(FIN), tr=(THIRD&&THIRD.winner)?THIRD.winner:null;
var h='<div class="bilan-podium">';
if(fs)h+='<div class="pod pod2"><div class="medal">🥈</div>'+fimg(codeOf(FIN,fs))+'<div class="pn">'+esc(fs)+'</div><div class="pr">Finaliste</div></div>';
h+='<div class="pod pod1"><div class="medal">🥇</div>'+fimg(CHC)+'<div class="pn">'+esc(CH)+'</div><div class="pr">Champion</div></div>';
if(tr)h+='<div class="pod pod3"><div class="medal">🥉</div>'+fimg(codeOf(THIRD,tr))+'<div class="pn">'+esc(tr)+'</div><div class="pr">3e place</div></div>';
h+='</div>';
if(FIN.sh!=null&&FIN.sa!=null){var pen=(FIN.tab&&FIN.penh!=null)?(' ('+FIN.penh+'-'+FIN.pena+' t.a.b.)'):'';
h+='<div class="bilan-final">Finale : '+esc(FIN.home)+' <b>'+FIN.sh+'–'+FIN.sa+'</b> '+esc(FIN.away)+pen+'</div>';}
return h;}

// Classement OFFICIEL FIFA (buts · passes décisives) — source consolidée figée en fin de tournoi.
var FIFA_TOP=[['Kylian Mbappé',10,4],['Lionel Messi',8,4],['Jude Bellingham',7,1],['Erling Haaland',7,0],['Ousmane Dembélé',6,2],['Harry Kane',6,1],['Mikel Oyarzabal',5,1],['Ismaïla Sarr',4,1],['Julián Quiñones',4,1],['Vinicius Junior',4,1]];
var FIFA_TEAM={'Kylian Mbappé':'France','Lionel Messi':'Argentine','Jude Bellingham':'Angleterre','Erling Haaland':'Norvège','Ousmane Dembélé':'France','Harry Kane':'Angleterre','Mikel Oyarzabal':'Espagne','Ismaïla Sarr':'Sénégal','Julián Quiñones':'Mexique','Vinicius Junior':'Brésil'};
function normName(s){try{return String(s||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().trim();}catch(e){return String(s||'').toLowerCase();}}
function fifaMeta(name){var code='',team='';try{var arr=(DATA.scorers||DATA.scorers_top||[]).concat(DATA.assists||DATA.assists_top||[]);var nn=normName(name);for(var i=0;i<arr.length;i++){if(normName(arr[i].player)===nn){if(arr[i].code&&!code)code=arr[i].code;if(arr[i].team&&!team)team=arr[i].team;if(code&&team)break;}}}catch(e){}return {code:code,team:team||FIFA_TEAM[name]||''};}
// Top buteurs (depuis FIFA_TOP, drapeau/équipe résolus via les données de l'app) et
// Top passeurs = classement OFFICIEL des passes décisives FIFA (indépendant des buteurs :
// le leader Michael Olise n'est PAS dans le top buteurs). Codes/équipes en dur pour les passeurs.
var BUT_ROWS=FIFA_TOP.map(function(r){return {n:r[0],v:r[1]};});
var PASS_ROWS=[{n:'Michael Olise',v:7,code:'fr',team:'France'},{n:'Martin Ødegaard',v:4,code:'no',team:'Norvège'},{n:'Kylian Mbappé',v:4,code:'fr',team:'France'},{n:'Brahim Díaz',v:4,code:'ma',team:'Maroc'},{n:'Bruno Guimarães',v:4,code:'br',team:'Brésil'}];
function rankList(rows){var mx=0;rows.forEach(function(r){if(r.v>mx)mx=r.v;});if(!mx)mx=1;
return rows.map(function(r,i){var mt=fifaMeta(r.n),code=r.code||mt.code||'',team=r.team||mt.team||'',rk=(i<3)?(' r'+(i+1)):'';
return '<div class="b-row"><span class="b-rk'+rk+'">'+(i+1)+'</span><span class="b-fl">'+fimg(code)+'</span>'
+'<div class="b-mid"><div class="b-top"><span class="b-nm">'+esc(r.n)+'</span><span class="b-tm">'+esc(team)+'</span><span class="b-val">'+r.v+'</span></div>'
+'<div class="b-track"><span class="b-bar" style="width:'+Math.round(r.v/mx*100)+'%"></span></div></div></div>';}).join('');}

function tournStats(){try{var goals=0,played=0,big=null,tab=0,surp=0;
function acc(sc,isTab,isSurp){if(!sc)return;var a=sc[0],b=sc[1];if(a==null||b==null)return;goals+=a+b;played++;if(big==null||a+b>big)big=a+b;if(isTab)tab++;if(isSurp)surp++;}
(DATA.matches||[]).forEach(function(m){acc(m.reel,false,m.surprise);});
(DATA.ko_feed||[]).forEach(function(m){var sc=m.reel||((m.reel_home!=null)?[m.reel_home,m.reel_away]:null);acc(sc,m.tab,(m.upset||m.surprise));});
function c(ic,v,l){return '<div class="bstat"><div class="bi">'+ic+'</div><div class="bv">'+v+'</div><div class="bl">'+l+'</div></div>';}
var o='';if(played){o+=c('⚽',goals,'buts');o+=c('📊',(goals/played).toFixed(2),'buts / match');}
if(big!=null)o+=c('🔥',big,'+ de buts (1 match)');o+=c('🥅',tab,'séances de t.a.b.');if(surp)o+=c('😮',surp,'surprises');
return '<div class="bstats">'+o+'</div>';}catch(e){return '<div class="bmuted">—</div>';}}

function finaleExacte(){try{var f=(DATA.ko_feed||[]).filter(function(m){return m.num===104;})[0];return !!(f&&f.statut==='exact');}catch(e){return false;}}

function pronoBilan(){var s=DATA.stats||{},j=s.joue||0,ex=s.exact||0,bon=s.bon||0,rt=s.rate||0;
var fiab=j?(((ex+bon)/j)*100).toFixed(1):'0';
var h='<div class="b-fiab"><div class="fv">'+fiab+' %</div><div class="fl">de fiabilité — '+(ex+bon)+' pronos justes sur '+j+'</div></div>';
h+='<div class="bstats"><div class="bstat ok"><div class="bi">🎯</div><div class="bv">'+ex+'</div><div class="bl">scores exacts</div></div>'
+'<div class="bstat ok"><div class="bi">✅</div><div class="bv">'+bon+'</div><div class="bl">bons vainqueurs</div></div>'
+'<div class="bstat ko"><div class="bi">❌</div><div class="bv">'+rt+'</div><div class="bl">ratés</div></div></div>';
if(finaleExacte())h+='<div class="b-note">🎯 Nono avait pronostiqué la finale au score exact !</div>';
return h;}

function sec(ic,t,body){return '<div class="card"><div class="b-sec"><span class="ic">'+ic+'</span><h3>'+t+'</h3></div>'+body+'</div>';}
function bilanHtml(){try{
var h='<div class="bilan"><div class="bilan-hero"><h2>🏆 Bilan de la Coupe du Monde 2026</h2><div class="sub">11 juin – 19 juillet · États-Unis · Canada · Mexique</div></div>';
h+=sec('🏅','Podium',podiumHtml());
h+=sec('📊','Statistiques clés du tournoi',tournStats());
h+=sec('⚽','Top buteurs',rankList(BUT_ROWS)+'<div class="bmuted" style="margin-top:10px">Buts — classement officiel FIFA.</div>');
h+=sec('🎯','Top passeurs',rankList(PASS_ROWS)+'<div class="bmuted" style="margin-top:10px">Passes décisives — classement officiel FIFA.</div>');
h+=sec('🤖','Bilan des pronos de Nono',pronoBilan());
return h+'</div>';}catch(e){return '<div class="card">Bilan momentanément indisponible.</div>';}}

try{var nav=document.getElementById('nav');
if(nav&&!nav.querySelector('[data-v="bilan"]')){var b=document.createElement('button');b.setAttribute('data-v','bilan');b.innerHTML='🏆 Bilan';
b.onclick=function(){try{view='bilan';}catch(e){}try{render();}catch(e){}};nav.appendChild(b);}}catch(e){}

if(typeof render==='function'){var _r=render;render=function(){try{_r();}catch(e){}
try{if(typeof view!=='undefined'&&view==='bilan'){var c=document.getElementById('content');if(c)c.innerHTML=bilanHtml();}}catch(e){}
ensureChampBar();};}
ensureChampBar();
try{if(typeof view!=='undefined'){view='bilan';if(typeof render==='function')render();}}catch(e){}
}catch(e){}
})();</script>"""
    html=html.replace("</body>", bilan_js+"</body>")
    # Rechargement auto SILENCIEUX : si le CODE de l'app change (app_version différent de celui
    # embarqué), l'onglet ouvert se recharge pour récupérer la nouvelle version. Les DONNÉES,
    # elles, sont déjà rafraîchies en direct par le poll existant. Garde anti-boucle 120 s
    # (le temps que le CDN GitHub Pages propage la nouvelle page).
    reload_js=("<script>(function(){var V='%s';function c(){"
               "fetch('./app.version?v='+Date.now(),{cache:'no-store'})"
               ".then(function(r){return r.ok?r.text():null;})"
               ".then(function(t){if(!t)return;t=t.trim();if(!t||t===V)return;"
               "var now=Date.now(),last=0;try{last=+sessionStorage.getItem('pb_reload_at')||0;}catch(e){}"
               "if(now-last<120000)return;try{sessionStorage.setItem('pb_reload_at',String(now));}catch(e){}"
               "location.reload();}).catch(function(){});}"
               "setInterval(c,180000);document.addEventListener('visibilitychange',function(){if(!document.hidden)c();});"
               "})();</script>") % app_ver
    html=html.replace("</body>", reload_js+"</body>")
    return html

def main():
    results, datetimes, ko_fixtures = load_results()
    scorers, scorers_top, assists_top = fetch_scorers()
    if scorers:
        print(f"[OK] Buteurs récupérés pour {len(scorers)} équipe(s) ; {len(scorers_top)} buteur(s) classés ; {len(assists_top)} passeur(s) classés")
    payload=build_payload(results, scorers, datetimes, scorers_top, assists_top, ko_fixtures)
    html=render_html(payload)
    out=os.path.join(ROOT,"index.html")
    with open(out,"w",encoding="utf-8") as f:
        f.write(html)
    # data.json : données structurées réutilisables (service worker pour les notifications, etc.)
    with open(os.path.join(ROOT,"data.json"),"w",encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    # app.version : minuscule fichier sondé par le client pour l'auto-reload (évite de
    # re-télécharger data.json juste pour lire la version).
    with open(os.path.join(ROOT,"app.version"),"w",encoding="utf-8") as f:
        f.write(payload.get("app_version",""))
    # ko_pronos.json : pronos KO FIGÉS (persistés d'un run à l'autre). Écrit systématiquement
    # (idempotent) pour que le fichier committé reste la référence stable des pronos affichés/notés.
    with open(os.path.join(ROOT,"data","ko_pronos.json"),"w",encoding="utf-8") as f:
        json.dump({"_meta":{"role":"Pronos de phase finale FIGÉS 24 h avant le coup d'envoi "
                            "(affichage = notation, aucune dérive). Écrit par update.py.",
                            "author":"Nico-Mtn",
                            "credit":"Auteur : Nico-Mtn (https://github.com/Nico-Mtn). Réutilisation libre, crédit apprécié."},
                   "pronos":_KO_FROZEN_OUT}, f, ensure_ascii=False, indent=2)
    # content.sig : empreinte du CONTENU (hors timestamp "maj", qui change à chaque run).
    # Sert au déploiement conditionnel dans update.yml : on ne republie sur GitHub Pages
    # QUE si cette empreinte a changé (nouveau résultat, buteur, horaire, code…), jamais
    # pour un simple rafraîchissement d'heure. Évite les déploiements Pages « à vide ».
    # On y intègre l'ensemble des pronos figés : un NOUVEAU gel modifie l'empreinte ->
    # déclenche le commit (donc la persistance de ko_pronos.json), sans déploiement « à vide ».
    _sig_payload = {k: v for k, v in payload.items() if k != "maj"}
    _sig_payload["_ko_frozen"] = _KO_FROZEN_OUT
    _sig = hashlib.md5(json.dumps(_sig_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    with open(os.path.join(ROOT,"content.sig"),"w",encoding="utf-8") as f:
        f.write(_sig)
    s=payload["stats"]
    print(f"[OK] index.html généré — {s['joue']} joués | {s['exact']} exacts, {s['bon']} bons, {s['rate']} ratés | {s['today']} match(s) aujourd'hui")

if __name__=="__main__":
    main()
