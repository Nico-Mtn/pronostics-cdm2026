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
import os, json, hashlib, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))

# Déclaration des compétitions. `statut` : "en_cours" ou "passee".
COMPETITIONS = [
    {"slug": "ligue-1-france", "nom": "Ligue 1", "lieu": "France", "drapeau": "🇫🇷",
     "famille": "championnat", "statut": "en_cours", "saison": "2026-2027"},
    {"slug": "premier-league-england", "nom": "Premier League", "lieu": "Angleterre",
     "drapeau": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "famille": "championnat", "statut": "en_cours", "saison": "2026-2027"},
    {"slug": "pronostics-cdm2026", "nom": "Coupe du Monde 2026",
     "lieu": "États-Unis · Canada · Mexique", "drapeau": "🏆",
     "famille": "coupe", "statut": "passee", "saison": "2026"},
]

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
    # Championnat : leader du classement réel
    tb = d.get("table") or []
    if tb:
        info["leader"] = tb[0].get("team")
    return info

def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))

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
    if d.get("vainqueur"):
        lignes.append(f'<span class="kpi win">🏆 {esc(d["vainqueur"])}</span>')
    elif d.get("leader"):
        lignes.append(f'<span class="kpi">🥇 {esc(d["leader"])}</span>')
    kpis = "".join(lignes) or '<span class="kpi soft">bientôt disponible</span>'
    return (f'<a class="card{" past" if c["statut"] == "passee" else ""}" href="./{c["slug"]}/">'
            f'<div class="flag">{c["drapeau"]}</div>'
            f'<div class="txt"><div class="nom">{esc(c["nom"])}</div>'
            f'<div class="lieu">{esc(c["lieu"])} · {esc(c["saison"])}</div>'
            f'<div class="kpis">{kpis}</div></div>'
            f'<div class="go">→</div></a>')

def section(titre, icone, famille):
    blocs = ""
    for statut, label in (("en_cours", "En cours"), ("passee", "Passées")):
        items = [c for c in COMPETITIONS if c["famille"] == famille and c["statut"] == statut]
        if not items:
            continue
        blocs += f'<div class="sub">{label}</div>' + "".join(carte(c) for c in items)
    if not blocs:
        return ""
    return (f'<section><h2><span class="ic">{icone}</span>{titre}</h2>{blocs}</section>')

PAGE = """<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pronostix — Pronostics IA gratuits, sans pub ni paris</title>
<meta name="description" content="Pronostics IA gratuits du football : Ligue 1, Premier League, Coupe du Monde. Sans publicité, sans paris. Par Nico-Mtn.">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:#f4f6fb;color:#1b2333;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:0 16px 48px}
header{text-align:center;padding:34px 16px 26px}
h1{margin:0;font-size:30px;font-weight:900;letter-spacing:-.02em}
.tag{color:#2246c7;font-weight:700;font-size:14px;margin-top:5px}
.sous{font-size:12px;opacity:.6;margin-top:8px;text-transform:uppercase;letter-spacing:.06em}
section{margin-bottom:30px}
h2{display:flex;align-items:center;gap:10px;font-size:17px;font-weight:800;margin:0 0 14px}
h2 .ic{width:32px;height:32px;border-radius:10px;display:flex;align-items:center;justify-content:center;
font-size:16px;background:linear-gradient(135deg,#f6c453,#e8a20c);flex:none}
.sub{font-size:11px;font-weight:800;opacity:.5;text-transform:uppercase;letter-spacing:.07em;margin:16px 0 9px}
.card{display:flex;align-items:center;gap:14px;padding:16px;margin-bottom:11px;border-radius:16px;
background:#fff;border:1px solid #e6e9f2;text-decoration:none;color:inherit;transition:.15s}
.card:hover{border-color:#2246c7;transform:translateY(-1px);box-shadow:0 6px 18px rgba(34,70,199,.10)}
.card.past{opacity:.72}
.flag{font-size:30px;flex:none;line-height:1}
.txt{flex:1;min-width:0}
.nom{font-size:17px;font-weight:800}
.lieu{font-size:12px;opacity:.6;margin-top:2px}
.kpis{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px}
.kpi{font-size:11px;font-weight:700;padding:3px 9px;border-radius:99px;background:#eef1f8;color:#4b5568}
.kpi{color:#4b5568}
.kpi b{color:#1b2333}
.kpi.win{background:linear-gradient(135deg,#f6c453,#e8a20c);color:#3a2a00}
.kpi.win b{color:#3a2a00}
.kpi.soft{opacity:.7}
.go{font-size:19px;opacity:.35;flex:none}
footer{text-align:center;font-size:11px;opacity:.55;padding:16px;line-height:1.8}
footer a{color:#2246c7}
@media(prefers-color-scheme:dark){
body{background:#0f1420;color:#e8ecf5}
.card{background:#161d2e;border-color:#242d42}
.kpi{background:#242d42;color:#94a0b8}.kpi b{color:#e8ecf5}}
</style></head><body>
<header>
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
