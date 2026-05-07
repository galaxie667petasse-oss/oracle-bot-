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

# ── CONFIG ────────────────────────────────────────────────────────────────────
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

# ── DB ────────────────────────────────────────────────────────────────────────
def load_db():
    if DB_FILE.exists():
        try: return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except: pass
    return {"scans": {}, "lessons": [], "bankroll": BANKROLL_DEF}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

# ── DATE ──────────────────────────────────────────────────────────────────────
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

# ── GROQ API (sans Groq SDK pour eviter le bug proxies) ───────────────────────
async def call_groq(system: str, user: str, max_tokens: int = 500) -> str:
    key = next_key()
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
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
                        await asyncio.sleep((attempt+1) * 6)
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        raise RuntimeError(f"Groq HTTP {resp.status}: {text[:200]}")
                    data = await resp.json()
                    result = data["choices"][0]["message"]["content"].strip()
                    await asyncio.sleep(max(0.3, 1.0 / max(1, len(GROQ_KEYS))))
                    return result
        except RuntimeError:
            raise
        except Exception as e:
            log.warning(f"Groq attempt {attempt+1}: {e}")
            if attempt == 3: raise
            await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

# ── FETCH MATCHS — API-FOOTBALL ───────────────────────────────────────────────
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
]
LEAGUE_IDS   = {l[0] for l in LEAGUES}
LEAGUE_NAMES = {l[0]: l[1] for l in LEAGUES}
LEAGUE_PRIO  = {l[0]: i for i, l in enumerate(LEAGUES)}

async def fetch_matches(label: str, api_date: str) -> list:
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key":  FOOTBALL_KEY,
    }
    paris_tz = pytz.timezone("Europe/Paris")
    matches  = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://v3.football.api-sports.io/fixtures?date={api_date}&status=NS",
                headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    log.error(f"API-Football {resp.status}")
                    return []
                data = await resp.json()

        fixtures = data.get("response", [])
        log.info(f"API-Football: {len(fixtures)} matchs bruts")

        for fix in fixtures:
            lid = fix.get("league", {}).get("id")
            if lid not in LEAGUE_IDS:
                continue
            teams   = fix.get("teams", {})
            fixture = fix.get("fixture", {})
            home    = teams.get("home", {}).get("name", "?")
            away    = teams.get("away", {}).get("name", "?")
            comp    = LEAGUE_NAMES.get(lid, "?")
            heure   = ""
            kickoff = fixture.get("date", "")
            if kickoff:
                try:
                    dt    = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                    heure = dt.astimezone(paris_tz).strftime("%H:%M")
                except: pass
            matches.append({
                "home": home, "away": away, "competition": comp,
                "date": label, "heure": heure,
                "cote_home": None, "cote_draw": None, "cote_away": None,
                "contexte": f"{comp}",
                "_prio": LEAGUE_PRIO.get(lid, 99),
            })

        matches.sort(key=lambda m: m["_prio"])
        matches = matches[:10]
        log.info(f"Matchs selectionnes: {len(matches)}")

        # Enrichir contexte + cotes via Groq
        for m in matches:
            try:
                raw = await call_groq(
                    "Expert football. JSON uniquement, sans texte autour.",
                    f"Match: {m['home']} vs {m['away']} ({m['competition']}) le {label}\n"
                    f"Donne en JSON: contexte 15 mots, cotes estimees.\n"
                    f'Format: {{"contexte":"...","cote_home":1.85,"cote_draw":3.40,"cote_away":4.20}}',
                    100
                )
                raw = raw.strip()
                if "```" in raw:
                    r2 = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
                    if r2: raw = r2.group(1).strip()
                p = json.loads(raw)
                m["contexte"]  = p.get("contexte",  m["contexte"])
                m["cote_home"] = p.get("cote_home", None)
                m["cote_draw"] = p.get("cote_draw", None)
                m["cote_away"] = p.get("cote_away", None)
            except: pass

    except Exception as e:
        log.error(f"fetch_matches: {e}")
    return matches

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {"id":"tact",  "n":"Tacticien",    "e":"🧠",
     "s":"Expert tacticien football. Formations, pressing, transitions. 80 mots max."},
    {"id":"stat",  "n":"Statisticien", "e":"📊",
     "s":"Analyste statistique. Forme, H2H, buts, xG. 80 mots max."},
    {"id":"doc",   "n":"Medecin",      "e":"🏃",
     "s":"Medecin sportif. Fatigue, blessures, rotations. 80 mots max."},
    {"id":"scout", "n":"L'Ancien",     "e":"🧓",
     "s":"Scout 40 ans. Patterns caches, pieges, tendances. 80 mots max."},
    {"id":"mkt",   "n":"Marche",       "e":"💰",
     "s":"Expert paris. Value bets, probabilite implicite des cotes. 80 mots max."},
    {"id":"psy",   "n":"Psychologue",  "e":"🎭",
     "s":"Psychologue sport. Enjeux, pression, motivation. 80 mots max."},
    {"id":"juge",  "n":"Juge",         "e":"⚖️",
     "s":"Juge Arbitre. Synthetise les 6 rapports. 120 mots max."},
    {"id":"pr1",   "n":"Prof Pragma",  "e":"🎓",
     "s":"Professeur Pragmatique. Identifie failles, critique realiste. 100 mots max."},
    {"id":"pr2",   "n":"Prof Vision",  "e":"🔭", "s":""},
]

def build_pr2(lessons):
    """Prompt strict pour forcer JSON avec vraie diversite de paris."""
    lesson_block = ""
    if lessons:
        lesson_block = "\n\nLECONS PRECEDENTES (OBLIGATOIRE de les appliquer):\n"
        lesson_block += "\n".join(f"- {l['text']}" for l in lessons[-5:])

    return (
        "Tu es un expert en value betting football. Tu dois retourner UN OBJET JSON UNIQUEMENT.\n\n"
        "ANALYSE le match fourni et trouve le MEILLEUR PARI en termes de value.\n\n"
        "TYPES DE PARIS DISPONIBLES (choisis celui avec la meilleure value):\n"
        "- Victoire equipe A ou B (si forte domination attendue)\n"
        "- BTTS Oui (si les deux equipes ont tendance a marquer)\n"
        "- BTTS Non (si match serré tactique attendu)\n"
        "- Plus de 2.5 buts (si match offensif attendu)\n"
        "- Moins de 2.5 buts (si match defenstif ou enjeux defensifs)\n"
        "- Plus de 1.5 buts en 1ere mi-temps\n"
        "- Double chance (1X ou X2) si incertitude\n"
        "- Handicap -1 si domination ecrasante attendue\n"
        "- Match nul si equilibre parfait\n\n"
        "REGLES STRICTES POUR LES VALEURS:\n"
        "- confiance: calcule en fonction des VRAIS facteurs du match (pas un chiffre fixe)\n"
        "  * Match tres incertain = 58-63\n"
        "  * Leger avantage = 64-68\n"
        "  * Bon signal = 69-74\n"
        "  * Fort = 75-80\n"
        "  * Tres fort = 81-87\n"
        "- mise_pct: 1 si conf<65, 2 si conf 65-70, 3 si conf 71-76, 4 si conf 77-82, 5 si conf>82\n"
        "- cote_mini: cote REALISTE pour ce type de pari (ne pas toujours mettre 1.75)\n"
        "  * Victoire favori clair = 1.45-1.65\n"
        "  * Victoire favori leger = 1.70-1.95\n"
        "  * BTTS Oui = 1.65-1.90\n"
        "  * BTTS Non = 1.60-1.85\n"
        "  * Over 2.5 = 1.65-2.00\n"
        "  * Under 2.5 = 1.60-1.85\n"
        "  * Match nul = 2.80-3.60\n"
        "  * Double chance = 1.20-1.50\n\n"
        "RETOURNE UNIQUEMENT CE JSON (pas de texte avant ou apres):\n"
        "{\n"
        '  "pari": "nom exact du pari avec les vrais noms des equipes",\n'
        '  "confiance": <chiffre calcule selon les facteurs reels>,\n'
        '  "mise_pct": <1-5 selon la confiance>,\n'
        '  "cote_mini": <cote realiste pour ce type de pari>,\n'
        '  "risque": "risque principal specifique a CE match",\n'
        '  "resume": "3 phrases logiques basees sur les rapports des 8 agents"\n'
        "}" + lesson_block
    )

def parse_verdict(text: str) -> dict:
    """Parse le JSON retourne par le Prof Visionnaire."""
    default = {"pari": "Voir analyse", "conf": 65, "mp": 2, "cm": 1.75, "risque": "", "resume": ""}
    if not text:
        return default

    # Nettoyer le texte
    t = text.strip()
    # Enlever markdown si present
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m:
            t = m.group(1).strip()

    # Tentative JSON d'abord
    try:
        # Chercher le JSON dans le texte
        json_match = re.search(r'\{[\s\S]*?"pari"[\s\S]*?\}', t)
        if json_match:
            t = json_match.group(0)
        data = json.loads(t)

        pari   = str(data.get("pari", "")).strip()
        conf   = int(data.get("confiance", data.get("conf", 65)))
        mp     = int(data.get("mise_pct", data.get("mp", 2)))
        cm_raw = data.get("cote_mini", data.get("cm", 1.75))
        risque = str(data.get("risque", "")).strip()
        resume = str(data.get("resume", "")).strip()

        # Valider les valeurs
        conf = min(87, max(58, conf))
        mp   = min(5,  max(1,  mp))
        try:
            cm = float(str(cm_raw).replace(",","."))
            if cm < 1.10 or cm > 20: cm = 1.75
        except: cm = 1.75

        if not pari or len(pari) < 3:
            pari = "Voir analyse"

        log.info(f"Verdict JSON OK — {pari[:40]} conf={conf} cm={cm}")
        return {"pari": pari, "conf": conf, "mp": mp, "cm": cm, "risque": risque, "resume": resume}

    except Exception as e:
        log.warning(f"JSON parse failed: {e} — fallback texte")

    # Fallback: parser le texte libre si JSON echoue
    def g(rx, fb=""):
        m = re.search(rx, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else fb

    pari   = g(r'^PARI\s*:\s*(.+)$', "")
    cs     = g(r'^CONFIANCE\s*:\s*(\d+)', "65")
    ms     = g(r'^MISE_PCT\s*:\s*(\d+)', "2")
    cms    = g(r'^COTE[_\s]*MINI\s*:\s*([\d.,]+)', "1.75").replace(",",".")
    risque = g(r'^RISQUE\s*:\s*(.+)$', "")
    resume = g(r"^RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|\Z)", "")


    if not pari:
        for rx in [r"(BTTS|Over \d|Under \d|Victoire|Plus de|Moins de|Handicap|Match nul)[^\n]{0,60}"]:
            m = re.search(rx, text, re.IGNORECASE)
            m = re.search(rx, text, re.IGNORECASE)
            if m: pari = m.group(0).strip()[:80]; break
    if not pari: pari = "Voir analyse"

    try: conf = min(87, max(58, int(cs)))
    except: conf = 65
    try: mp = min(5, max(1, int(ms)))
    except: mp = 2
    try:
        cm = float(cms)
        if cm < 1.10 or cm > 20: cm = 1.75
    except: cm = 1.75

    if not resume:
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 30]
        resume = " ".join(lines[:3])

    log.info(f"Verdict fallback — {pari[:40]} conf={conf}")
    return {"pari": pari, "conf": conf, "mp": mp, "cm": cm, "risque": risque, "resume": resume.strip()}

# ── ANALYSE UN MATCH ──────────────────────────────────────────────────────────
async def analyze_match(match: dict, lessons: list, pcb) -> dict:
    ch = match.get("cote_home","?")
    cd = match.get("cote_draw","?")
    ca = match.get("cote_away","?")
    base = (
        f"MATCH: {match['home']} vs {match['away']}\n"
        f"Competition: {match.get('competition','')}\n"
        f"Heure: {match.get('heure','?')}\n"
        f"Contexte: {match.get('contexte','')}\n"
        f"Cotes: Dom {ch} | Nul {cd} | Ext {ca}"
    )
    reports = {}
    AGENTS[8]["s"] = build_pr2(lessons)

    # 6 agents specialistes
    for ag in AGENTS[:6]:
        await pcb(ag["id"], "run")
        try:
            reports[ag["id"]] = await call_groq(ag["s"], base + "\n\nAnalyse en 80 mots.", 220)
        except Exception as e:
            reports[ag["id"]] = f"Erreur: {e}"
        await pcb(ag["id"], "done")

    all_r = "\n\n".join(
        f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports[AGENTS[i]['id']]}"
        for i in range(6)
    )

    # Juge
    await pcb("juge", "run")
    try:
        reports["juge"] = await call_groq(
            AGENTS[6]["s"], f"{base}\n\nRAPPORTS:\n{all_r}\n\nSynthese.", 280)
    except Exception as e:
        reports["juge"] = f"Erreur: {e}"
    await pcb("juge", "done")

    # Prof Pragmatique
    await pcb("pr1", "run")
    try:
        reports["pr1"] = await call_groq(
            AGENTS[7]["s"], f"{base}\n\nJUGE:\n{reports['juge']}\n\nCorrige.", 220)
    except Exception as e:
        reports["pr1"] = f"Erreur: {e}"
    await pcb("pr1", "done")

    # Prof Visionnaire — verdict final
    await pcb("pr2", "run")
    try:
        home_name = match['home']
        away_name = match['away']
        reports["pr2"] = await call_groq(
            AGENTS[8]["s"],
            f"{base}\n\nJUGE:\n{reports['juge']}\n\nPRAGMATIQUE:\n{reports['pr1']}\n\n"
            f"Retourne UNIQUEMENT le JSON de ton verdict.\n"
            f"IMPORTANT: Dans le champ pari, utilise les VRAIS noms: '{home_name}' et '{away_name}'.\n"
            f"Exemple pari valide: 'Victoire {home_name}' ou 'BTTS Oui' ou 'Plus de 2.5 buts'\n"
            f"JSON uniquement, aucun texte autour.",
            400
        )
    except Exception as e:
        reports["pr2"] = f"Erreur: {e}"
    await pcb("pr2", "done")

    return {"match": match, "reports": reports, "verdict": parse_verdict(reports.get("pr2",""))}

# ── UI ────────────────────────────────────────────────────────────────────────
def bar(pct: int, size: int = 10) -> str:
    f = round(pct / (100 / size))
    return "█" * f + "░" * (size - f)

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

def fmt_pick(rank: int, pick: dict, bankroll: float) -> str:
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    medal  = medals[rank-1] if rank <= 5 else f"#{rank}"
    home   = pick.get("home","?")
    away   = pick.get("away","?")
    comp   = pick.get("comp","")
    heure  = pick.get("heure","")
    pari   = pick.get("pari","—")
    # Remplacer X/Y generiques par vrais noms d'equipes
    pari = pari.replace(" X", f" {home}").replace(" Y", f" {away}")
    pari = re.sub(r"Victoire domicile", f"Victoire {home}", pari, flags=re.IGNORECASE)
    pari = re.sub(r"Victoire exterieur", f"Victoire {away}", pari, flags=re.IGNORECASE)
    conf   = pick.get("conf", 65)
    mp     = pick.get("mp", 2)
    cm     = pick.get("cm", None)
    risque = pick.get("risque","")
    resume = pick.get("resume","")
    mise   = round(bankroll * mp / 100, 2)
    gain   = round(mise * cm, 2) if cm else None
    ben    = round(gain - mise, 2) if gain else None

    conf_icon = "🔥" if conf >= 75 else "✅" if conf >= 65 else "👍"

    lines = [
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}" + (f"  ⏰ {heure}" if heure else ""),
        f"━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 *PARI : {pari}*",
        "",
        f"📊 Confiance : `{bar(conf)}` {conf_icon} *{conf}%*",
        f"💰 Mise : *{mise}€*  ({mp}% de ta bankroll)",
    ]
    if cm:
        lines += [
            f"⚡ Cote minimum : *{cm}*",
            f"🎁 Si gagne : *{gain}€*  (profit +{ben}€)",
        ]
    if resume:
        lines += ["", f"💡 *Pourquoi ce pari :*", f"{resume}"]
    if risque:
        lines += ["", f"⚠️ *Risque :* {risque}"]
    return "\n".join(lines)

# ── SCAN ──────────────────────────────────────────────────────────────────────
async def run_scan(context, bankroll: float):
    bot = context.bot
    db  = load_db()
    ti  = get_target()
    pfx = "DEMAIN" if ti["tmrw"] else "AUJOURD'HUI"
    ico = "🌙" if ti["tmrw"] else "☀️"

    msg = await bot.send_message(
        chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
        text=f"⚽ *ORACLE — SCAN {pfx}*\n{ico} {ti['label']}\n\n🔍 Recuperation des matchs...\n━━━━━━━━━━━━━━━━━━━━━"
    )

    matches = await fetch_matches(ti["label"], ti["api_date"])

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
            text=f"⚽ *ORACLE*\n\n❌ Aucun match trouve pour {ti['label']}.\nVerifie FOOTBALL KEY ou reessaie."
        )
        return

    to_analyze = matches[:10]
    await bot.edit_message_text(
        chat_id=CHAT_ID, message_id=msg.message_id, parse_mode=ParseMode.MARKDOWN,
        text=(
            f"⚽ *ORACLE — {pfx}*\n{ico} {ti['label']}\n\n"
            f"✅ *{len(matches)} vrais matchs* via API-Football\n"
            f"🔬 Analyse de {len(to_analyze)} matchs par 9 agents Groq...\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
    )

    lessons = db.get("lessons", [])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition","")

        pmsg = await bot.send_message(
            chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN,
            text=build_progress(i, len(to_analyze), mname, comp, {}, 0)
        )

        states = {ag["id"]:"wait" for ag in AGENTS}
        steps  = [0]

        async def pcb(aid, status, _s=states, _st=steps, _m=pmsg,
                      _n=mname, _c=comp, _i=i, _t=len(to_analyze)):
            if status == "run":  _s[aid] = "run"
            elif status == "done": _s[aid] = "done"; _st[0] += 1
            pct = round(_st[0] / 9 * 100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID, message_id=_m.message_id,
                    parse_mode=ParseMode.MARKDOWN,
                    text=build_progress(_i, _t, _n, _c, _s, pct)
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
                    f"📊 Confiance : {v['conf']}%\n"
                    f"⚡ Cote mini : {v['cm']}"
                )
            )
        except Exception as e:
            log.error(f"Erreur {mname}: {e}")
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID, message_id=pmsg.message_id,
                    text=f"❌ Erreur sur {mname}"
                )
            except: pass
        await asyncio.sleep(1)

    results.sort(key=lambda x: x["verdict"]["conf"], reverse=True)
    # Deduplication - si meme confiance, trier par cote_mini decroissante
    results.sort(key=lambda x: (x["verdict"]["conf"], x["verdict"].get("cm",0)), reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Aucune analyse completee. Reessaie avec /scan.")
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
        text="✅ *Scan termine !*\n\nAppuie sur WIN ou LOSS apres chaque match.\nL'IA apprend 🧬\n\n/stats  /resultats  /bankroll"
    )

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    ti = get_target()
    pfx = "demain" if ti["tmrw"] else "aujourd'hui"
    ico = "🌙" if ti["tmrw"] else "☀️"
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{ico} Scanner les matchs de {pfx}", callback_data="launch_scan")
    ]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"9 agents Groq — Matchs API-Football — Auto-apprentissage\n\n"
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
    wins = [p for p in dec  if p["result"] == "win"]
    wr   = round(len(wins)/len(dec)*100) if dec else 0
    profit = sum(
        (bank*p.get("mp",2)/100)*p["cm"] - (bank*p.get("mp",2)/100)
        if p["result"]=="win" and p.get("cm")
        else -(bank*p.get("mp",2)/100)
        for p in dec
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
        db = load_db(); db["bankroll"] = amount; save_db(db)
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
        pick["result"] = None if prev == result else result
        save_db(db)

        if pick["result"]:
            bank = db.get("bankroll", BANKROLL_DEF)
            mise = round(bank * pick.get("mp",2) / 100, 2)
            cm   = pick.get("cm")
            gs   = f"+{round(mise*cm-mise,2)}€" if cm and pick["result"]=="win" else f"-{mise}€"
            ic   = "✅" if pick["result"]=="win" else "❌"
            try:
                await q.edit_message_text(
                    text=q.message.text + f"\n\n{ic} *{pick['result'].upper()}* — {gs}",
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
        won = pick["result"] == "win"
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
    except Exception as e:
        log.error(f"Learning: {e}")

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

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    for k, v in [("TELEGRAM_TOKEN", TOKEN), ("FOOTBALL_KEY", FOOTBALL_KEY)]:
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
