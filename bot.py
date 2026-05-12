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

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS","").split(",") if k.strip()]
ODDSPAPI_KEY = os.getenv("ODDSPAPI_KEY", "")
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "10"))
DB_FILE = Path("oracle_db.json")
GROQ_IDX = 0

def next_key():
    global GROQ_IDX
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
    now = datetime.now(pytz.timezone("Europe/Paris"))
    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    return {"label": f"{JOURS[now.weekday()]} {now.day} {MOIS[now.month-1]} {now.year}", "key": now.strftime("%d/%m/%Y"), "iso_date": now.strftime("%Y-%m-%d"), "hour": now.hour}

async def call_groq(system: str, user: str, max_tokens: int = 500) -> str:
    key = next_key()
    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role":"system","content":system},{"role":"user","content":user}], "max_tokens": max_tokens, "temperature": 0.6}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(4):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30) as resp:
                    if resp.status == 429:
                        await asyncio.sleep((attempt+1)*6); continue
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == 3: raise
            await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

# THE ODDS API
async def fetch_matches(iso_date: str, label: str) -> list:
    if not ODDSPAPI_KEY: raise RuntimeError("ODDSPAPI_KEY manquante")
    paris_tz = pytz.timezone("Europe/Paris")
    SPORT_KEYS = ["soccer_france_ligue_1","soccer_france_ligue_2","soccer_epl","soccer_england_championship","soccer_spain_la_liga","soccer_italy_serie_a","soccer_germany_bundesliga","soccer_uefa_champions_league","soccer_uefa_europa_league","soccer_uefa_europa_conf_league"]

    matches = []
    start = f"{iso_date}T00:00:00Z"
    end = f"{iso_date}T23:59:59Z"

    async with aiohttp.ClientSession() as session:
        for sport in SPORT_KEYS:
            params = {"apiKey": ODDSPAPI_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal", "commenceTimeFrom": start, "commenceTimeTo": end}
            try:
                async with session.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds", params=params, timeout=15) as resp:
                    if resp.status != 200: continue
                    data = await resp.json()
                    for event in data:
                        try:
                            dt = datetime.fromisoformat(event["commence_time"].replace("Z","+00:00"))
                            dt_p = dt.astimezone(paris_tz)
                            if dt_p.strftime("%Y-%m-%d") != iso_date: continue
                            heure = dt_p.strftime("%H:%M")
                        except: continue
                        home = event.get("home_team","?")
                        away = event.get("away_team","?")
                        ch = cd = ca = bk = None
                        for bookmaker in event.get("bookmakers", []):
                            if bookmaker["key"] not in ["bet365","unibet","pinnacle"]: continue
                            for market in bookmaker.get("markets", []):
                                if market["key"] != "h2h": continue
                                outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
                                ch = outcomes.get("Home")
                                cd = outcomes.get("Draw")
                                ca = outcomes.get("Away")
                                bk = bookmaker["key"]
                                if ch and ca: break
                            if ch: break
                        if ch:
                            matches.append({"home":home,"away":away,"competition":sport.replace("_"," ").title(),"date":label,"heure":heure,"cote_home":ch,"cote_draw":cd,"cote_away":ca,"bookmaker":bk})
            except: continue
    matches.sort(key=lambda m: m.get("heure","99:99"))
    return matches[:12]

# 12 AGENTS SPÉCIALISÉS
AGENTS = [
    {"id":"tact", "n":"Tacticien", "e":"🧠", "s":"Expert tacticien. Formations, pressing, transitions. 80 mots max. Français."},
    {"id":"stat", "n":"Statisticien", "e":"📊", "s":"Stats + xG + forme + H2H. 80 mots max. Français."},
    {"id":"doc", "n":"Médecin", "e":"🏃", "s":"Blessures, fatigue, rotations. 80 mots max. Français."},
    {"id":"scout", "n":"L'Ancien", "e":"🧓", "s":"Patterns cachés, pièges, coaching. 80 mots max. Français."},
    {"id":"mkt", "n":"Marché", "e":"💰", "s":"Value betting + vraies cotes. 80 mots max. Français."},
    {"id":"psy", "n":"Psychologue", "e":"🎭", "s":"Motivation, pression, derby. 80 mots max. Français."},
    {"id":"meteo", "n":"Météo", "e":"🌧️", "s":"Impact pluie/vent sur le match. 60 mots max. Français."},
    {"id":"juge", "n":"Juge", "e":"⚖️", "s":"Synthèse des 7 rapports. 130 mots max. Français."},
    {"id":"pr1", "n":"Prof Pragma", "e":"🎓", "s":"Critique réaliste, failles. 100 mots max. Français."},
    {"id":"pr2", "n":"Prof Vision", "e":"🔭", "s":""},
    {"id":"arbitre", "n":"Arbitre", "e":"⚖️", "s":"Style arbitre (cartons/corners). 60 mots max. Français."},
    {"id":"corners", "n":"Corners", "e":"📐", "s":"Stats corners + BTTS corners. 60 mots max. Français."}
]

# ── METEO, CONTEXT, BUILD_PR2, PARSE_VERDICT, ANALYZE_MATCH, etc. (code original complet) ──
# (le reste du fichier est exactement le même que la version originale que tu avais avant, avec seulement AGENTS et fetch_matches mis à jour)

# Pour gagner de la place je ne recopie pas tout ici, mais tu peux garder tout le code à partir de # ── METEO jusqu'à la fin du fichier original.

# Si tu veux le fichier complet en un seul bloc sans rien manquer, dis-moi "envoie le full" et je te le donne en une seule fois.

# Sinon remplace juste la partie AGENTS et fetch_matches dans ton fichier actuel.

# Push sur GitHub → Railway redéploie.
