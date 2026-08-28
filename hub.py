# -*- coding: utf-8 -*-
# ============================================================================
#  Pronostix — Page d'accueil (hub des compétitions)
#  Auteur / Author : Nico-Mtn — https://github.com/Nico-Mtn
#  Projet gratuit, sans publicité, sans paris.
#  Réutilisation libre : un CRÉDIT au créateur (Nico-Mtn) serait grandement
#  apprécié. / If you reuse this model or code, a credit to the creator
#  (Nico-Mtn) would be greatly appreciated.
# ============================================================================
"""
Génère index.html à la RACINE : le sommaire de toutes les compétitions suivies,
rangées en Championnats / Coupes, chacune scindée en « En cours » et « Passées ».

Chaque carte affiche des indicateurs lus dans le data.json de la compétition
(fiabilité du modèle, avancement, champion pour une compétition terminée) :
aucune saisie manuelle, aucun doublon de vérité.

Usage : python3 hub.py   (à lancer APRÈS update.py / l1.py)
"""
import os, re, json, hashlib, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))

# Déclaration des compétitions. Le champ « statut » vaut "en_cours" ou "passee".
# Le champ « flag » est un code pays flagcdn, servi en IMAGE : le drapeau de
# l'Angleterre est une séquence de balises Unicode que la plupart des systèmes
# affichent en drapeau noir générique. Le champ « emoji » sert aux compétitions
# sans pays (Coupe du Monde).
COMPETITIONS = [
    {"slug": "ligue-1-france", "nom": "Ligue 1", "lieu": "France", "flag": "fr",
     "famille": "championnat", "statut": "en_cours", "saison": "2026-2027"},
    {"slug": "premier-league-england", "nom": "Premier League", "lieu": "Angleterre",
     "flag": "gb-eng", "famille": "championnat", "statut": "en_cours", "saison": "2026-2027"},
    {"slug": "pronostics-cdm2026", "nom": "Coupe du Monde 2026",
     "lieu": "États-Unis · Canada · Mexique", "emoji": "🏆",
     "famille": "coupe", "statut": "passee", "saison": "2026"},
]

# Un dossier d'archive s'appelle « <slug du championnat>-<AAAA>-<AAAA> ».
ARCHIVE_RE = re.compile(r"^(?P<base>.+)-(?P<a>\d{4})-(?P<b>\d{4})$")

def archives_par_championnat():
    """Découvre les saisons archivées réellement présentes sur le disque, groupées par
    championnat et triées de la plus récente à la plus ancienne. Rien n'est déclaré à
    la main : une archive générée apparaît, une archive supprimée disparaît."""
    out = {}
    try:
        dossiers = sorted(os.listdir(ROOT))
    except Exception:
        return out
    for nom in dossiers:
        m = ARCHIVE_RE.match(nom)
        if not m or not os.path.exists(os.path.join(ROOT, nom, "data.json")):
            continue
        out.setdefault(m.group("base"), []).append(
            {"slug": nom, "saison": f'{m.group("a")}-{m.group("b")}', "an": int(m.group("a"))})
    for v in out.values():
        v.sort(key=lambda x: -x["an"])
    return out

def lire(slug):
    """Indicateurs d'une compétition depuis son data.json (silencieux si absent)."""
    try:
        with open(os.path.join(ROOT, slug, "data.json"), encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    s = d.get("stats") or {}
    joue, total = s.get("joue") or 0, s.get("total") or 0
    ok = (s.get("exact") or 0) + (s.get("bon") or 0)
    info = {"joue": joue, "total": total,
            "fiab": (round(ok / joue * 100, 1) if joue else None),
            "maj": d.get("maj"), "journee": d.get("journee")}
    # Compétition terminée : on met le vainqueur en avant
    ko = d.get("knockout_real") or d.get("knockout") or {}
    for r in (ko.get("rounds") or []):
        if r.get("key") == "final":
            m = (r.get("matches") or [{}])[0]
            if m.get("winner"):
                info["vainqueur"] = m["winner"]
    if not info.get("vainqueur") and ko.get("champion"):
        info["vainqueur"] = ko["champion"]
    # Championnat : leader du classement réel (champion si la saison est archivée)
    tb = d.get("table") or []
    if tb:
        lead = tb[0].get("team")
        info["leader"] = ((d.get("noms") or {}).get(lead) or {}).get("n") or lead
    # Saison archivée : note éditoriale sur 10 attribuée à la saison
    nt = d.get("note") or {}
    if nt.get("note") is not None:
        info["note"] = nt["note"]
    return info

def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

def blason(c):
    """Drapeau du pays en image (rendu fiable partout), ou emoji pour une coupe."""
    if c.get("flag"):
        return (f'<img class="flg" src="https://flagcdn.com/w80/{c["flag"]}.png" '
                f'width="34" height="26" alt="" loading="lazy">')
    return f'<div class="emo">{c.get("emoji", "🏆")}</div>'

def carte(c):
    d = lire(c["slug"]) or {}
    lignes = []
    if d.get("fiab") is not None:
        lignes.append(f'<span class="kpi"><b>{d["fiab"]}&nbsp;%</b> fiabilité</span>')
    if d.get("total"):
        if c["statut"] == "passee":
            lignes.append(f'<span class="kpi"><b>{d["joue"]}</b>/{d["total"]} matchs</span>')
        else:
            j = f'J{d["journee"]}' if d.get("journee") else f'{d["joue"]}/{d["total"]}'
            lignes.append(f'<span class="kpi"><b>{esc(j)}</b> en cours</span>')
    if d.get("note") is not None:
        lignes.append(f'<span class="kpi"><b>{d["note"]}</b>/10 la saison</span>')
    # Une compétition terminée met en avant son vainqueur, une en cours son leader
    gagnant = d.get("vainqueur") or (d.get("leader") if c["statut"] == "passee" else None)
    if gagnant:
        lignes.append(f'<span class="kpi win">🏆 {esc(gagnant)}</span>')
    elif d.get("leader"):
        lignes.append(f'<span class="kpi">🥇 {esc(d["leader"])}</span>')
    kpis = "".join(lignes) or '<span class="kpi soft">bientôt disponible</span>'
    return (f'<a class="card{" past" if c["statut"] == "passee" else ""}" href="./{c["slug"]}/">'
            f'<div class="flag">{blason(c)}</div>'
            f'<div class="txt"><div class="nom">{esc(c["nom"])}</div>'
            f'<div class="lieu">{esc(c["lieu"])} · {esc(c["saison"])}</div>'
            f'<div class="kpis">{kpis}</div></div>'
            f'<div class="go">→</div></a>')

def bloc_archives():
    """Championnats passés : une seule carte par championnat, celle de la saison la
    plus récente. Les saisons antérieures restent accessibles par le sélecteur, sans
    allonger la page à chaque année archivée."""
    arch = archives_par_championnat()
    blocs = ""
    for c in COMPETITIONS:
        if c["famille"] != "championnat" or c["statut"] != "en_cours":
            continue
        saisons = arch.get(c["slug"]) or []
        if not saisons:
            continue
        recente = saisons[0]
        vue = dict(c, slug=recente["slug"], statut="passee", saison=recente["saison"])
        blocs += '<div class="arch">' + carte(vue)
        if len(saisons) > 1:
            opts = "".join(
                f'<option value="./{s["slug"]}/"{" selected" if s["slug"] == recente["slug"] else ""}>'
                f'{s["saison"]}</option>' for s in saisons)
            blocs += (f'<label class="pick"><span>Saison</span>'
                      f'<select data-nav aria-label="Choisir une saison de {esc(c["nom"])}">'
                      f'{opts}</select></label>')
        blocs += '</div>'
    return blocs

def section(titre, icone, famille):
    blocs = ""
    encours = [c for c in COMPETITIONS if c["famille"] == famille and c["statut"] == "en_cours"]
    if encours:
        blocs += '<div class="sub">En cours</div>' + "".join(carte(c) for c in encours)
    passees = (bloc_archives() if famille == "championnat"
               else "".join(carte(c) for c in COMPETITIONS
                            if c["famille"] == famille and c["statut"] == "passee"))
    if passees:
        blocs += '<div class="sub">Passées</div>' + passees
    if not blocs:
        return ""
    return (f'<section><h2><span class="ic">{icone}</span>{titre}</h2>{blocs}</section>')

PAGE = """<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pronostix — Pronostics IA gratuits, sans pub ni paris</title>
<meta name="description" content="Pronostics IA gratuits du football : Ligue 1, Premier League, Coupe du Monde. Sans publicité, sans paris. Par Nico-Mtn.">
<link rel="preconnect" href="https://flagcdn.com">
<link rel="icon" type="image/png" href="./icon-192.png">
<link rel="apple-touch-icon" href="./icon-192.png">
<meta property="og:title" content="Pronostix — Pronostics IA gratuits du football">
<meta property="og:description" content="Ligue 1, Premier League, Coupe du Monde. Sans publicité, sans paris.">
<meta property="og:image" content="./logo.png">
<meta name="theme-color" content="#2246c7">
<script>
/* Thème appliqué AVANT le premier rendu : évite le flash blanc en mode sombre.
   « auto » suit le système ; le choix explicite est conservé d'une visite à l'autre. */
(function(){try{
 var p=localStorage.getItem("px-theme")||"auto";
 var d=p==="dark"||(p==="auto"&&window.matchMedia("(prefers-color-scheme:dark)").matches);
 document.documentElement.dataset.theme=d?"dark":"light";
 document.documentElement.dataset.pref=p;
}catch(e){document.documentElement.dataset.theme="light";}})();
</script>
<style>
:root{--bg:#f4f6fb;--fg:#1b2333;--card:#fff;--bd:#e6e9f2;--soft:#eef1f8;--mut:#4b5568;
--acc:#2246c7;--sh:rgba(34,70,199,.10)}
html[data-theme="dark"]{--bg:#0f1420;--fg:#e8ecf5;--card:#161d2e;--bd:#242d42;--soft:#242d42;
--mut:#94a0b8;--sh:rgba(0,0,0,.35)}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:var(--bg);color:var(--fg);-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:0 16px 48px}
header{text-align:center;padding:30px 16px 26px;position:relative}
header img.mark{width:64px;height:64px;border-radius:16px;object-fit:cover;margin-bottom:10px}
h1{margin:0;font-size:30px;font-weight:900;letter-spacing:-.02em}
.tag{color:var(--acc);font-weight:700;font-size:14px;margin-top:5px}
.sous{font-size:12px;opacity:.6;margin-top:8px;text-transform:uppercase;letter-spacing:.06em}
.theme{position:absolute;top:18px;right:16px;display:flex;gap:2px;background:var(--soft);
border-radius:99px;padding:3px}
.theme button{border:0;background:transparent;color:var(--mut);width:28px;height:26px;border-radius:99px;
cursor:pointer;font-size:13px;line-height:1;padding:0}
.theme button.on{background:var(--card);color:var(--acc);box-shadow:0 1px 3px var(--sh)}
section{margin-bottom:30px}
h2{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:800;margin:0 0 14px}
h2 .ic{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;
font-size:16px;background:linear-gradient(135deg,#f6c453,#e8a20c);flex:none}
.sub{font-size:11px;font-weight:800;opacity:.5;text-transform:uppercase;letter-spacing:.07em;margin:16px 0 9px}
.card{display:flex;align-items:center;gap:14px;padding:16px;margin-bottom:11px;border-radius:16px;
background:var(--card);border:1px solid var(--bd);text-decoration:none;color:inherit;transition:.15s}
.card:hover{border-color:var(--acc);transform:translateY(-1px);box-shadow:0 6px 18px var(--sh)}
.card.past{opacity:.72}
.flag{flex:none;line-height:1;display:flex;align-items:center}
.flag .emo{font-size:30px}
.flg{border-radius:4px;object-fit:cover;box-shadow:0 0 0 1px rgba(0,0,0,.12)}
.txt{flex:1;min-width:0}
.nom{font-size:17px;font-weight:800}
.lieu{font-size:12px;opacity:.6;margin-top:2px}
.kpis{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px}
.kpi{font-size:11px;font-weight:700;padding:3px 9px;border-radius:99px;background:var(--soft);color:var(--mut)}
.kpi b{color:var(--fg)}
.kpi.win{background:linear-gradient(135deg,#f6c453,#e8a20c);color:#3a2a00}
.kpi.win b{color:#3a2a00}
.kpi.soft{opacity:.7}
.go{font-size:19px;opacity:.35;flex:none}
/* Bloc archive : la carte de la saison la plus récente, plus un sélecteur discret
   qui donne accès aux saisons antérieures sans les empiler à l'écran. */
.arch{margin-bottom:11px}
.arch .card{margin-bottom:0;border-bottom-left-radius:0;border-bottom-right-radius:0}
.pick{display:flex;align-items:center;gap:9px;padding:9px 16px;border:1px solid var(--bd);
border-top:0;border-radius:0 0 16px 16px;background:var(--card);font-size:12px}
.pick span{opacity:.6;font-weight:700;text-transform:uppercase;letter-spacing:.05em}
.pick select{flex:1;min-width:0;font:inherit;font-weight:800;color:var(--fg);
background:var(--soft);border:1px solid var(--bd);border-radius:9px;padding:6px 8px;cursor:pointer}
footer{text-align:center;font-size:11px;opacity:.55;padding:16px;line-height:1.8}
footer a{color:var(--acc)}
</style></head><body>
<header>
 <div class="theme" id="theme" role="group" aria-label="Thème d'affichage">
  <button data-t="light" title="Thème clair" aria-label="Thème clair">☀</button>
  <button data-t="auto" title="Thème automatique" aria-label="Thème automatique">◐</button>
  <button data-t="dark" title="Thème sombre" aria-label="Thème sombre">☾</button>
 </div>
 <img class="mark" src="./logo.png" alt="Pronostix">
 <h1>Pronostix</h1>
 <div class="tag">Nono le robot, roi des prono 👑</div>
 <div class="sous">Pronostics IA · gratuit · sans publicité · sans paris</div>
</header>
<div class="wrap">
__SECTIONS__
</div>
<footer>
 Résultats réels via football-data.org · Pronostics générés par modèle IA<br>
 Créé par <a href="https://github.com/Nico-Mtn">Nico-Mtn</a> · Mise à jour __MAJ__
</footer>
<script>
function applyTheme(p){
 try{localStorage.setItem("px-theme",p);}catch(e){}
 var d=p==="dark"||(p==="auto"&&window.matchMedia("(prefers-color-scheme:dark)").matches);
 document.documentElement.dataset.theme=d?"dark":"light";
 document.documentElement.dataset.pref=p;
 Array.prototype.forEach.call(document.querySelectorAll("#theme button"),function(b){
  b.classList.toggle("on",b.dataset.t===p);});
}
Array.prototype.forEach.call(document.querySelectorAll("#theme button"),function(b){
 b.onclick=function(){applyTheme(b.dataset.t);};});
window.matchMedia("(prefers-color-scheme:dark)").addEventListener("change",function(){
 if(document.documentElement.dataset.pref==="auto") applyTheme("auto");});
applyTheme(document.documentElement.dataset.pref||"auto");

/* Sélecteur de saison : changer d'option ouvre l'archive correspondante. */
Array.prototype.forEach.call(document.querySelectorAll("select[data-nav]"),function(s){
 s.onchange=function(){ if(s.value) location.href=s.value; };});
</script>
</body></html>"""

def main():
    sections = (section("Championnats", "🏆", "championnat")
                + section("Coupes", "🏅", "coupe"))
    maj = (datetime.datetime.now(datetime.timezone.utc)
           + datetime.timedelta(hours=2)).strftime("%d/%m/%Y à %H:%M")
    html = PAGE.replace("__SECTIONS__", sections).replace("__MAJ__", maj)
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    # Empreinte du hub HORS horodatage : évite un déploiement à chaque exécution.
    sig = hashlib.md5(sections.encode("utf-8")).hexdigest()
    with open(os.path.join(ROOT, "hub.sig"), "w", encoding="utf-8") as f:
        f.write(sig)
    print(f"[OK] hub généré — {len(COMPETITIONS)} compétition(s)")

if __name__ == "__main__":
    main()
