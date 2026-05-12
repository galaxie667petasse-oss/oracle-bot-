import os, json, asyncio, logging, re, aiohttp, pytz
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN        = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID      = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS    = [k.strip() for k in os.getenv("GROQ_KEYS","").split(",") if k.strip()]
ODDSPAPI_KEY = os.getenv("ODDSPAPI_KEY", "")
SCAN_HOUR    = int(os.getenv("SCAN_HOUR", "10"))
DB_FILE      = Path("oracle_db.json")
GROQ_IDX     = 0

def next_key():
    global GROQ_IDX
    if not GROQ_KEYS: raise ValueError("Aucune cle Groq")
    k = GROQ_KEYS[GROQ_IDX % len(GROQ_KEYS)]
    GROQ_IDX += 1
    return k

def load_db():
    if DB_FILE.exists():
        try: return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except: pass
    return {"scans": {}, "lessons": []}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def get_target():
    now = datetime.now()
    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS  = ["janvier","fevrier","mars","avril","mai","juin","juillet",
              "aout","septembre","octobre","novembre","decembre"]
    return {
        "label":    f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month-1]} {now.year}",
        "key":      now.strftime("%d/%m/%Y"),
        "iso_date": now.strftime("%Y-%m-%d"),
        "hour":     now.hour,
    }

# ── GROQ HTTP DIRECT ──────────────────────────────────────────────────────────
async def call_groq(system: str, user: str, max_tokens: int = 500) -> str:
    key = next_key()
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role":"system","content":system},{"role":"user","content":user}],
        "max_tokens": max_tokens, "temperature": 0.7,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(4):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 429:
                        await asyncio.sleep((attempt+1)*6); continue
                    if resp.status != 200:
                        txt = await resp.text()
                        raise RuntimeError(f"ERREUR GROQ {resp.status}: {txt[:200]}")
                    data = await resp.json()
                    await asyncio.sleep(max(0.3, 0.8/max(1,len(GROQ_KEYS))))
                    return data["choices"][0]["message"]["content"].strip()
        except RuntimeError: raise
        except Exception as e:
            log.warning(f"Groq attempt {attempt+1}: {e}")
            if attempt == 3: raise RuntimeError(f"ERREUR GROQ: {e}")
            await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

# ── ODDSPAPI — MATCHS + COTES REELLES ────────────────────────────────────────
SPORT_KEYS = {
    "soccer_france_ligue1":            "Ligue 1",
    "soccer_france_ligue2":            "Ligue 2",
    "soccer_england_premier":          "Premier League",
    "soccer_england_efl_champ":        "Championship",
    "soccer_spain_la_liga":            "La Liga",
    "soccer_italy_serie_a":            "Serie A",
    "soccer_germany_bundesliga":       "Bundesliga",
    "soccer_uefa_champs_league":       "Champions League",
    "soccer_uefa_europa_league":       "Europa League",
    "soccer_uefa_europa_conf_league":  "Conference League",
    "soccer_portugal_primeira":        "Primeira Liga",
    "soccer_netherlands_erediv":       "Eredivisie",
}

async def fetch_matches(iso_date: str, label: str) -> list:
    """Recupere les matchs du jour via OddsPapi — 1 requete avec retry intelligent."""
    if not ODDSPAPI_KEY:
        raise RuntimeError("ERREUR: ODDSPAPI_KEY manquante dans Railway")

    paris_tz = pytz.timezone("Europe/Paris")
    COMP_MAP = {
        "soccer_france_ligue1":           "Ligue 1",
        "soccer_france_ligue2":           "Ligue 2",
        "soccer_england_premier":         "Premier League",
        "soccer_england_efl_champ":       "Championship",
        "soccer_spain_la_liga":           "La Liga",
        "soccer_italy_serie_a":           "Serie A",
        "soccer_germany_bundesliga":      "Bundesliga",
        "soccer_uefa_champs_league":      "Champions League",
        "soccer_uefa_europa_league":      "Europa League",
        "soccer_uefa_europa_conf_league": "Conference League",
        "soccer_portugal_primeira":       "Primeira Liga",
        "soccer_netherlands_erediv":      "Eredivisie",
    }

    # Differentes tentatives de params en cas d erreur
    param_attempts = [
        # Tentative 1: avec filtre date
        {
            "apiKey":           ODDSPAPI_KEY,
            "sportId":          10,
            "bookmakers":       "bet365,unibet",
            "markets":          "h2h",
            "commenceTimeFrom": f"{iso_date}T00:00:00Z",
            "commenceTimeTo":   f"{iso_date}T23:59:59Z",
        },
        # Tentative 2: sans filtre date
        {
            "apiKey":     ODDSPAPI_KEY,
            "sportId":    10,
            "bookmakers": "bet365,unibet",
            "markets":    "h2h",
        },
        # Tentative 3: sport football specifique
        {
            "apiKey":     ODDSPAPI_KEY,
            "sportId":    "soccer",
            "bookmakers": "bet365",
            "markets":    "h2h",
        },
    ]

    data = None
    async with aiohttp.ClientSession() as session:
        for attempt_num, params in enumerate(param_attempts):
            # Attendre entre chaque tentative pour eviter rate limit
            if attempt_num > 0:
                wait = attempt_num * 2
                log.info(f"OddsPapi: attente {wait}s avant tentative {attempt_num+1}")
                await asyncio.sleep(wait)

            for retry in range(3):
                if retry > 0:
                    await asyncio.sleep(retry * 1.5)
                try:
                    async with session.get(
                        "https://api.oddspapi.io/v4/odds",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=20)
                    ) as resp:
                        if resp.status == 401:
                            raise RuntimeError("ERREUR: Cle ODDSPAPI invalide ou expiree")
                        if resp.status == 429:
                            # Extraire le temps d attente depuis la reponse
                            try:
                                err = await resp.json()
                                details = err.get("error",{}).get("details","")
                                # Parser "wait X.XX seconds"
                                wm = re.search(r"(\d+\.?\d*)\s*second", details)
                                wait_time = float(wm.group(1)) + 0.5 if wm else 2.0
                            except:
                                wait_time = 2.0
                            log.warning(f"OddsPapi 429 — attente {wait_time:.1f}s")
                            await asyncio.sleep(wait_time)
                            continue  # Retry
                        if resp.status == 400:
                            log.warning(f"OddsPapi 400 params={list(params.keys())}")
                            break  # Essayer params suivants
                        if resp.status != 200:
                            txt = await resp.text()
                            log.warning(f"OddsPapi {resp.status}: {txt[:150]}")
                            break
                        data = await resp.json()
                        log.info(f"OddsPapi: reponse OK (tentative {attempt_num+1})")
                        break
                except RuntimeError: raise
                except Exception as e:
                    log.warning(f"OddsPapi connexion: {e}")
                    await asyncio.sleep(1)

            if data:
                break

        if not data:
            raise RuntimeError("OddsPapi: impossible de recuperer les matchs apres toutes les tentatives")

        matches = []
        for event in data.get("data", []):
            commence = event.get("commenceTime", "")
            if not commence: continue
            try:
                dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                dt_p = dt.astimezone(paris_tz)
                if dt_p.strftime("%Y-%m-%d") != iso_date: continue
                heure = dt_p.strftime("%H:%M")
            except: continue

            # Identifier la competition
            sport_key = event.get("sportKey", event.get("sport", {}).get("key", ""))
            comp_name = COMP_MAP.get(sport_key)
            if not comp_name:
                league_name = (event.get("league", {}).get("name", "") or
                               event.get("competition", {}).get("name", "") or "")
                for k, v in COMP_MAP.items():
                    if v.lower() in league_name.lower():
                        comp_name = v; break
            if not comp_name: continue

            home = event.get("homeTeam", {}).get("name", "?")
            away = event.get("awayTeam", {}).get("name", "?")

            # Extraire cotes 1X2
            ch = cd = ca = bk_used = None
            bk_odds = event.get("bookmakerOdds", {})
            for bk in ["bet365", "unibet", "winamax", "pinnacle"]:
                bk_data = bk_odds.get(bk, {})
                for mkt in bk_data.get("markets", {}).values():
                    h = d = a = None
                    for oid, out in mkt.get("outcomes", {}).items():
                        price = out.get("players", {}).get("0", {}).get("price")
                        if price:
                            try: price = float(price)
                            except: continue
                            if str(oid) == "101": h = price
                            elif str(oid) == "102": d = price
                            elif str(oid) == "103": a = price
                    if h and a:
                        ch, cd, ca, bk_used = h, d, a, bk
                        break
                if ch: break

            matches.append({
                "home": home, "away": away, "competition": comp_name,
                "date": label, "heure": heure,
                "cote_home": ch, "cote_draw": cd, "cote_away": ca,
                "bookmaker": bk_used or "?",
            })

    matches.sort(key=lambda m: m.get("heure", "99:99"))
    log.info(f"OddsPapi: {len(matches)} matchs filtres pour {iso_date}")
    return matches[:12]

# ── METEO (wttr.in — sans cle API) ───────────────────────────────────────────
TEAM_CITY = {
    "Paris Saint Germain":"Paris","PSG":"Paris","Marseille":"Marseille",
    "Lyon":"Lyon","Lille":"Lille","Monaco":"Monaco","Rennes":"Rennes",
    "Lens":"Lens","Strasbourg":"Strasbourg","Nantes":"Nantes","Brest":"Brest",
    "Toulouse":"Toulouse","Nice":"Nice","Angers":"Angers","Auxerre":"Auxerre",
    "Le Havre":"Le Havre","Metz":"Metz","Lorient":"Lorient","Reims":"Reims",
    "Manchester City":"Manchester","Manchester United":"Manchester",
    "Arsenal":"London","Chelsea":"London","Tottenham":"London",
    "Crystal Palace":"London","West Ham":"London","Brentford":"London",
    "Nottingham Forest":"Nottingham","Aston Villa":"Birmingham",
    "Liverpool":"Liverpool","Everton":"Liverpool","Newcastle":"Newcastle",
    "Leeds United":"Leeds","Brighton":"Brighton","Southampton":"Southampton",
    "Burnley":"Burnley","Middlesbrough":"Middlesbrough","Sunderland":"Sunderland",
    "Real Madrid":"Madrid","Atletico Madrid":"Madrid","Rayo Vallecano":"Madrid",
    "FC Barcelona":"Barcelona","Valencia":"Valencia","Sevilla":"Sevilla",
    "Real Betis":"Sevilla","Athletic Club":"Bilbao","Osasuna":"Pamplona",
    "Celta Vigo":"Vigo","Girona":"Girona","Real Sociedad":"San Sebastian",
    "Juventus":"Turin","AC Milan":"Milan","Inter":"Milan","AS Roma":"Rome",
    "Lazio":"Rome","Napoli":"Naples","Atalanta":"Bergamo","Fiorentina":"Florence",
    "Bologna":"Bologna","Torino":"Turin",
    "Bayern Munich":"Munich","Borussia Dortmund":"Dortmund",
    "Bayer Leverkusen":"Leverkusen","SC Freiburg":"Freiburg",
    "RB Leipzig":"Leipzig","Eintracht Frankfurt":"Frankfurt",
    "Benfica":"Lisbon","Sporting CP":"Lisbon","Porto":"Porto","SC Braga":"Braga",
    "Shakhtar Donetsk":"Krakow","Dynamo Kyiv":"Krakow",
}

def get_city(team: str) -> str:
    for k,v in TEAM_CITY.items():
        if k.lower() in team.lower() or team.lower() in k.lower(): return v
    return team.split()[0]

async def fetch_weather(home_team: str) -> str:
    city = get_city(home_team)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{city.replace(' ','+')}?format=j1",
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status != 200: return "Meteo indisponible"
                d = await r.json(content_type=None)
                c = d.get("current_condition",[{}])[0]
                return (f"{c.get('weatherDesc',[{}])[0].get('value','?')}, "
                        f"{c.get('temp_C','?')}°C, "
                        f"Vent {c.get('windspeedKmph','?')}km/h, "
                        f"Pluie {c.get('precipMM','0')}mm")
    except: return "Meteo indisponible"

# ── CONTEXTE SPORTIF VIA GROQ ─────────────────────────────────────────────────
async def fetch_context(match: dict) -> str:
    prompt = (
        f"Match: {match['home']} vs {match['away']}\n"
        f"Competition: {match['competition']} | {match['date']}\n\n"
        f"Donne le contexte sportif REEL en francais (150 mots max):\n"
        f"- Forme recente des deux equipes (5 derniers matchs si connus)\n"
        f"- Blessures et suspensions connues\n"
        f"- Enjeux du match\n"
        f"- H2H recent\n"
        f"Si tu n'es pas certain d'une info, dis-le. Ne jamais inventer."
    )
    return await call_groq(
        "Expert football europeen 2024-2025. Tu donnes uniquement des infos factuelles. "
        "Si tu n'es pas sur d'une stat, tu le signales clairement.",
        prompt, 280
    )

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {"id":"tact",  "n":"Tacticien",    "e":"🧠",
     "s":"Expert tacticien football. Analyse formations, pressing, transitions. 80 mots max. Francais."},
    {"id":"stat",  "n":"Statisticien", "e":"📊",
     "s":"Analyste statistique. Analyse forme, H2H, probabilites depuis les cotes. 80 mots max. Francais."},
    {"id":"doc",   "n":"Medecin",      "e":"🏃",
     "s":"Medecin sportif. Analyse fatigue, blessures mentionnees, rotations. 80 mots max. Francais."},
    {"id":"scout", "n":"L'Ancien",     "e":"🧓",
     "s":"Scout legendaire 40 ans. Patterns caches, pieges, enjeux. 80 mots max. Francais."},
    {"id":"mkt",   "n":"Marche",       "e":"💰",
     "s":"Expert value betting. Calcule proba implicite des cotes vs proba reelle. Identifie value bets. 80 mots max. Francais."},
    {"id":"psy",   "n":"Psychologue",  "e":"🎭",
     "s":"Psychologue sport. Pression, motivation, effet domicile, enjeux. 80 mots max. Francais."},
    {"id":"juge",  "n":"Juge",         "e":"⚖️",
     "s":"Juge Arbitre. Synthetise les 6 rapports. Consensus et divergences. 130 mots max. Francais."},
    {"id":"pr1",   "n":"Prof Pragma",  "e":"🎓",
     "s":"Professeur Pragmatique. Identifie les failles, sois critique et realiste. 100 mots max. Francais."},
    {"id":"pr2",   "n":"Prof Vision",  "e":"🔭", "s":""},
]

def winrate_by_type(db: dict) -> str:
    picks = [p for s in db.get("scans",{}).values() for p in s.get("picks",[])]
    dec   = [p for p in picks if p.get("result") in ["win","loss"]]
    if len(dec) < 3: return ""
    cats = {}
    for p in dec:
        t = p.get("pari","").lower()
        k = ("btts" if "btts" in t else "over" if "plus de" in t else
             "under" if "moins de" in t else "nul" if "nul" in t else "victoire")
        cats.setdefault(k,[]).append(p["result"]=="win")
    return " | ".join(f"{k}: {round(sum(v)/len(v)*100)}% ({len(v)}j)"
                      for k,v in cats.items() if len(v)>=2)

def build_pr2(lessons, db=None):
    lb = ""
    if lessons:
        lb = "\n\nLECONS PRECEDENTES:\n" + "\n".join(f"- {l['text']}" for l in lessons[-5:])
    hb = ""
    if db:
        h = winrate_by_type(db)
        if h: hb = f"\n\nHISTORIQUE WIN RATE:\n{h}"
    return (
        "Tu es le Professeur Visionnaire, expert value betting football.\n"
        "FRANCAIS UNIQUEMENT. Toujours proposer UN pari precis.\n\n"
        "ANALYSE:\n"
        "1. Meteo: pluie forte/vent>40km/h → under 2.5 buts\n"
        "2. Forme recente + blessures mentionnees\n"
        "3. Value: ta proba estimee > proba implicite cotes = BET\n"
        "4. Type de pari optimal selon les donnees\n\n"
        "TYPES: Victoire [equipe] / Match nul / BTTS Oui / BTTS Non / "
        "Plus de 2.5 buts / Moins de 2.5 buts / Double chance / Handicap -1\n\n"
        "CONFIANCE reelle (pas de valeur ronde comme 70 ou 75):\n"
        "58-65=incertain | 66-74=bon signal | 75-83=fort | 84-92=exceptionnel\n\n"
        "JSON UNIQUEMENT en francais:\n"
        "{\n"
        "  \"pari\": \"Victoire Napoli ou BTTS Oui ou Plus de 2.5 buts\",\n"
        "  \"confiance\": <58-92>,\n"
        "  \"mise_pct\": <1 si <65, 2 si 65-70, 3 si 71-77, 4 si 78-84, 5 si >84>,\n"
        "  \"risque\": \"risque principal specifique\",\n"
        "  \"resume\": \"3 phrases basees sur les donnees reelles\"\n"
        "}" + lb + hb
    )

def parse_verdict(text: str) -> dict:
    default = {"pari":"Analyse en cours","conf":65,"mp":2,"risque":"","resume":""}
    if not text: return default
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```",t)
        if m: t = m.group(1).strip()
    try:
        jm = re.search(r'\{[\s\S]*?"pari"[\s\S]*?\}',t)
        if jm: t = jm.group(0)
        d = json.loads(t)
        pari   = str(d.get("pari","")).strip()
        conf   = int(d.get("confiance",d.get("conf",65)))
        mp     = int(d.get("mise_pct",d.get("mp",2)))
        risque = str(d.get("risque","")).strip()
        resume = str(d.get("resume","")).strip()
        conf = min(92,max(58,conf))
        mp   = min(5,max(1,mp))
        # Nettoyage pari
        pari = re.sub(r'[\w\s]+ vs [\w\s]+\s*[:\-]\s*','',pari,flags=re.IGNORECASE).strip()
        pari = pari.replace("Victory ","Victoire ").replace("Win ","Victoire ")
        if pari and len(pari.split())<=3 and not any(w in pari.lower() for w in
            ["victoire","btts","plus","moins","nul","handicap","double"]):
            pari = "Victoire " + pari
        if pari and pari[0].islower(): pari = pari[0].upper()+pari[1:]
        log.info(f"Verdict OK — {pari[:40]} conf={conf}")
        return {"pari":pari,"conf":conf,"mp":mp,"risque":risque,"resume":resume}
    except Exception as e:
        log.warning(f"JSON parse failed: {e}")
        def g(rx,fb=""):
            m = re.search(rx,text,re.IGNORECASE|re.MULTILINE)
            return m.group(1).strip() if m else fb
        pari = g(r'^PARI\s*:\s*(.+)$',"Analyse en cours")
        try: conf = min(92,max(58,int(g(r'^CONFIANCE\s*:\s*(\d+)',"65"))))
        except: conf=65
        try: mp = min(5,max(1,int(g(r'^MISE_PCT\s*:\s*(\d+)',"2"))))
        except: mp=2
        return {"pari":pari,"conf":conf,"mp":mp,
                "risque":g(r'^RISQUE\s*:\s*(.+)$',""),
                "resume":g(r'^RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|\Z)',"").strip()}

# ── ANALYSE UN MATCH ──────────────────────────────────────────────────────────
async def analyze_match(match, context, weather, lessons, pcb, db=None):
    def prob(c):
        try: return round(1/float(c)*100,1)
        except: return "?"
    ch = match.get("cote_home","?")
    cd = match.get("cote_draw","?")
    ca = match.get("cote_away","?")
    bk = match.get("bookmaker","?")

    base = (
        f"MATCH: {match['home']} vs {match['away']}\n"
        f"Competition: {match['competition']} | {match['heure']}\n\n"
        f"METEO: {weather}\n\n"
        f"COTES {bk.upper()} EN DIRECT:\n"
        f"{match['home']}: {ch} (proba {prob(ch)}%) | "
        f"Nul: {cd} (proba {prob(cd)}%) | "
        f"{match['away']}: {ca} (proba {prob(ca)}%)\n\n"
        f"CONTEXTE SPORTIF:\n{context}"
    )

    AGENTS[8]["s"] = build_pr2(lessons, db)
    reports = {}

    for ag in AGENTS[:6]:
        await pcb(ag["id"],"run")
        try: reports[ag["id"]] = await call_groq(ag["s"], base+"\n\nAnalyse 80 mots.", 220)
        except RuntimeError as e: reports[ag["id"]] = str(e); log.error(f"Agent {ag['n']}: {e}")
        await pcb(ag["id"],"done")

    all_r = "\n\n".join(f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports[AGENTS[i]['id']]}" for i in range(6))

    await pcb("juge","run")
    try: reports["juge"] = await call_groq(AGENTS[6]["s"],base+"\n\nRAPPORTS:\n"+all_r+"\n\nSynthese.",280)
    except RuntimeError as e: reports["juge"]=str(e)
    await pcb("juge","done")

    await pcb("pr1","run")
    try: reports["pr1"] = await call_groq(AGENTS[7]["s"],base+"\n\nJUGE:\n"+reports["juge"]+"\n\nCorrige.",220)
    except RuntimeError as e: reports["pr1"]=str(e)
    await pcb("pr1","done")

    await pcb("pr2","run")
    try:
        reports["pr2"] = await call_groq(
            AGENTS[8]["s"],
            base+"\n\nJUGE:\n"+reports["juge"]+"\n\nPRAGMATIQUE:\n"+reports["pr1"]+
            f"\n\nEquipes: '{match['home']}' vs '{match['away']}'. JSON uniquement.",
            420
        )
    except RuntimeError as e: reports["pr2"]=str(e)
    await pcb("pr2","done")

    return {"match":match,"reports":reports,"verdict":parse_verdict(reports.get("pr2",""))}

# ── BARRE DE PROGRESSION ──────────────────────────────────────────────────────
def bar(pct,size=10):
    f = round(pct/(100/size))
    return "█"*f+"░"*(size-f)

def build_progress(i,total,mname,comp,states,pct):
    def line(aid,emoji,name):
        s=states.get(aid,"wait")
        ic="✅" if s=="done" else "⚡" if s=="run" else "⏳"
        return f"{emoji} {name:<18} {ic}"
    return "\n".join([
        f"🔬 *Match {i+1}/{total}*  —  {mname}",
        f"🏆 {comp}",f"`{bar(pct)}  {pct}%`","",
        line("tact","🧠","Tacticien"),line("stat","📊","Statisticien"),
        line("doc","🏃","Medecin"),line("scout","🧓","L'Ancien"),
        line("mkt","💰","Marche"),line("psy","🎭","Psychologue"),
        line("juge","⚖️","Juge"),line("pr1","🎓","Prof Pragma"),
        line("pr2","🔭","Prof Vision"),
    ])

def fmt_pick(rank, pick):
    medals=["🥇","🥈","🥉","4️⃣","5️⃣"]
    medal = medals[rank-1] if rank<=5 else f"#{rank}"
    home  = pick.get("home","?"); away  = pick.get("away","?")
    comp  = pick.get("comp","");  heure = pick.get("heure","")
    pari  = pick.get("pari","—"); conf  = pick.get("conf",65)
    bk    = pick.get("bookmaker",""); ch = pick.get("cote_home")
    cd    = pick.get("cote_draw");    ca = pick.get("cote_away")
    risque= pick.get("risque","");   resume=pick.get("resume","")
    def prob(c):
        try: return round(1/float(c)*100,1)
        except: return "?"
    ci = "🔥" if conf>=80 else "✅" if conf>=70 else "👍"
    lines=[
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}"+(f"  ⏰ {heure}" if heure else ""),
        "━━━━━━━━━━━━━━━━━━━━━","",
        f"🎯 *PARI : {pari}*","",
        f"📊 Confiance : `{bar(conf)}` {ci} *{conf}%*",
    ]
    if ch:
        lines+=[
            "",f"📈 *Cotes {bk.title()} :*",
            f"{home}: *{ch}* ({prob(ch)}%) | Nul: *{cd}* | {away}: *{ca}* ({prob(ca)}%)",
        ]
    if resume: lines+=["",f"💡 *Analyse :*",f"{resume}"]
    if risque: lines+=["",f"⚠️ *Risque :* {risque}"]
    return "\n".join(lines)

# ── SCAN ──────────────────────────────────────────────────────────────────────
async def run_scan(ctx, force=False):
    bot = ctx.bot
    db  = load_db()
    ti  = get_target()

    if not force and ti["key"] in db.get("scans",{}):
        pks = db["scans"][ti["key"]].get("picks",[])
        if pks:
            await bot.send_message(
                chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
                text=(f"💾 *Scan du {ti['key']} deja effectue*\n\n"
                      f"{len(pks)} paris en memoire.\n"
                      f"/resultats pour les voir\n"
                      f"/scan force pour forcer un nouveau scan")
            )
            return

    msg = await bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text=(f"⚽ *ORACLE — SCAN DU JOUR*\n☀️ {ti['label']}\n\n"
              f"🔍 Recuperation matchs + cotes en direct...\n━━━━━━━━━━━━━━━━━━━━━")
    )

    try:
        matches = await fetch_matches(ti["iso_date"], ti["label"])
    except RuntimeError as e:
        await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg.message_id,
                                    text=f"❌ *{e}*", parse_mode=ParseMode.MARKDOWN)
        return

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
            text=f"⚽ *ORACLE*\n\n❌ Aucun match trouve pour {ti['label']}."
        )
        return

    to_analyze = matches[:10]
    await bot.edit_message_text(
        chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
        text=(f"⚽ *ORACLE — {ti['label']}*\n\n"
              f"✅ *{len(matches)} matchs* avec cotes en direct\n"
              f"🔬 Analyse par 9 agents Groq...\n\n━━━━━━━━━━━━━━━━━━━━━")
    )

    lessons = db.get("lessons",[])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition","")
        pmsg  = await bot.send_message(
            chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
            text=build_progress(i,len(to_analyze),mname,comp,{},0)
        )
        states={ag["id"]:"wait" for ag in AGENTS}
        steps=[0]

        async def pcb(aid,status,_s=states,_st=steps,_m=pmsg,
                      _n=mname,_c=comp,_i=i,_t=len(to_analyze)):
            if status=="run": _s[aid]="run"
            elif status=="done": _s[aid]="done"; _st[0]+=1
            pct=round(_st[0]/9*100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,message_id=_m.message_id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=build_progress(_i,_t,_n,_c,_s,pct)
                )
            except: pass

        try:
            ctx_text, weather = await asyncio.gather(
                fetch_context(match), fetch_weather(match["home"]), return_exceptions=True
            )
            if isinstance(ctx_text,Exception): raise RuntimeError(f"ERREUR contexte: {ctx_text}")
            if isinstance(weather,Exception): weather="Meteo indisponible"
        except RuntimeError as e:
            await bot.edit_message_text(chat_id=CHAT_ID,message_id=pmsg.message_id,text=f"❌ {e}")
            log.error(str(e)); continue

        try:
            result = await analyze_match(match,ctx_text,weather,lessons,pcb,db)
            results.append(result)
            v = result["verdict"]
            await bot.edit_message_text(
                chat_id=CHAT_ID,message_id=pmsg.message_id,parse_mode=ParseMode.MARKDOWN,
                text=(f"✅ *{i+1}/{len(to_analyze)} — {mname}*\n\n"
                      f"`{'█'*10}  100%`\n\n"
                      f"🎯 *{v['pari']}*\n📊 Confiance : {v['conf']}%")
            )
        except RuntimeError as e:
            await bot.edit_message_text(
                chat_id=CHAT_ID,message_id=pmsg.message_id,text=f"❌ ERREUR {mname}: {e}")
            log.error(f"Erreur {mname}: {e}")
        await asyncio.sleep(1)

    if not results:
        await bot.send_message(chat_id=CHAT_ID,text="❌ Aucune analyse completee."); return

    # Tri + deduplication
    results.sort(key=lambda x:x["verdict"]["conf"],reverse=True)
    seen,top5=[],[]
    for r in results:
        p=r["verdict"].get("pari","").lower()
        pt=("btts" if "btts" in p else "over" if "plus de" in p else
            "under" if "moins de" in p else "nul" if "nul" in p
            else f"vic_{r['match']['home'][:6]}")
        if seen.count(pt)<2: top5.append(r); seen.append(pt)
        if len(top5)>=5: break
    if not top5: top5=results[:5]

    entry={
        "date_key":ti["key"],"date_label":ti["label"],
        "timestamp":datetime.now().isoformat(),
        "picks":[{
            "home":r["match"]["home"],"away":r["match"]["away"],
            "comp":r["match"].get("competition",""),
            "heure":r["match"].get("heure",""),
            "bookmaker":r["match"].get("bookmaker",""),
            "cote_home":r["match"].get("cote_home"),
            "cote_draw":r["match"].get("cote_draw"),
            "cote_away":r["match"].get("cote_away"),
            "pari":r["verdict"]["pari"],"conf":r["verdict"]["conf"],
            "mp":r["verdict"]["mp"],"risque":r["verdict"]["risque"],
            "resume":r["verdict"]["resume"],"result":None,
        } for r in top5]
    }
    db["scans"][ti["key"]]=entry
    save_db(db)

    await bot.send_message(
        chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,
        text=f"🏆 *TOP {len(top5)} PARIS — {ti['label']}*\n━━━━━━━━━━━━━━━━━━━━━"
    )
    await asyncio.sleep(0.5)

    for rank,r in enumerate(top5,1):
        pick={
            "home":r["match"]["home"],"away":r["match"]["away"],
            "comp":r["match"].get("competition",""),
            "heure":r["match"].get("heure",""),
            "bookmaker":r["match"].get("bookmaker",""),
            "cote_home":r["match"].get("cote_home"),
            "cote_draw":r["match"].get("cote_draw"),
            "cote_away":r["match"].get("cote_away"),
            **r["verdict"],
        }
        kbd=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",     callback_data=f"res:{ti['key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS",    callback_data=f"res:{ti['key']}:{rank-1}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{ti['key']}:{rank-1}:cancel"),
        ]])
        await bot.send_message(
            chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,
            text=fmt_pick(rank,pick),reply_markup=kbd
        )
        await asyncio.sleep(0.5)

    await bot.send_message(
        chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,
        text="✅ *Scan termine !*\n\nWIN / LOSS / ANNULER apres chaque match.\n🧬 L'IA apprend de chaque resultat\n\n/stats  /resultats"
    )

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id!=CHAT_ID: return
    ti=get_target()
    kbd=InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner les matchs du jour",callback_data="launch_scan")]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"9 agents Groq · Cotes Winamax/Bet365 en direct · Auto-apprentissage\n\n"
        f"*Commandes :*\n/scan — Scan du jour\n/scan force — Forcer nouveau scan\n"
        f"/stats — Statistiques\n/resultats — Paris en attente\n\n"
        f"Il est {ti['hour']}h · Scan optimal a 10h",
        parse_mode=ParseMode.MARKDOWN,reply_markup=kbd
    )

async def cmd_scan(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id!=CHAT_ID: return
    force=len(context.args)>0 and context.args[0].lower()=="force"
    await run_scan(context,force=force)

async def cmd_stats(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id!=CHAT_ID: return
    db=load_db()
    allp=[p for s in db.get("scans",{}).values() for p in s.get("picks",[])]
    dec=[p for p in allp if p.get("result") in ["win","loss"]]
    wins=[p for p in dec if p["result"]=="win"]
    wr=round(len(wins)/len(dec)*100) if dec else 0
    nb=len(db.get("lessons",[]))
    lvl="Expert ⭐" if nb>=20 else "Bon 🔥" if nb>=10 else "En cours 📈"
    wt=winrate_by_type(db)
    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joues : *{len(dec)}*\n✅ Gagnes : *{len(wins)}*\n"
        f"❌ Perdus : *{len(dec)-len(wins)}*\n📈 Win rate : *{wr}%*\n\n"
        f"🧬 Lecons : *{nb}*  |  Niveau : *{lvl}*"
        +(f"\n\n📊 *Par type :*\n{wt}" if wt else ""),
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_resultats(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id!=CHAT_ID: return
    db=load_db()
    pnd=[(dk,i,p,s["date_label"]) for dk,s in db.get("scans",{}).items()
         for i,p in enumerate(s.get("picks",[])) if p.get("result") is None]
    if not pnd:
        await update.message.reply_text("✅ Tous les resultats saisis !"); return
    await update.message.reply_text(f"⏳ *{len(pnd)} paris en attente*",parse_mode=ParseMode.MARKDOWN)
    for dk,idx,pick,dlabel in pnd[:10]:
        kbd=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",     callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS",    callback_data=f"res:{dk}:{idx}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel"),
        ]])
        await update.message.reply_text(
            f"📅 {dlabel}\n⚽ *{pick['home']} vs {pick['away']}*\n🎯 {pick['pari']} ({pick['conf']}%)",
            parse_mode=ParseMode.MARKDOWN,reply_markup=kbd
        )
        await asyncio.sleep(0.3)

async def handle_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.message.chat_id!=CHAT_ID: return
    data=q.data

    if data=="launch_scan":
        await run_scan(context,force=False); return

    if data.startswith("res:"):
        _,dk,idx_s,result=data.split(":")
        idx=int(idx_s)
        db=load_db()
        scan=db.get("scans",{}).get(dk)
        if not scan or idx>=len(scan.get("picks",[])): return
        pick=scan["picks"][idx]
        prev=pick.get("result")

        if result=="cancel":
            pick["result"]="cancelled"
            save_db(db)
            try:
                await q.edit_message_text(
                    text=q.message.text+"\n\n🚫 *Annule — non compte dans les stats*",
                    parse_mode=ParseMode.MARKDOWN,reply_markup=None)
            except: pass
            return

        pick["result"]=None if prev==result else result
        save_db(db)

        if pick["result"]:
            ic="✅" if pick["result"]=="win" else "❌"
            try:
                await q.edit_message_text(
                    text=q.message.text+f"\n\n{ic} *{pick['result'].upper()} enregistre*",
                    parse_mode=ParseMode.MARKDOWN,reply_markup=None)
            except: pass
            if not prev: await trigger_learning(pick,db,context)
        else:
            kbd=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ WIN",     callback_data=f"res:{dk}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS",    callback_data=f"res:{dk}:{idx}:loss"),
                InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel"),
            ]])
            try: await q.edit_message_reply_markup(reply_markup=kbd)
            except: pass

async def trigger_learning(pick,db,context):
    try:
        won=pick["result"]=="win"
        txt=await call_groq(
            "Auto-amelioration paris sportifs. Francais, concis, actionnable.",
            f"Pari {'GAGNE' if won else 'PERDU'}:\n"
            f"Match: {pick['home']} vs {pick['away']}\n"
            f"Pari: {pick['pari']} | Confiance: {pick['conf']}%\n\n"
            f"1 lecon de 2 phrases MAX pour ameliorer les prochaines analyses.",150
        )
        lesson={"id":int(datetime.now().timestamp()),
                "date":datetime.now().strftime("%d/%m/%Y"),
                "match":f"{pick['home']} vs {pick['away']}",
                "pari":pick["pari"],"result":pick["result"],"text":txt.strip()}
        db.setdefault("lessons",[])
        db["lessons"].append(lesson)
        db["lessons"]=db["lessons"][-50:]
        save_db(db)
        ic="🟢" if won else "🔴"
        await context.bot.send_message(
            chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,
            text=f"🧬 *Lecon apprise !*\n\n{ic} {pick['home']} vs {pick['away']} — {'WIN' if won else 'LOSS'}\n\n💡 {txt.strip()}"
        )
    except Exception as e: log.error(f"Learning: {e}")

async def remind_yesterday(ctx):
    db=load_db()
    yd=(datetime.now()-timedelta(days=1)).strftime("%d/%m/%Y")
    scan=db.get("scans",{}).get(yd)
    if not scan: return
    pnd=[p for p in scan.get("picks",[]) if p.get("result") is None]
    if not pnd: return
    await ctx.bot.send_message(
        chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,
        text=f"⏰ *Resultats en attente — {yd}*\n\n{len(pnd)} paris sans resultat !\n/resultats"
    )

async def auto_scan(ctx):
    await run_scan(ctx,force=False)

def main():
    if not TOKEN:        log.error("TELEGRAM_TOKEN manquant"); return
    if not GROQ_KEYS:   log.error("GROQ_KEYS manquantes"); return
    if not ODDSPAPI_KEY: log.error("ODDSPAPI_KEY manquante"); return

    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq=app.job_queue
    jq.run_daily(auto_scan,        time=datetime.strptime(f"{SCAN_HOUR:02d}:00","%H:%M").time(),name="scan")
    jq.run_daily(remind_yesterday, time=datetime.strptime(f"{(SCAN_HOUR+1)%24:02d}:00","%H:%M").time(),name="remind")

    log.info(f"Oracle Bot demarre — {len(GROQ_KEYS)} cles Groq — scan auto {SCAN_HOUR}h")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
