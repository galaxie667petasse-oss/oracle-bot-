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
FOOTBALL_KEY = os.getenv("FOOTBALL_KEY", "")
SCAN_HOUR    = int(os.getenv("SCAN_HOUR", "9"))
BANKROLL_DEF = float(os.getenv("BANKROLL", "100"))
DB_FILE      = Path("oracle_db.json")
GROQ_IDX     = 0

def next_key():
    global GROQ_IDX
    if not GROQ_KEYS: raise ValueError("Pas de cle Groq")
    k = GROQ_KEYS[GROQ_IDX % len(GROQ_KEYS)]
    GROQ_IDX += 1
    return k

def load_db():
    if DB_FILE.exists():
        try: return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except: pass
    return {"scans": {}, "lessons": [], "bankroll": BANKROLL_DEF}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def get_target():
    now = datetime.now()
    h = now.hour
    d = now + timedelta(days=1) if h >= 21 else now
    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS  = ["janvier","fevrier","mars","avril","mai","juin",
              "juillet","aout","septembre","octobre","novembre","decembre"]
    return {
        "label":    f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month-1]} {d.year}",
        "key":      d.strftime("%d/%m/%Y"),
        "api_date": d.strftime("%Y-%m-%d"),
        "tmrw":     h >= 21,
        "hour":     h,
    }

# ── GROQ VIA AIOHTTP (pas de SDK pour eviter bug proxies) ─────────────────────
async def call_groq(system: str, user: str, max_tokens: int = 500) -> str:
    key = next_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role":"system","content":system}, {"role":"user","content":user}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    for attempt in range(4):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 429:
                        await asyncio.sleep((attempt+1)*6)
                        continue
                    if resp.status != 200:
                        txt = await resp.text()
                        raise RuntimeError(f"Groq {resp.status}: {txt[:200]}")
                    data = await resp.json()
                    result = data["choices"][0]["message"]["content"].strip()
                    await asyncio.sleep(max(0.3, 0.8/max(1, len(GROQ_KEYS))))
                    return result
        except RuntimeError: raise
        except Exception as e:
            log.warning(f"Groq attempt {attempt+1}: {e}")
            if attempt == 3: raise
            await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

# ── API-FOOTBALL ──────────────────────────────────────────────────────────────
LEAGUES = [
    (2,   "Champions League"),
    (3,   "Europa League"),
    (848, "Conference League"),
    (61,  "Ligue 1"),
    (39,  "Premier League"),
    (140, "La Liga"),
    (135, "Serie A"),
    (78,  "Bundesliga"),
    (62,  "Ligue 2"),
    (40,  "Championship"),
    (88,  "Eredivisie"),
    (94,  "Primeira Liga"),
    (203, "Super Lig"),
]
LEAGUE_IDS   = {l[0] for l in LEAGUES}
LEAGUE_NAMES = {l[0]: l[1] for l in LEAGUES}
LEAGUE_PRIO  = {l[0]: i for i, l in enumerate(LEAGUES)}

async def api_get(session, url, headers):
    """Appel API-Football avec gestion erreurs."""
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        log.warning(f"API call failed {url}: {e}")
    return {}

def format_form(results: list) -> str:
    """Formate les 5 derniers resultats en W/D/L."""
    if not results:
        return "Inconnu"
    symbols = []
    for r in results[-5:]:
        goals_for     = r.get("goals", {}).get("for", 0) or 0
        goals_against = r.get("goals", {}).get("against", 0) or 0
        if goals_for > goals_against:   symbols.append("V")
        elif goals_for == goals_against: symbols.append("N")
        else:                            symbols.append("D")
    return " ".join(symbols)

def format_goals_avg(results: list) -> tuple:
    """Retourne (buts marqués moy, buts encaissés moy) sur 5 matchs."""
    if not results:
        return (0, 0)
    last5 = results[-5:]
    scored   = sum(r.get("goals",{}).get("for",0) or 0 for r in last5)
    conceded = sum(r.get("goals",{}).get("against",0) or 0 for r in last5)
    n = len(last5)
    return (round(scored/n, 1), round(conceded/n, 1))

async def fetch_team_stats(session, headers, team_id: int, league_id: int, season: int = 2025) -> dict:
    """Recupere forme + stats d'une equipe."""
    data = await api_get(session,
        f"https://v3.football.api-sports.io/teams/statistics?team={team_id}&league={league_id}&season={season}",
        headers)
    stats = data.get("response", {})
    if not stats:
        return {}

    fixtures = stats.get("fixtures", {})
    goals    = stats.get("goals", {})
    form_str = stats.get("form", "") or ""

    # Forme sur les 5 derniers
    recent_form = form_str[-5:] if form_str else "?????"
    played = fixtures.get("played", {}).get("total", 0) or 0
    wins   = fixtures.get("wins",   {}).get("total", 0) or 0
    draws  = fixtures.get("draws",  {}).get("total", 0) or 0
    losses = fixtures.get("loses",  {}).get("total", 0) or 0

    goals_for_avg     = goals.get("for",     {}).get("average", {}).get("total", "?")
    goals_against_avg = goals.get("against", {}).get("average", {}).get("total", "?")

    # Forme domicile/exterieur
    home_wins = fixtures.get("wins",  {}).get("home", 0) or 0
    home_played = fixtures.get("played", {}).get("home", 0) or 0
    away_wins = fixtures.get("wins",  {}).get("away", 0) or 0
    away_played = fixtures.get("played", {}).get("away", 0) or 0

    return {
        "form":              recent_form,
        "played":            played,
        "wins":              wins,
        "draws":             draws,
        "losses":            losses,
        "goals_for_avg":     goals_for_avg,
        "goals_against_avg": goals_against_avg,
        "home_win_rate":     f"{home_wins}/{home_played}" if home_played else "?",
        "away_win_rate":     f"{away_wins}/{away_played}" if away_played else "?",
    }

async def fetch_h2h(session, headers, home_id: int, away_id: int) -> str:
    """Recupere les 5 derniers H2H."""
    data = await api_get(session,
        f"https://v3.football.api-sports.io/fixtures/headtohead?h2h={home_id}-{away_id}&last=5",
        headers)
    fixtures = data.get("response", [])
    if not fixtures:
        return "Pas de H2H disponible"

    lines = []
    for f in fixtures[-5:]:
        home  = f.get("teams", {}).get("home", {}).get("name", "?")
        away  = f.get("teams", {}).get("away", {}).get("name", "?")
        gh    = f.get("goals", {}).get("home", "?")
        ga    = f.get("goals", {}).get("away", "?")
        date  = f.get("fixture", {}).get("date", "")[:10]
        lines.append(f"{date}: {home} {gh}-{ga} {away}")
    return " | ".join(lines)

async def fetch_standings_position(session, headers, team_id: int, league_id: int, season: int = 2025) -> str:
    """Recupere la position au classement."""
    data = await api_get(session,
        f"https://v3.football.api-sports.io/standings?league={league_id}&season={season}",
        headers)
    standings = data.get("response", [])
    for group in standings:
        for league in group.get("league", {}).get("standings", []):
            for team in league:
                if team.get("team", {}).get("id") == team_id:
                    rank   = team.get("rank", "?")
                    pts    = team.get("points", "?")
                    played = team.get("all", {}).get("played", "?")
                    gd     = team.get("goalsDiff", "?")
                    return f"#{rank} ({pts}pts, {played}J, GD:{gd})"
    return "Position inconnue"

async def enrich_match(session, headers, match: dict) -> dict:
    """Enrichit un match avec vraies stats API-Football."""
    home_id   = match.get("home_id")
    away_id   = match.get("away_id")
    league_id = match.get("league_id")

    if not home_id or not away_id or not league_id:
        return match

    log.info(f"Enrichissement: {match['home']} vs {match['away']}")

    # Lancer les requetes en parallele
    home_stats_task  = fetch_team_stats(session, headers, home_id, league_id)
    away_stats_task  = fetch_team_stats(session, headers, away_id, league_id)
    h2h_task         = fetch_h2h(session, headers, home_id, away_id)
    home_pos_task    = fetch_standings_position(session, headers, home_id, league_id)
    away_pos_task    = fetch_standings_position(session, headers, away_id, league_id)

    home_stats, away_stats, h2h, home_pos, away_pos = await asyncio.gather(
        home_stats_task, away_stats_task, h2h_task, home_pos_task, away_pos_task,
        return_exceptions=True
    )

    # Gerer les exceptions
    if isinstance(home_stats, Exception): home_stats = {}
    if isinstance(away_stats, Exception): away_stats = {}
    if isinstance(h2h,        Exception): h2h = "H2H indisponible"
    if isinstance(home_pos,   Exception): home_pos = "?"
    if isinstance(away_pos,   Exception): away_pos = "?"

    match["home_stats"]  = home_stats
    match["away_stats"]  = away_stats
    match["h2h"]         = h2h
    match["home_pos"]    = home_pos
    match["away_pos"]    = away_pos
    return match

def build_match_context(match: dict) -> str:
    """Construit le contexte complet avec vraies stats pour les agents."""
    home = match["home"]
    away = match["away"]
    comp = match.get("competition", "")
    hs   = match.get("home_stats", {})
    as_  = match.get("away_stats", {})
    h2h  = match.get("h2h", "Pas de H2H")
    hp   = match.get("home_pos", "?")
    ap   = match.get("away_pos", "?")
    ch   = match.get("cote_home", "?")
    cd   = match.get("cote_draw", "?")
    ca   = match.get("cote_away", "?")

    ctx = f"""MATCH: {home} vs {away}
Competition: {comp} | Heure: {match.get('heure','?')}h

=== {home} (DOMICILE) ===
Classement: {hp}
Forme recente: {hs.get('form', '?????')}
Bilan saison: {hs.get('wins','?')}V {hs.get('draws','?')}N {hs.get('losses','?')}D sur {hs.get('played','?')} matchs
Buts marques/encaisses (moy): {hs.get('goals_for_avg','?')} / {hs.get('goals_against_avg','?')}
A domicile: {hs.get('home_win_rate','?')} victoires

=== {away} (EXTERIEUR) ===
Classement: {ap}
Forme recente: {as_.get('form', '?????')}
Bilan saison: {as_.get('wins','?')}V {as_.get('draws','?')}N {as_.get('losses','?')}D sur {as_.get('played','?')} matchs
Buts marques/encaisses (moy): {as_.get('goals_for_avg','?')} / {as_.get('goals_against_avg','?')}
A l'exterieur: {as_.get('away_win_rate','?')} victoires

=== HISTORIQUE H2H (5 derniers) ===
{h2h}

=== COTES MARCHE ===
Domicile ({home}): {ch} | Nul: {cd} | Exterieur ({away}): {ca}
Probabilite implicite: Dom {round(1/float(ch)*100,1) if ch and ch!='?' else '?'}% | Nul {round(1/float(cd)*100,1) if cd and cd!='?' else '?'}% | Ext {round(1/float(ca)*100,1) if ca and ca!='?' else '?'}%"""

    return ctx

async def fetch_matches(label: str, api_date: str) -> list:
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key":  FOOTBALL_KEY,
    }
    paris_tz = pytz.timezone("Europe/Paris")
    matches  = []

    async with aiohttp.ClientSession() as session:
        # 1. Recuperer les matchs du jour
        try:
            async with session.get(
                f"https://v3.football.api-sports.io/fixtures?date={api_date}&status=NS",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    log.error(f"API-Football {resp.status}")
                    return []
                data = await resp.json()
        except Exception as e:
            log.error(f"fetch_matches: {e}")
            return []

        fixtures = data.get("response", [])
        log.info(f"API-Football: {len(fixtures)} matchs bruts")

        for fix in fixtures:
            lid = fix.get("league", {}).get("id")
            if lid not in LEAGUE_IDS:
                continue
            teams   = fix.get("teams", {})
            fixture = fix.get("fixture", {})
            home_id = teams.get("home", {}).get("id")
            away_id = teams.get("away", {}).get("id")
            home    = teams.get("home", {}).get("name", "?")
            away    = teams.get("away", {}).get("name", "?")
            comp    = LEAGUE_NAMES.get(lid, "?")
            heure   = ""
            kickoff = fixture.get("date", "")
            if kickoff:
                try:
                    dt    = datetime.fromisoformat(kickoff.replace("Z","+00:00"))
                    heure = dt.astimezone(paris_tz).strftime("%H:%M")
                except: pass

            matches.append({
                "home": home, "away": away, "competition": comp,
                "date": label, "heure": heure,
                "home_id": home_id, "away_id": away_id, "league_id": lid,
                "cote_home": None, "cote_draw": None, "cote_away": None,
                "_prio": LEAGUE_PRIO.get(lid, 99),
            })

        matches.sort(key=lambda m: m["_prio"])
        matches = matches[:10]
        log.info(f"Matchs selectionnes: {len(matches)}")

        # 2. Enrichir avec vraies stats (cotes + form + H2H + standings)
        # D'abord les cotes
        for m in matches:
            try:
                raw = await call_groq(
                    "Expert football. JSON uniquement.",
                    f"Estime les cotes Betclic pour {m['home']} vs {m['away']} ({m['competition']}).\n"
                    f'JSON: {{"cote_home":1.85,"cote_draw":3.40,"cote_away":4.20}}',
                    80
                )
                raw = raw.strip()
                if "```" in raw:
                    r2 = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                    if r2: raw = r2.group(1).strip()
                p = json.loads(raw)
                m["cote_home"] = p.get("cote_home")
                m["cote_draw"] = p.get("cote_draw")
                m["cote_away"] = p.get("cote_away")
            except: pass

        # Puis les stats reelles en parallele
        enrich_tasks = [enrich_match(session, headers, m) for m in matches]
        enriched = await asyncio.gather(*enrich_tasks, return_exceptions=True)
        matches = [m if not isinstance(m, Exception) else matches[i]
                   for i, m in enumerate(enriched)]

    return matches

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {"id":"tact",  "n":"Tacticien",    "e":"🧠",
     "s":"Expert tacticien football. Analyse les formations, le pressing, les transitions et les duels. Base-toi sur les stats reelles fournies. 90 mots max."},
    {"id":"stat",  "n":"Statisticien", "e":"📊",
     "s":"Analyste statistique football. Analyse la forme recente, le H2H, les buts marques/encaisses, les moyennes. Donne des probabilites chiffrees. 90 mots max."},
    {"id":"doc",   "n":"Medecin",      "e":"🏃",
     "s":"Medecin sportif. Analyse la fatigue selon le rythme des matchs, les blessures probables, les rotations attendues. 90 mots max."},
    {"id":"scout", "n":"L'Ancien",     "e":"🧓",
     "s":"Scout legendaire 40 ans. Analyse les patterns caches, les equipes pieges, les tendances historiques H2H. 90 mots max."},
    {"id":"mkt",   "n":"Marche",       "e":"💰",
     "s":"Expert value betting. Calcule la probabilite reelle vs probabilite implicite des cotes. Identifie les value bets. 90 mots max."},
    {"id":"psy",   "n":"Psychologue",  "e":"🎭",
     "s":"Psychologue sport. Analyse les enjeux, la pression, la motivation, l'effet domicile/exterieur. 90 mots max."},
    {"id":"juge",  "n":"Juge",         "e":"⚖️",
     "s":"Juge Arbitre. Synthetise les 6 rapports, identifie le consensus et les divergences. 130 mots max."},
    {"id":"pr1",   "n":"Prof Pragma",  "e":"🎓",
     "s":"Professeur Pragmatique 40 ans. Identifie les failles dans l'analyse, sois realiste et critique. 110 mots max."},
    {"id":"pr2",   "n":"Prof Vision",  "e":"🔭", "s":""},
]

def build_pr2(lessons):
    lesson_block = ""
    if lessons:
        lesson_block = "\n\nLECONS DES PARIS PRECEDENTS (applique-les):\n"
        lesson_block += "\n".join(f"- {l['text']}" for l in lessons[-5:])

    return (
        "Tu es le Professeur Visionnaire, expert en value betting avec 20 ans d'experience.\n"
        "Tu analyses les rapports de 8 experts ET les vraies statistiques du match.\n\n"
        "PROCESSUS D'ANALYSE:\n"
        "1. Regarde les formes recentes (V/N/D des 5 derniers matchs)\n"
        "2. Regarde le H2H - historique entre ces equipes\n"
        "3. Compare buts marques/encaisses des deux equipes\n"
        "4. Calcule si les cotes offrent de la value\n"
        "5. Choisis le MEILLEUR pari selon ces donnees reelles\n\n"
        "TYPES DE PARIS (choisis selon les stats):\n"
        "- Si les deux equipes marquent souvent → BTTS Oui\n"
        "- Si les deux equipes encaissent peu → BTTS Non ou Moins de 2.5 buts\n"
        "- Si les moyennes de buts sont elevees → Plus de 2.5 buts\n"
        "- Si forte domination statistique → Victoire + handicap\n"
        "- Si equipes tres proches → Double chance ou nul\n"
        "- Si favori clair avec value → Victoire directe\n\n"
        "CALCUL CONFIANCE (base sur les donnees reelles):\n"
        "- Forme des 5 derniers: 3V+= fort signal\n"
        "- H2H favorable: +signal\n"
        "- Value dans les cotes: +signal\n"
        "- Equipes proches en stats: -confiance\n\n"
        "RETOURNE UNIQUEMENT CE JSON:\n"
        "{\n"
        '  "pari": "pari precis avec vrais noms equipes",\n'
        '  "confiance": <58-87 calcule selon donnees reelles>,\n'
        '  "mise_pct": <1=conf<65, 2=65-70, 3=71-76, 4=77-82, 5=conf>82>,\n'
        '  "cote_mini": <cote realiste: victoire favori=1.45-1.80, BTTS=1.65-1.90, over/under=1.60-1.95, nul=2.80-3.60>,\n'
        '  "risque": "risque specifique base sur les stats",\n'
        '  "resume": "3 phrases basees sur les vraies stats (forme, H2H, buts)"\n'
        "}" + lesson_block
    )

def parse_verdict(text: str) -> dict:
    default = {"pari":"Voir analyse","conf":65,"mp":2,"cm":1.75,"risque":"","resume":""}
    if not text: return default
    t = text.strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m: t = m.group(1).strip()
    try:
        jm = re.search(r'\{[\s\S]*?"pari"[\s\S]*?\}', t)
        if jm: t = jm.group(0)
        data   = json.loads(t)
        pari   = str(data.get("pari","")).strip()
        conf   = int(data.get("confiance", data.get("conf", 65)))
        mp     = int(data.get("mise_pct", data.get("mp", 2)))
        cm_raw = data.get("cote_mini", data.get("cm", 1.75))
        risque = str(data.get("risque","")).strip()
        resume = str(data.get("resume","")).strip()
        conf = min(87, max(58, conf))
        mp   = min(5,  max(1,  mp))
        try:
            cm = float(str(cm_raw).replace(",","."))
            if cm < 1.10 or cm > 20: cm = 1.75
        except: cm = 1.75
        if not pari or len(pari) < 3: pari = "Voir analyse"
        log.info(f"Verdict JSON OK — {pari[:40]} conf={conf} cm={cm}")
        return {"pari":pari,"conf":conf,"mp":mp,"cm":cm,"risque":risque,"resume":resume}
    except Exception as e:
        log.warning(f"JSON parse failed: {e}")
        def g(rx, fb=""):
            m = re.search(rx, text, re.IGNORECASE|re.MULTILINE)
            return m.group(1).strip() if m else fb
        pari   = g(r'^PARI\s*:\s*(.+)$', "Voir analyse")
        cs     = g(r'^CONFIANCE\s*:\s*(\d+)', "65")
        ms     = g(r'^MISE_PCT\s*:\s*(\d+)', "2")
        cms    = g(r'^COTE[_\s]*MINI\s*:\s*([\d.,]+)', "1.75").replace(",",".")
        risque = g(r'^RISQUE\s*:\s*(.+)$', "")
        resume = g(r'^RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|\Z)', "")
        try: conf = min(87, max(58, int(cs)))
        except: conf = 65
        try: mp = min(5, max(1, int(ms)))
        except: mp = 2
        try:
            cm = float(cms)
            if cm < 1.10 or cm > 20: cm = 1.75
        except: cm = 1.75
        return {"pari":pari,"conf":conf,"mp":mp,"cm":cm,"risque":risque,"resume":resume.strip()}

# ── ANALYSE UN MATCH ──────────────────────────────────────────────────────────
async def analyze_match(match: dict, lessons: list, pcb) -> dict:
    # Contexte complet avec vraies stats
    base = build_match_context(match)
    reports = {}
    AGENTS[8]["s"] = build_pr2(lessons)

    for ag in AGENTS[:6]:
        await pcb(ag["id"], "run")
        try:
            reports[ag["id"]] = await call_groq(
                ag["s"],
                base + "\n\nDonne ton analyse experte basee sur ces vraies statistiques.",
                250
            )
        except Exception as e:
            reports[ag["id"]] = f"Erreur: {e}"
        await pcb(ag["id"], "done")

    all_r = "\n\n".join(
        f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports[AGENTS[i]['id']]}"
        for i in range(6)
    )

    await pcb("juge", "run")
    try:
        reports["juge"] = await call_groq(
            AGENTS[6]["s"],
            base + "\n\nRAPPORTS DES 6 EXPERTS:\n" + all_r + "\n\nSynthese complete.",
            300)
    except Exception as e: reports["juge"] = f"Erreur: {e}"
    await pcb("juge", "done")

    await pcb("pr1", "run")
    try:
        reports["pr1"] = await call_groq(
            AGENTS[7]["s"],
            base + "\n\nJUGE:\n" + reports["juge"] + "\n\nIdentifie les failles et corrige.",
            250)
    except Exception as e: reports["pr1"] = f"Erreur: {e}"
    await pcb("pr1", "done")

    await pcb("pr2", "run")
    try:
        home_name = match['home']
        away_name = match['away']
        reports["pr2"] = await call_groq(
            AGENTS[8]["s"],
            base + "\n\nJUGE:\n" + reports["juge"] +
            "\n\nPRAGMATIQUE:\n" + reports["pr1"] +
            f"\n\nNote: Les equipes sont '{home_name}' (domicile) et '{away_name}' (exterieur).\n"
            "Utilise les VRAIS NOMS dans le champ pari. Retourne UNIQUEMENT le JSON.",
            450
        )
    except Exception as e: reports["pr2"] = f"Erreur: {e}"
    await pcb("pr2", "done")

    return {"match":match, "reports":reports, "verdict":parse_verdict(reports.get("pr2",""))}

# ── UI ────────────────────────────────────────────────────────────────────────
def bar(pct, size=10):
    f = round(pct / (100/size))
    return "█"*f + "░"*(size-f)

def build_progress(i, total, mname, comp, states, pct):
    def line(aid, emoji, name):
        s = states.get(aid, "wait")
        ic = "✅" if s=="done" else "⚡" if s=="run" else "⏳"
        return f"{emoji} {name:<18} {ic}"
    return "\n".join([
        f"🔬 *Match {i+1}/{total}*  —  {mname}",
        f"🏆 {comp}",
        f"`{bar(pct)}  {pct}%`",
        "",
        line("tact",  "🧠","Tacticien"),
        line("stat",  "📊","Statisticien"),
        line("doc",   "🏃","Medecin"),
        line("scout", "🧓","L'Ancien"),
        line("mkt",   "💰","Marche"),
        line("psy",   "🎭","Psychologue"),
        line("juge",  "⚖️","Juge"),
        line("pr1",   "🎓","Prof Pragma"),
        line("pr2",   "🔭","Prof Vision"),
    ])

def fmt_pick(rank, pick, bankroll):
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    medal  = medals[rank-1] if rank <= 5 else f"#{rank}"
    home   = pick.get("home","?")
    away   = pick.get("away","?")
    comp   = pick.get("comp","")
    heure  = pick.get("heure","")
    pari   = pick.get("pari","—")
    # Remplacer generiques
    pari = pari.replace(" X", f" {home}").replace(" Y", f" {away}")
    pari = re.sub(r"(?i)victoire domicile", f"Victoire {home}", pari)
    pari = re.sub(r"(?i)victoire exterieur", f"Victoire {away}", pari)
    conf   = pick.get("conf", 65)
    mp     = pick.get("mp", 2)
    cm     = pick.get("cm", None)
    risque = pick.get("risque","")
    resume = pick.get("resume","")
    mise   = round(bankroll * mp / 100, 2)
    gain   = round(mise * cm, 2) if cm else None
    ben    = round(gain - mise, 2) if gain else None
    conf_icon = "🔥" if conf >= 78 else "✅" if conf >= 68 else "👍"

    lines = [
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}" + (f"  ⏰ {heure}" if heure else ""),
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 *PARI : {pari}*",
        "",
        f"📊 Confiance : `{bar(conf)}` {conf_icon} *{conf}%*",
        f"💰 Mise : *{mise}€*  ({mp}% bankroll)",
    ]
    if cm:
        lines += [
            f"⚡ Cote minimum : *{cm}*",
            f"🎁 Si gagne : *{gain}€*  (profit +{ben}€)",
        ]
    if resume:
        lines += ["", "💡 *Analyse basee sur les stats :*", f"{resume}"]
    if risque:
        lines += ["", f"⚠️ *Risque :* {risque}"]
    return "\n".join(lines)

# ── SCAN ──────────────────────────────────────────────────────────────────────
async def run_scan(context, bankroll):
    bot = context.bot
    db  = load_db()
    ti  = get_target()
    pfx = "DEMAIN" if ti["tmrw"] else "AUJOURD'HUI"
    ico = "🌙" if ti["tmrw"] else "☀️"

    msg = await bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text=f"⚽ *ORACLE — SCAN {pfx}*\n{ico} {ti['label']}\n\n🔍 Recuperation matchs + statistiques reelles...\n━━━━━━━━━━━━━━━━━━━━━"
    )

    matches = await fetch_matches(ti["label"], ti["api_date"])

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
            text=f"⚽ *ORACLE*\n\n❌ Aucun match trouve.\nVerifie FOOTBALL KEY ou reessaie."
        )
        return

    to_analyze = matches[:10]
    await bot.edit_message_text(
        chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
        text=(
            f"⚽ *ORACLE — {pfx}*\n{ico} {ti['label']}\n\n"
            f"✅ *{len(matches)} matchs* + stats reelles chargees\n"
            f"🔬 Analyse par 9 agents Groq...\n\n━━━━━━━━━━━━━━━━━━━━━"
        )
    )

    lessons = db.get("lessons", [])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition","")
        pmsg  = await bot.send_message(
            chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
            text=build_progress(i, len(to_analyze), mname, comp, {}, 0)
        )
        states = {ag["id"]:"wait" for ag in AGENTS}
        steps  = [0]

        async def pcb(aid, status, _s=states, _st=steps, _m=pmsg,
                      _n=mname, _c=comp, _i=i, _t=len(to_analyze)):
            if status=="run": _s[aid]="run"
            elif status=="done": _s[aid]="done"; _st[0]+=1
            pct = round(_st[0]/9*100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID, message_id=_m.message_id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=build_progress(_i,_t,_n,_c,_s,pct)
                )
            except: pass

        try:
            result = await analyze_match(match, lessons, pcb)
            results.append(result)
            v = result["verdict"]
            await bot.edit_message_text(
                chat_id=CHAT_ID, message_id=pmsg.message_id, parse_mode=ParseMode.MARKDOWN,
                text=(
                    f"✅ *{i+1}/{len(to_analyze)} — {mname}*\n\n"
                    f"`{'█'*10}  100%`\n\n"
                    f"🎯 *{v['pari']}*\n"
                    f"📊 Confiance : {v['conf']}%  |  Cote mini : {v['cm']}"
                )
            )
        except Exception as e:
            log.error(f"Erreur {mname}: {e}")
            try:
                await bot.edit_message_text(chat_id=CHAT_ID, message_id=pmsg.message_id, text=f"❌ Erreur {mname}")
            except: pass
        await asyncio.sleep(1)

    results.sort(key=lambda x: (x["verdict"]["conf"], x["verdict"].get("cm",0)), reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Aucune analyse completee.")
        return

    entry = {
        "date_key": ti["key"], "date_label": ti["label"],
        "is_tomorrow": ti["tmrw"], "timestamp": datetime.now().isoformat(),
        "bankroll": bankroll,
        "picks": [{
            "home": r["match"]["home"], "away": r["match"]["away"],
            "comp": r["match"].get("competition",""),
            "date": r["match"].get("date", ti["label"]),
            "heure": r["match"].get("heure",""),
            **r["verdict"], "result": None,
        } for r in top5]
    }
    db["scans"][ti["key"]] = entry
    save_db(db)

    await bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text=f"🏆 *TOP {len(top5)} PARIS — {pfx}*\n{ico} {ti['label']}\n━━━━━━━━━━━━━━━━━━━━━"
    )
    await asyncio.sleep(0.5)

    for rank, r in enumerate(top5, 1):
        pick = {
            "home": r["match"]["home"], "away": r["match"]["away"],
            "comp": r["match"].get("competition",""),
            "heure": r["match"].get("heure",""),
            **r["verdict"],
        }
        kbd = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{ti['key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{ti['key']}:{rank-1}:loss"),
        ]])
        await bot.send_message(
            chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
            text=fmt_pick(rank, pick, bankroll), reply_markup=kbd
        )
        await asyncio.sleep(0.5)

    await bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text="✅ *Scan termine !*\n\nAppuie sur WIN ou LOSS apres chaque match.\nL'IA apprend de chaque resultat 🧬\n\n/stats  /resultats  /bankroll"
    )

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    ti  = get_target()
    pfx = "demain" if ti["tmrw"] else "aujourd'hui"
    ico = "🌙" if ti["tmrw"] else "☀️"
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{ico} Scanner les matchs de {pfx}", callback_data="launch_scan")
    ]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"9 agents Groq — Stats reelles API-Football — Auto-apprentissage\n\n"
        f"*Commandes :*\n/scan — Lancer le scan\n/stats — Statistiques\n"
        f"/resultats — Paris en attente\n/bankroll 150 — Changer la bankroll\n\n"
        f"Il est {ti['hour']}h — scan pour {pfx}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kbd
    )

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db   = load_db()
    bank = db.get("bankroll", BANKROLL_DEF)
    allp = [p for s in db["scans"].values() for p in s["picks"]]
    dec  = [p for p in allp if p.get("result")]
    wins = [p for p in dec  if p["result"]=="win"]
    wr   = round(len(wins)/len(dec)*100) if dec else 0
    profit = sum(
        (bank*p.get("mp",2)/100)*p["cm"]-(bank*p.get("mp",2)/100)
        if p["result"]=="win" and p.get("cm")
        else -(bank*p.get("mp",2)/100) for p in dec
    )
    nb  = len(db.get("lessons",[]))
    lvl = "Expert ⭐" if nb>=20 else "Bon 🔥" if nb>=10 else "En cours 📈"
    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joues : *{len(dec)}*\n✅ Gagnes : *{len(wins)}*\n"
        f"❌ Perdus : *{len(dec)-len(wins)}*\n📈 Win rate : *{wr}%*\n"
        f"💵 Profit : *{'+' if profit>=0 else ''}{profit:.2f}€*\n\n"
        f"🧬 Lecons : *{nb}*  |  Niveau : *{lvl}*\n💰 Bankroll : *{bank:.2f}€*",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db  = load_db()
    pnd = [(dk,i,p,s["date_label"]) for dk,s in db["scans"].items()
           for i,p in enumerate(s["picks"]) if not p.get("result")]
    if not pnd:
        await update.message.reply_text("✅ Tous les resultats ont ete saisis !")
        return
    await update.message.reply_text(f"⏳ *{len(pnd)} paris en attente*", parse_mode=ParseMode.MARKDOWN)
    for dk,idx,pick,dlabel in pnd[:10]:
        kbd = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
        ]])
        await update.message.reply_text(
            f"📅 {dlabel}\n⚽ *{pick['home']} vs {pick['away']}*\n🎯 {pick['pari']} ({pick['conf']}%)",
            parse_mode=ParseMode.MARKDOWN, reply_markup=kbd
        )
        await asyncio.sleep(0.3)

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    try:
        amount = float(context.args[0])
        db = load_db(); db["bankroll"]=amount; save_db(db)
        await update.message.reply_text(f"💰 Bankroll : *{amount:.2f}€*", parse_mode=ParseMode.MARKDOWN)
    except (IndexError, ValueError):
        await update.message.reply_text("Usage : /bankroll 150")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.message.chat_id != CHAT_ID: return
    data = q.data
    if data == "launch_scan":
        db = load_db()
        await run_scan(context, db.get("bankroll", BANKROLL_DEF))
        return
    if data.startswith("res:"):
        _, dk, idx_s, result = data.split(":")
        idx = int(idx_s)
        db  = load_db()
        scan = db["scans"].get(dk)
        if not scan or idx >= len(scan["picks"]): return
        pick = scan["picks"][idx]
        prev = pick.get("result")
        pick["result"] = None if prev==result else result
        save_db(db)
        if pick["result"]:
            bank = db.get("bankroll", BANKROLL_DEF)
            mise = round(bank*pick.get("mp",2)/100, 2)
            cm   = pick.get("cm")
            gs   = f"+{round(mise*cm-mise,2)}€" if cm and pick["result"]=="win" else f"-{mise}€"
            ic   = "✅" if pick["result"]=="win" else "❌"
            try:
                await q.edit_message_text(
                    text=q.message.text+f"\n\n{ic} *{pick['result'].upper()}* — {gs}",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=None
                )
            except: pass
            if not prev:
                await trigger_learning(pick, db, context)
        else:
            kbd = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
            ]])
            try: await q.edit_message_reply_markup(reply_markup=kbd)
            except: pass

async def trigger_learning(pick, db, context):
    try:
        won = pick["result"]=="win"
        txt = await call_groq(
            "Auto-amelioration paris sportifs. Francais, concis.",
            f"Pari {'GAGNE' if won else 'PERDU'}:\n"
            f"Match: {pick['home']} vs {pick['away']}\n"
            f"Pari: {pick['pari']} | Confiance: {pick['conf']}%\n\n"
            f"Genere UNE lecon de 2 phrases pour ameliorer les prochaines analyses.",
            150
        )
        lesson = {
            "id": int(datetime.now().timestamp()),
            "date": datetime.now().strftime("%d/%m/%Y"),
            "match": f"{pick['home']} vs {pick['away']}",
            "pari": pick["pari"], "result": pick["result"], "text": txt.strip()
        }
        db.setdefault("lessons",[])
        db["lessons"].append(lesson)
        db["lessons"] = db["lessons"][-50:]
        save_db(db)
        ic = "🟢" if won else "🔴"
        await context.bot.send_message(
            chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
            text=f"🧬 *Lecon apprise !*\n\n{ic} {pick['home']} vs {pick['away']} — {'WIN' if won else 'LOSS'}\n\n💡 {txt.strip()}"
        )
    except Exception as e: log.error(f"Learning: {e}")

async def remind_yesterday(context):
    db  = load_db()
    yd  = (datetime.now()-timedelta(days=1)).strftime("%d/%m/%Y")
    scan = db["scans"].get(yd)
    if not scan: return
    pnd = [p for p in scan["picks"] if not p.get("result")]
    if not pnd: return
    await context.bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text=f"⏰ *Resultats en attente — {yd}*\n\n{len(pnd)} paris sans resultat !\nTape /resultats"
    )

async def auto_scan(context):
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

def main():
    for k,v in [("TELEGRAM_TOKEN",TOKEN),("FOOTBALL_KEY",FOOTBALL_KEY)]:
        if not v: log.error(f"{k} manquant"); return
    if not GROQ_KEYS: log.error("GROQ_KEYS manquantes"); return

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("bankroll",  cmd_bankroll))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq = app.job_queue
    jq.run_daily(auto_scan,        time=datetime.strptime(f"{SCAN_HOUR:02d}:00","%H:%M").time(), name="scan")
    jq.run_daily(remind_yesterday, time=datetime.strptime(f"{(SCAN_HOUR+1)%24:02d}:00","%H:%M").time(), name="remind")

    log.info(f"Oracle Bot demarre — {len(GROQ_KEYS)} cles Groq — scan auto {SCAN_HOUR}h")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
