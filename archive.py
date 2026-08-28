# -*- coding: utf-8 -*-
# ============================================================================
#  Pronostix — Archives des saisons passées
#  Auteur / Author : Nico-Mtn — https://github.com/Nico-Mtn
#  Projet gratuit, sans publicité, sans paris.
#  Réutilisation libre : un CRÉDIT au créateur (Nico-Mtn) serait grandement
#  apprécié. / If you reuse this model or code, a credit to the creator
#  (Nico-Mtn) would be greatly appreciated.
# ============================================================================
"""
Génère une page par SAISON ARCHIVÉE : résultats journée par journée (réel vs
pronostic), classement final, fiabilité du modèle, meilleurs buteurs, résumé de
la saison et note sur 10 (« cette saison a-t-elle marqué l'histoire ? »).

HONNÊTETÉ MÉTHODOLOGIQUE — les pronostics d'une saison passée n'ont pas été émis
à l'époque : ils sont RECONSTITUÉS a posteriori, en walk-forward. Chaque match est
pronostiqué avec les ratings tels qu'ils étaient AVANT ce match : le modèle ne
connaît jamais le résultat qu'il prédit, ni ceux des journées suivantes. La page
l'indique explicitement pour qu'on ne confonde pas avec un prono réellement joué.

Usage : python3 archive.py   (variable d'env FOOTBALLDATA_KEY)
"""
import os, sys, json, hashlib, datetime
import l1  # réutilise le moteur : Elo, Dixon-Coles, walk-forward, affichage des noms

ROOT = os.path.dirname(os.path.abspath(__file__))

# Saisons à archiver. « saison » = année de départ (2025 => saison 2025-2026).
ARCHIVES = [
    {"slug": "ligue-1-france-2025-2026", "code": "FL1", "nom": "Ligue 1",
     "drapeau": "🇫🇷", "saison": 2025, "libelle": "2025-2026"},
]

# Barème de la note /10 (voir note_saison). Modifiable sans toucher au code.
BAREME = {
    "suspense_titre": 2.5,   # écart final 1er-2e + journée du sacre
    "suspense_bas": 2.0,     # lutte pour le maintien au coude-à-coude
    "buts": 2.0,             # buts par match rapporté à la référence
    "spectacle": 1.5,        # part de matchs à 3 buts ou plus
    "intensite": 2.0,        # renversements : changements de leader, gros écarts comblés
}
REF_BUTS = 2.70              # référence de buts/match d'un grand championnat

def edito(slug):
    """Surcharge éditoriale : data/archives_edito.json permet de remplacer la note
    et/ou le résumé calculés par un jugement humain, saison par saison."""
    try:
        with open(os.path.join(ROOT, "data", "archives_edito.json"), encoding="utf-8") as f:
            return (json.load(f).get("saisons") or {}).get(slug) or {}
    except Exception:
        return {}

# ─── Analyse d'une saison ────────────────────────────────────────────────────
def analyser(matches_raw, standings_raw, scorers_raw):
    """Rejoue la saison : pronostics walk-forward, classement journée par journée,
    et tous les indicateurs nécessaires au résumé et à la note."""
    rows = []
    for m in (matches_raw or {}).get("matches", []):
        ht, at = m.get("homeTeam") or {}, m.get("awayTeam") or {}
        ft = ((m.get("score") or {}).get("fullTime") or {})
        if ft.get("home") is None:
            continue
        rows.append({"id": m.get("id"), "j": m.get("matchday"), "date": (m.get("utcDate") or "")[:10],
                     "home": l1.disp(ht), "away": l1.disp(at),
                     "ch": ht.get("crest"), "ca": at.get("crest"),
                     "sh": ft["home"], "sa": ft["away"], "played": True})
    rows.sort(key=lambda r: (r["date"], r["j"] or 0))

    # Pronostics reconstitués : ratings mis à jour au fil de la saison, jamais en avance
    l1.ELO_START = {}
    preds, _ = l1.walk_forward(rows)

    stats = {"joue": 0, "exact": 0, "bon": 0, "rate": 0, "total": len(rows)}
    feed, buts, gros = [], 0, 0
    for r in rows:
        p = preds[str(r["id"])]
        st = l1.grade(p, r["sh"], r["sa"])
        stats["joue"] += 1; stats[st] += 1
        buts += r["sh"] + r["sa"]
        if r["sh"] + r["sa"] >= 3:
            gros += 1
        feed.append({"j": r["j"], "date": r["date"], "home": r["home"], "away": r["away"],
                     "ch": r["ch"], "ca": r["ca"], "reel": [r["sh"], r["sa"]],
                     "prono": [p["sh"], p["sa"]], "conf": p["conf"], "statut": st})

    # Classement final + évolution du leader journée par journée
    table, pts, bp, bc, jou = {}, {}, {}, {}, {}
    leaders, prev_leader, changements = [], None, 0
    par_journee = {}
    for r in rows:
        par_journee.setdefault(r["j"] or 0, []).append(r)
    for j in sorted(par_journee):
        for r in par_journee[j]:
            for team, pour, contre in ((r["home"], r["sh"], r["sa"]), (r["away"], r["sa"], r["sh"])):
                pts.setdefault(team, 0); bp.setdefault(team, 0); bc.setdefault(team, 0); jou.setdefault(team, 0)
                bp[team] += pour; bc[team] += contre; jou[team] += 1
                pts[team] += 3 if pour > contre else (1 if pour == contre else 0)
        if pts:
            lead = sorted(pts, key=lambda t: (-pts[t], -(bp[t] - bc[t])))[0]
            leaders.append({"j": j, "team": lead, "pts": pts[lead]})
            if prev_leader and lead != prev_leader:
                changements += 1
            prev_leader = lead

    # Classement officiel de l'API si disponible, sinon reconstruit
    final = []
    for blk in (standings_raw or {}).get("standings", []):
        if blk.get("type") != "TOTAL":
            continue
        for t in blk.get("table", []):
            tm = t.get("team") or {}
            final.append({"pos": t.get("position"), "team": l1.disp(tm), "crest": tm.get("crest"),
                          "j": t.get("playedGames"), "pts": t.get("points"), "g": t.get("won"),
                          "n": t.get("draw"), "p": t.get("lost"), "bp": t.get("goalsFor"),
                          "bc": t.get("goalsAgainst"), "diff": t.get("goalDifference")})
        break
    if not final:
        ordre = sorted(pts, key=lambda t: (-pts[t], -(bp[t] - bc[t]), -bp[t]))
        final = [{"pos": i, "team": t, "crest": None, "j": jou[t], "pts": pts[t], "g": 0, "n": 0,
                  "p": 0, "bp": bp[t], "bc": bc[t], "diff": bp[t] - bc[t]}
                 for i, t in enumerate(ordre, 1)]

    scorers = []
    for s in (scorers_raw or {}).get("scorers", []):
        pl = s.get("player") or {}; tm = s.get("team") or {}
        scorers.append({"player": pl.get("name"), "team": l1.disp(tm), "crest": tm.get("crest"),
                        "goals": s.get("goals") or 0, "assists": s.get("assists") or 0})

    nb = max(1, len(rows))
    return {"stats": stats, "matches": feed, "table": final, "scorers": scorers,
            "leaders": leaders, "changements": changements,
            "buts_match": round(buts / nb, 2), "part_gros": round(gros / nb, 3),
            "journees": sorted(par_journee)}

def note_saison(a):
    """Note sur 10, détaillée critère par critère. Chaque composante est bornée
    et explicitée : rien n'est opaque, tout est reproductible."""
    t = a["table"]
    det = []
    def add(cle, valeur, libelle):
        v = max(0.0, min(BAREME[cle], valeur))
        det.append({"cle": cle, "note": round(v, 2), "max": BAREME[cle], "libelle": libelle})
        return v

    # 1. Suspense pour le titre : plus l'écart 1er-2e est faible, plus la saison a tenu en haleine
    if len(t) >= 2:
        ecart = (t[0]["pts"] or 0) - (t[1]["pts"] or 0)
        v = BAREME["suspense_titre"] * max(0.0, 1 - ecart / 15.0)
        add("suspense_titre", v, f"{ecart} pt(s) d'écart entre le champion et son dauphin")
    else:
        add("suspense_titre", 0, "classement indisponible")

    # 2. Suspense pour le maintien : écart entre le premier relégable et le premier sauvé
    if len(t) >= 4:
        n = len(t)
        barrage, sauve = t[n - 3], t[n - 4]
        ecart_bas = (sauve["pts"] or 0) - (barrage["pts"] or 0)
        v = BAREME["suspense_bas"] * max(0.0, 1 - ecart_bas / 10.0)
        add("suspense_bas", v, f"{ecart_bas} pt(s) séparaient le maintien de la relégation")
    else:
        add("suspense_bas", 0, "classement indisponible")

    # 3. Buts par match, rapporté à la référence des grands championnats
    bm = a["buts_match"]
    v = BAREME["buts"] * max(0.0, min(1.0, (bm - REF_BUTS + 0.5) / 1.0))
    add("buts", v, f"{bm} buts par match (référence {REF_BUTS})")

    # 4. Spectacle : part de matchs à 3 buts ou plus
    pg = a["part_gros"]
    v = BAREME["spectacle"] * max(0.0, min(1.0, (pg - 0.35) / 0.30))
    add("spectacle", v, f"{round(pg * 100)} % des matchs à 3 buts ou plus")

    # 5. Intensité : nombre de changements de leader au fil de la saison
    ch = a["changements"]
    v = BAREME["intensite"] * min(1.0, ch / 8.0)
    add("intensite", v, f"{ch} changement(s) de leader en cours de saison")

    total = round(sum(d["note"] for d in det), 1)
    if total >= 8.5:   verdict = "Une saison d'anthologie, de celles qu'on raconte longtemps."
    elif total >= 7:   verdict = "Une très bonne cuvée, disputée et spectaculaire."
    elif total >= 5.5: verdict = "Une saison plaisante, sans être inoubliable."
    elif total >= 4:   verdict = "Une saison classique, au scénario vite écrit."
    else:              verdict = "Une saison sans grand suspense, dominée de bout en bout."
    return {"note": total, "sur": 10, "detail": det, "verdict": verdict}

def resume(a, lg):
    """Résumé factuel de la saison, construit uniquement à partir des données."""
    t, ph = a["table"], []
    if t:
        c = t[0]
        ph.append(f"{c['team']} termine champion avec {c['pts']} points"
                  + (f" ({c['g']} victoires)" if c.get("g") else "") + ".")
        if len(t) > 1:
            e = (t[0]["pts"] or 0) - (t[1]["pts"] or 0)
            ph.append(f"{t[1]['team']} suit à {e} point(s)." if e else
                      f"{t[1]['team']} termine à égalité de points, départagé à la différence de buts.")
        if len(t) >= 3:
            ph.append("Le podium est complété par " + t[2]["team"] + ".")
        if len(t) >= 3:
            relegues = [x["team"] for x in t[-2:]]
            ph.append("Descendent en division inférieure : " + " et ".join(relegues) + ".")
    if a["scorers"]:
        b = a["scorers"][0]
        ph.append(f"{b['player']} ({b['team']}) finit meilleur buteur avec {b['goals']} buts.")
    ph.append(f"Sur l'ensemble de la saison, {a['buts_match']} buts ont été inscrits par match.")
    if a["changements"]:
        ph.append(f"La tête du classement a changé {a['changements']} fois.")
    return " ".join(ph)

# ─── Page HTML ───────────────────────────────────────────────────────────────
PAGE = """<!DOCTYPE html><html lang="fr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pronostix — __NOM__ __LIB__ (archive)</title>
<meta name="description" content="Archive de la saison __LIB__ de __NOM__ : résultats, classement, buteurs, fiabilité des pronostics. Sans publicité, sans paris.">
<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
background:#f4f6fb;color:#1b2333;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:0 14px 44px}
header{background:#fff;border-bottom:1px solid #e6e9f2;padding:16px 0 12px}
.hrow{max-width:820px;margin:0 auto;padding:0 14px;display:flex;align-items:center;gap:12px}
h1{margin:0;font-size:20px;font-weight:900}
.sub{font-size:11px;opacity:.6;text-transform:uppercase;letter-spacing:.05em;margin-top:3px}
.arch{margin-left:auto;font-size:10px;font-weight:800;padding:4px 10px;border-radius:99px;
background:#eef1f8;color:#5a6478;text-transform:uppercase;letter-spacing:.05em}
.compnav{display:flex;gap:8px;margin:14px 0 8px;flex-wrap:wrap}
.compnav a{flex:1;min-width:120px;text-align:center;padding:11px;border-radius:12px;text-decoration:none;
font-weight:800;font-size:13px;background:#fff;border:1px solid #e6e9f2;color:#5a6478}
.hero{border-radius:18px;padding:22px 18px;text-align:center;margin:6px 0 18px;
background:linear-gradient(135deg,rgba(246,196,83,.22),rgba(232,162,12,.10));border:1px solid rgba(232,162,12,.35)}
.hero .nt{font-size:44px;font-weight:900;line-height:1;color:#e8a20c}
.hero .sur{font-size:14px;opacity:.6;font-weight:700}
.hero .vd{font-size:14px;font-weight:700;margin-top:8px}
.card{background:#fff;border:1px solid #e6e9f2;border-radius:16px;padding:18px 16px;margin-bottom:16px}
.ctitle{display:flex;align-items:center;gap:9px;margin-bottom:14px}
.ctitle .ic{width:30px;height:30px;border-radius:9px;display:flex;align-items:center;justify-content:center;
font-size:15px;background:linear-gradient(135deg,#f6c453,#e8a20c);flex:none}
.ctitle h3{margin:0;font-size:15px;font-weight:800}
.crit{display:flex;align-items:center;gap:10px;padding:9px 0}
.crit+.crit{border-top:1px solid #eef0f6}
.crit .lb{flex:1;font-size:13px}
.crit .bar{width:110px;height:7px;border-radius:5px;background:rgba(127,127,127,.14);overflow:hidden;flex:none}
.crit .bar i{display:block;height:100%;background:linear-gradient(90deg,#f6c453,#e8a20c)}
.crit .vl{font-weight:900;font-size:13px;min-width:56px;text-align:right}
.txt{font-size:14px;line-height:1.75}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:10px}
.st{text-align:center;padding:13px 6px;border-radius:13px;background:rgba(127,127,127,.10)}
.st b{display:block;font-size:20px;font-weight:900}.st span{font-size:10px;opacity:.7;text-transform:uppercase}
.st.ok b{color:#16a34a}.st.ko b{color:#dc2626}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:10px;opacity:.55;text-transform:uppercase;padding:6px 4px;font-weight:800}
td{padding:8px 4px;border-top:1px solid #eef0f6}
td.n{text-align:center;width:26px;font-weight:800}td.p{text-align:center;font-weight:900}
tr.c1 td.n{color:#16a34a}tr.c3 td.n{color:#dc2626}
.tm{display:flex;align-items:center;gap:8px}.tm img{width:20px;height:20px;object-fit:contain}
.jsel{display:flex;gap:6px;overflow-x:auto;padding:4px 0 12px}
.jsel button{flex:none;padding:7px 13px;border-radius:99px;border:1px solid #e6e9f2;background:#fff;
font-weight:800;font-size:12px;color:#5a6478;cursor:pointer}
.jsel button.on{background:#2246c7;color:#fff;border-color:#2246c7}
.m{display:flex;align-items:center;gap:10px;padding:11px 2px}
.m+.m{border-top:1px solid #eef0f6}
.m .t{flex:1;display:flex;align-items:center;gap:7px;min-width:0}
.m .t.a{justify-content:flex-end;text-align:right}
.m .t b{font-weight:700;font-size:14px}
.m img{width:22px;height:22px;object-fit:contain}
.sc2{flex:none;text-align:center;min-width:96px}
.sc2 .v{font-size:16px;font-weight:900}
.sc2 .pr{font-size:11px;opacity:.65;margin-top:1px}
.bd{font-size:10px;font-weight:800;padding:2px 7px;border-radius:99px;margin-left:5px}
.bd.ex{background:#dcfce7;color:#166534}.bd.bo{background:#fef3c7;color:#92400e}.bd.ra{background:#fee2e2;color:#991b1b}
.note{font-size:11px;opacity:.62;margin-top:10px;line-height:1.6}
footer{text-align:center;font-size:11px;opacity:.55;padding:20px 14px;line-height:1.8}
footer a{color:#2246c7}
@media(prefers-color-scheme:dark){
body{background:#0f1420;color:#e8ecf5}header{background:#161d2e;border-color:#242d42}
.card,.compnav a,.jsel button{background:#161d2e;border-color:#242d42}
.compnav a,.jsel button{color:#94a0b8}
td,.m+.m,.crit+.crit{border-color:#242d42}.arch{background:#242d42;color:#94a0b8}}
</style></head><body>
<header><div class="hrow">
 <div><h1>__NOM__ <span style="opacity:.5">__LIB__</span></h1>
  <div class="sub">Archive · saison terminée</div></div>
 <div class="arch">📚 Archive</div>
</div></header>
<div class="wrap">
 <div class="compnav">__NAV__</div>
 <div id="app"></div>
</div>
<footer>
 Résultats réels via football-data.org · Pronostics reconstitués a posteriori<br>
 Créé par <a href="https://github.com/Nico-Mtn">Nico-Mtn</a> · Projet gratuit, sans publicité, sans paris
</footer>
<script>
var D = /*__DATA__*/null;
var jSel = null;
function esc(s){return String(s==null?"":s).replace(/[&<>"]/g,function(c){
 return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});}
function logo(u){return u?'<img src="'+esc(u)+'" alt="" loading="lazy">':'';}
function heroHtml(){
 var n=D.note;
 return '<div class="hero"><div class="nt">'+n.note+'<span class="sur"> / '+n.sur+'</span></div>'
  +'<div class="vd">'+esc(n.verdict)+'</div></div>';
}
function critHtml(){
 var h='<div class="card"><div class="ctitle"><span class="ic">⭐</span><h3>Comment cette note est calculée</h3></div>';
 D.note.detail.forEach(function(c){
  h+='<div class="crit"><span class="lb">'+esc(c.libelle)+'</span>'
   +'<span class="bar"><i style="width:'+Math.round(c.note/c.max*100)+'%"></i></span>'
   +'<span class="vl">'+c.note+'/'+c.max+'</span></div>';
 });
 return h+'<div class="note">Chaque critère est calculé à partir des résultats réels de la saison, puis borné. '
  +'Le total constitue la note finale.</div></div>';
}
function resumeHtml(){
 return '<div class="card"><div class="ctitle"><span class="ic">📖</span><h3>Résumé de la saison</h3></div>'
  +'<div class="txt">'+esc(D.resume)+'</div></div>';
}
function fiabHtml(){
 var s=D.stats,j=s.joue||0,ok=(s.exact||0)+(s.bon||0);
 return '<div class="card"><div class="ctitle"><span class="ic">🤖</span><h3>Fiabilité des pronostics</h3></div>'
  +'<div class="stats"><div class="st"><b>'+(j?((ok/j*100).toFixed(1)+" %"):"—")+'</b><span>fiabilité</span></div>'
  +'<div class="st"><b>'+j+'</b><span>matchs</span></div>'
  +'<div class="st ok"><b>'+(s.exact||0)+'</b><span>exacts</span></div>'
  +'<div class="st ok"><b>'+(s.bon||0)+'</b><span>bons</span></div>'
  +'<div class="st ko"><b>'+(s.rate||0)+'</b><span>ratés</span></div></div>'
  +'<div class="note">⚠️ Ces pronostics n\\'ont pas été émis à l\\'époque : ils sont <b>reconstitués a posteriori</b>. '
  +'Chaque match a été pronostiqué avec les données disponibles <b>avant</b> ce match uniquement — '
  +'le modèle n\\'a jamais connu le résultat qu\\'il prédit.</div></div>';
}
function tableHtml(){
 var r=D.table||[];
 if(!r.length) return "";
 var h='<div class="card"><div class="ctitle"><span class="ic">📊</span><h3>Classement final</h3></div>'
  +'<table><tr><th></th><th>Équipe</th><th>J</th><th>Diff</th><th>Pts</th></tr>';
 r.forEach(function(x){
  var c=x.pos<=3?"c1":(x.pos>=r.length-2?"c3":"");
  h+='<tr class="'+c+'"><td class="n">'+x.pos+'</td><td><div class="tm">'+logo(x.crest)+esc(x.team)+'</div></td>'
   +'<td class="n">'+(x.j||0)+'</td><td class="n">'+((x.diff>0?"+":"")+(x.diff||0))+'</td>'
   +'<td class="p">'+(x.pts||0)+'</td></tr>';
 });
 return h+'</table></div>';
}
function scorersHtml(){
 var s=D.scorers||[];
 if(!s.length) return "";
 var mx=s[0].goals||1;
 var h='<div class="card"><div class="ctitle"><span class="ic">⚽</span><h3>Meilleurs buteurs</h3></div><table>';
 s.slice(0,10).forEach(function(p,i){
  h+='<tr><td class="n">'+(i+1)+'</td><td><div class="tm">'+logo(p.crest)+'<b>'+esc(p.player)+'</b></div>'
   +'<div style="height:6px;border-radius:4px;background:rgba(127,127,127,.14);margin-top:5px;overflow:hidden">'
   +'<span style="display:block;height:100%;width:'+Math.round((p.goals||0)/mx*100)+'%;'
   +'background:linear-gradient(90deg,#f6c453,#e8a20c)"></span></div></td>'
   +'<td style="opacity:.6;font-size:11px">'+esc(p.team)+'</td><td class="p">'+(p.goals||0)+'</td></tr>';
 });
 return h+'</table></div>';
}
function journeeHtml(){
 var js=D.journees||[];
 if(!js.length) return "";
 if(jSel===null) jSel=js[0];
 var sel='<div class="jsel">'+js.map(function(j){
   return '<button class="'+(j===jSel?"on":"")+'" onclick="jSel='+j+';draw();">J'+j+'</button>';
 }).join("")+'</div>';
 var ms=(D.matches||[]).filter(function(m){return m.j===jSel;});
 var h='<div class="card"><div class="ctitle"><span class="ic">'+jSel+'</span><h3>Journée '+jSel+' — réel vs pronostic</h3></div>';
 ms.forEach(function(m){
  var bd=m.statut==="exact"?'<span class="bd ex">exact</span>':
         (m.statut==="bon"?'<span class="bd bo">bon</span>':'<span class="bd ra">raté</span>');
  h+='<div class="m"><div class="t">'+logo(m.ch)+'<b>'+esc(m.home)+'</b></div>'
   +'<div class="sc2"><div class="v">'+m.reel[0]+' – '+m.reel[1]+'</div>'
   +'<div class="pr">prono '+m.prono[0]+'–'+m.prono[1]+bd+'</div></div>'
   +'<div class="t a"><b>'+esc(m.away)+'</b>'+logo(m.ca)+'</div></div>';
 });
 return sel+h+'</div>';
}
function draw(){
 document.getElementById("app").innerHTML =
  heroHtml()+resumeHtml()+critHtml()+fiabHtml()+journeeHtml()+tableHtml()+scorersHtml();
}
draw();
</script></body></html>"""

def nav_html():
    items = ['<a href="../">🏠 Accueil</a>']
    for lg in l1.LEAGUES:
        items.append(f'<a href="../{lg["slug"]}/">{lg["drapeau"]} {lg["nom"]}</a>')
    return "\n  ".join(items)

def build_archive(a):
    l1.set_league({"slug": a["slug"], "prefix": "arch_" + a["slug"][:12],
                   "code": a["code"], "nom": a["nom"], "saison": a["saison"],
                   "libelle": a["libelle"], "drapeau": a["drapeau"]})
    outdir = os.path.join(ROOT, a["slug"])
    os.makedirs(outdir, exist_ok=True)
    cache = os.path.join(ROOT, "data", f"archive_{a['slug']}.json")

    m = l1.api_get(f"/competitions/{a['code']}/matches?season={a['saison']}")
    s = l1.api_get(f"/competitions/{a['code']}/standings?season={a['saison']}")
    b = l1.api_get(f"/competitions/{a['code']}/scorers?season={a['saison']}&limit=20")
    if m and m.get("matches"):
        try:
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({"matches": m, "standings": s, "scorers": b}, f, ensure_ascii=False)
        except Exception:
            pass
    elif os.path.exists(cache):   # une archive est figée : le cache suffit ensuite
        with open(cache, encoding="utf-8") as f:
            d = json.load(f)
        m, s, b = d.get("matches"), d.get("standings"), d.get("scorers")
    if not (m and m.get("matches")):
        print(f"[SKIP] {a['slug']} : aucune donnée disponible", file=sys.stderr)
        return None

    an = analyser(m, s, b)
    ed = edito(a["slug"])
    note = note_saison(an)
    res = resume(an, a)
    if ed.get("note") is not None:
        note["note"] = ed["note"]
        note["verdict"] = ed.get("verdict", note["verdict"])
    if ed.get("resume"):
        res = ed["resume"]

    payload = {"nom": a["nom"], "libelle": a["libelle"], "slug": a["slug"],
               "stats": an["stats"], "matches": an["matches"], "table": an["table"],
               "scorers": an["scorers"], "journees": an["journees"],
               "buts_match": an["buts_match"], "note": note, "resume": res,
               "credit": "Auteur : Nico-Mtn (https://github.com/Nico-Mtn)."}
    html = (PAGE.replace("__NAV__", nav_html()).replace("__NOM__", a["nom"])
                .replace("__LIB__", a["libelle"])
                .replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False)))
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(outdir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    sig = hashlib.md5(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    with open(os.path.join(outdir, "content.sig"), "w", encoding="utf-8") as f:
        f.write(sig)
    st = an["stats"]
    print(f"[OK] {a['slug']} — note {note['note']}/10 | {st['joue']} matchs : "
          f"{st['exact']} exacts, {st['bon']} bons, {st['rate']} ratés")
    return payload

def main():
    for a in ARCHIVES:
        try:
            build_archive(a)
        except Exception as e:
            print(f"[ERREUR] {a['slug']} : {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
