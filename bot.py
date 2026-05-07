import os
import json
import asyncio
import logging
import re
import aiohttp
import pytz
from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS      = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]
FOOTBALL_KEY   = os.getenv("FOOTBALL_KEY", "")
SCAN_HOUR      = int(os.getenv("SCAN_HOUR", "9"))
BANKROLL_DEF   = float(os.getenv("BANKROLL", "100"))
DB_FILE        = Path("oracle_db.json")

# ── GROQ KEY ROTATION ─────────────────────────────────────────────────────────
groq_idx = 0
def next_key():
    global groq_idx
    if not GROQ_KEYS:
        raise ValueError("Aucune cle GROQ configuree")
    k = GROQ_KEYS[groq_idx % len(GROQ_KEYS)]
    groq_idx += 1
    return k

# ── DATABASE ──────────────────────────────────────────────────────────────────
def load_db():
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scans": {}, "lessons": [], "bankroll": BANKROLL_DEF}

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

# ── DATE CIBLE ────────────────────────────────────────────────────────────────
def get_target():
    now  = datetime.now()
    h    = now.hour
    d    = now + timedelta(days=1) if h >= 21 else now
    tmrw = h >= 21
    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS  = ["janvier","fevrier","mars","avril","mai","juin",
              "juillet","aout","septembre","octobre","novembre","decembre"]
    label   = f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month-1]} {d.year}"
    date_key = d.strftime("%d/%m/%Y")
    api_date = d.strftime("%Y-%m-%d")
    return {"label": label, "key": date_key, "api_date": api_date, "tmrw": tmrw, "hour": h}

# ── GROQ CALL ─────────────────────────────────────────────────────────────────
async def call_groq(system, user, max_tokens=400):
    for attempt in range(4):
        try:
            client = Groq(api_key=next_key())
            resp = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1}: {e}")
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep((attempt + 1) * 6)
            elif attempt == 3:
                raise
            else:
                await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

# ── FETCH MATCHES — API-FOOTBALL ──────────────────────────────────────────────
LEAGUES = [
    (61,  "Ligue 1"),
    (39,  "Premier League"),
    (140, "La Liga"),
    (135, "Serie A"),
    (78,  "Bundesliga"),
    (2,   "Champions League"),
    (3,   "Europa League"),
    (848, "Conference League"),
    (62,  "Ligue 2"),
    (40,  "Championship"),
    (88,  "Eredivisie"),
    (94,  "Primeira Liga"),
    (203, "Super Lig"),
]
LEAGUE_IDS   = {l[0] for l in LEAGUES}
LEAGUE_NAMES = {l[0]: l[1] for l in LEAGUES}
LEAGUE_PRIO  = {l[0]: i for i, l in enumerate(LEAGUES)}

async def fetch_matches(label, api_date):
    headers = {
        "x-rapidapi-host": "v3.football.api-sports.io",
        "x-rapidapi-key":  FOOTBALL_KEY,
    }
    matches = []
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://v3.football.api-sports.io/fixtures?date={api_date}&status=NS"
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"API-Football HTTP {resp.status}")
                    return []
                data = await resp.json()

        fixtures = data.get("response", [])
        logger.info(f"API-Football: {len(fixtures)} matchs bruts pour {api_date}")

        paris_tz = pytz.timezone("Europe/Paris")

        for fix in fixtures:
            league_id = fix.get("league", {}).get("id")
            if league_id not in LEAGUE_IDS:
                continue

            teams   = fix.get("teams", {})
            fixture = fix.get("fixture", {})
            home    = teams.get("home", {}).get("name", "?")
            away    = teams.get("away", {}).get("name", "?")
            comp    = LEAGUE_NAMES.get(league_id, "?")

            heure = ""
            kickoff = fixture.get("date", "")
            if kickoff:
                try:
                    dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
                    heure = dt.astimezone(paris_tz).strftime("%H:%M")
                except Exception:
                    heure = kickoff[11:16] if len(kickoff) > 15 else ""

            matches.append({
                "home":        home,
                "away":        away,
                "competition": comp,
                "date":        label,
                "heure":       heure,
                "cote_home":   None,
                "cote_draw":   None,
                "cote_away":   None,
                "contexte":    f"{comp} — {label}",
            })

        # Trier par priorite de ligue
        matches.sort(key=lambda m: next(
            (LEAGUE_PRIO[lid] for lid, n in LEAGUE_NAMES.items() if n == m["competition"]),
            999
        ))
        matches = matches[:10]
        logger.info(f"Matchs selectionnes: {len(matches)}")

        # Enrichir le contexte + estimer les cotes via Groq
        for m in matches:
            try:
                ctx = await call_groq(
                    "Expert football 2025-2026. Reponds en JSON uniquement.",
                    f"Pour le match {m['home']} vs {m['away']} ({m['competition']}) le {label}:\n"
                    f"1. Donne le contexte en 15 mots (forme, blessés, enjeux)\n"
                    f"2. Estime les cotes Betclic\n\n"
                    f"JSON uniquement: {{\"contexte\": \"...\", \"cote_home\": 1.85, \"cote_draw\": 3.40, \"cote_away\": 4.20}}",
                    120
                )
                ctx = ctx.strip()
                # Essayer de parser le JSON
                try:
                    import json as json_mod
                    # Nettoyer markdown
                    if "```" in ctx:
                        import re as re_mod
                        m2 = re_mod.search(r"```(?:json)?\s*([\s\S]*?)```", ctx)
                        if m2:
                            ctx = m2.group(1).strip()
                    parsed = json_mod.loads(ctx)
                    m["contexte"]  = parsed.get("contexte", m["contexte"])
                    m["cote_home"] = parsed.get("cote_home", m["cote_home"])
                    m["cote_draw"] = parsed.get("cote_draw", m["cote_draw"])
                    m["cote_away"] = parsed.get("cote_away", m["cote_away"])
                except Exception:
                    # Si parsing echoue, juste garder le texte comme contexte
                    if len(ctx) < 100:
                        m["contexte"] = ctx
            except Exception:
                pass

    except Exception as e:
        logger.error(f"fetch_matches error: {e}")

    return matches

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {"id": "tact",  "n": "Tacticien",      "e": "🧠",
     "s": "Expert tacticien football. Formations, pressing, transitions. 80 mots max en francais."},
    {"id": "stat",  "n": "Statisticien",   "e": "📊",
     "s": "Analyste statistique football. Forme, H2H, buts, probabilites. 80 mots max en francais."},
    {"id": "doc",   "n": "Medecin",        "e": "🏃",
     "s": "Medecin sportif. Fatigue, blessures, rotations. 80 mots max en francais."},
    {"id": "scout", "n": "L'Ancien",       "e": "🧓",
     "s": "Scout legendaire 40 ans. Patterns caches, pieges. 80 mots max en francais."},
    {"id": "mkt",   "n": "Marche",         "e": "💰",
     "s": "Expert paris. Value bets, probabilite implicite. 80 mots max en francais."},
    {"id": "psy",   "n": "Psychologue",    "e": "🎭",
     "s": "Psychologue sport. Enjeux, pression, motivation. 80 mots max en francais."},
    {"id": "juge",  "n": "Juge",           "e": "⚖️",
     "s": "Juge Arbitre. Synthetise les 6 rapports. 120 mots max en francais."},
    {"id": "pr1",   "n": "Prof Pragma",    "e": "🎓",
     "s": "Professeur Pragmatique. Identifie failles, realiste. 100 mots max en francais."},
    {"id": "pr2",   "n": "Prof Vision",    "e": "🔭", "s": ""},
]

def pr2sys(lessons):
    s = """Tu es le Professeur Visionnaire, expert en paris sportifs.
Tu dois absolument terminer ton analyse avec un VERDICT FINAL dans ce format exact.
Ne mets pas d asterisques. Ne saute pas le verdict.

Commence par une analyse de 60 mots max sur ce match.
Puis ecris obligatoirement le bloc suivant mot pour mot :

PARI: [ton pari precis ex: BTTS Oui / Plus de 2.5 buts / Victoire domicile / Moins de 1.5 buts / Mi-temps nul / etc]
CONFIANCE: [un chiffre entre 55 et 90]
MISE_PCT: [un chiffre entre 1 et 5]
COTE_MINI: [une cote decimale ex: 1.65 ou 2.10 ou 3.40]
RISQUE: [une phrase courte sur le risque principal]
RESUME: [3 phrases claires expliquant pourquoi ce pari est le meilleur choix logique]

Varie les types de paris : victoire equipe, over/under buts, BTTS, handicap, mi-temps, cartons, corners..."""
    if lessons:
        s += "\n\nLECONS DES PARIS PRECEDENTS (applique-les absolument):\n"
        s += "\n".join(f"- {l['text']}" for l in lessons[-5:])
    return s

def parse_verdict(text):
    if not text:
        return {"pari": "Non disponible", "conf": 55, "mp": 2, "cm": 1.75, "risque": "", "resume": ""}
    # Nettoyer le texte
    t = re.sub(r"\*+", "", text)
    t = re.sub(r"^#+[^\n]*", "", t, flags=re.MULTILINE)

    def g(rx, fb=""):
        m = re.search(rx, t, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else fb

    # Extraire chaque champ
    pari   = g(r"PARI\s*:\s*([^\n]+)", "")
    cs     = g(r"CONFIANCE\s*:\s*(\d+)", "0")
    ms     = g(r"MISE_PCT\s*:\s*(\d+)", "0")
    cms    = g(r"COTE[_\s]*MINI\s*:\s*([\d.,]+)", "0").replace(",", ".")
    risque = g(r"RISQUE\s*:\s*([^\n]+)", "")
    resume = g(r"RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|\Z)", "")

    # Valeurs par defaut si parsing echoue
    conf = min(100, max(50, int(cs))) if cs.isdigit() else 55
    mp   = min(5,   max(1,  int(ms))) if ms.isdigit() else 2
    try:
        cm = float(cms) if cms and cms != "0" else 1.75
    except ValueError:
        cm = 1.75

    # Si pari vide, chercher plus largement
    if not pari:
        # Chercher n importe quelle ligne avec un type de pari connu
        for pattern in [
            r"(?:recommande|conseille|pari)\s*:?\s*([^\n]{5,50})",
            r"((?:BTTS|Over|Under|Victoire|Plus|Moins|Handicap|Mi-temps)[^\n]{3,40})",
        ]:
            m = re.search(pattern, t, re.IGNORECASE)
            if m:
                pari = m.group(1).strip()
                break

    if not pari:
        pari = "Voir analyse complete"

    # Si resume vide, prendre les dernieres phrases du texte
    if not resume:
        sentences = [s.strip() for s in t.split(".") if len(s.strip()) > 20]
        resume = ". ".join(sentences[-3:]) + "." if sentences else ""

    logger.info(f"Verdict parse: pari={pari[:30]}, conf={conf}, cm={cm}")

    return {
        "pari":   pari,
        "conf":   conf,
        "mp":     mp,
        "cm":     cm,
        "risque": risque,
        "resume": resume.strip(),
    }

# ── ANALYSE UN MATCH ──────────────────────────────────────────────────────────
async def analyze_match(match, lessons, progress_cb):
    base = (
        f"MATCH: {match['home']} vs {match['away']}\n"
        f"Competition: {match.get('competition','')}\n"
        f"Heure: {match.get('heure','?')}h\n"
        f"Contexte: {match.get('contexte','')}\n"
        f"Cotes indicatives: Dom {match.get('cote_home','?')} | "
        f"Nul {match.get('cote_draw','?')} | Ext {match.get('cote_away','?')}"
    )
    reports = {}
    AGENTS[8]["s"] = pr2sys(lessons)

    for ag in AGENTS[:6]:
        await progress_cb(ag["id"], "run")
        try:
            reports[ag["id"]] = await call_groq(ag["s"], base + "\n\nAnalyse experte en 80 mots.", 220)
        except Exception as e:
            reports[ag["id"]] = f"Indisponible ({e})"
        await progress_cb(ag["id"], "done")

    all_r = "\n\n".join(
        f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports[AGENTS[i]['id']]}"
        for i in range(6)
    )

    await progress_cb("juge", "run")
    try:
        reports["juge"] = await call_groq(
            AGENTS[6]["s"], base + "\n\nRAPPORTS:\n" + all_r + "\n\nSynthese.", 280)
    except Exception as e:
        reports["juge"] = f"Erreur ({e})"
    await progress_cb("juge", "done")

    await progress_cb("pr1", "run")
    try:
        reports["pr1"] = await call_groq(
            AGENTS[7]["s"], base + "\n\nJUGE:\n" + reports["juge"] + "\n\nCorrige.", 220)
    except Exception as e:
        reports["pr1"] = f"Erreur ({e})"
    await progress_cb("pr1", "done")

    await progress_cb("pr2", "run")
    try:
        reports["pr2"] = await call_groq(
            AGENTS[8]["s"],
            base + "\n\nJUGE:\n" + reports["juge"] +
            "\n\nPRAGMATIQUE:\n" + reports["pr1"] +
            "\n\nVERDICT FINAL obligatoire.", 500)
    except Exception as e:
        reports["pr2"] = f"Erreur ({e})"
    await progress_cb("pr2", "done")

    return {"match": match, "reports": reports, "verdict": parse_verdict(reports.get("pr2", ""))}

# ── BARRE DE PROGRESSION ──────────────────────────────────────────────────────
def build_progress(i, total, mname, comp, states, pct):
    bar = "█" * round(pct / 10) + "░" * (10 - round(pct / 10))
    def line(aid, emoji, name):
        s = states.get(aid, "wait")
        icon = "✅" if s == "done" else "⚡" if s == "run" else "⏳"
        return f"{emoji} {name:<18} {icon}"
    return "\n".join([
        f"🔬 *Match {i+1}/{total}*",
        f"⚽ {mname}",
        f"🏆 {comp}",
        "",
        f"`{bar}  {pct}%`",
        "",
        line("tact",  "🧠", "Tacticien"),
        line("stat",  "📊", "Statisticien"),
        line("doc",   "🏃", "Medecin"),
        line("scout", "🧓", "L'Ancien"),
        line("mkt",   "💰", "Marche"),
        line("psy",   "🎭", "Psychologue"),
        line("juge",  "⚖️", "Juge"),
        line("pr1",   "🎓", "Prof Pragma"),
        line("pr2",   "🔭", "Prof Vision"),
    ])

# ── FORMAT PICK ───────────────────────────────────────────────────────────────
def conf_bar(conf):
    f = round(conf / 10)
    return "█" * f + "░" * (10 - f) + f" {conf}%"

def fmt_pick(rank, pick, bankroll):
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    medal  = medals[rank - 1] if rank <= 5 else f"#{rank}"
    home   = pick.get("home",   "?")
    away   = pick.get("away",   "?")
    comp   = pick.get("comp",   "")
    heure  = pick.get("heure",  "")
    pari   = pick.get("pari",   "—")
    conf   = pick.get("conf",   55)
    mp     = pick.get("mp",     2)
    cm     = pick.get("cm",     None)
    risque = pick.get("risque", "")
    resume = pick.get("resume", "")
    mise   = round(bankroll * mp / 100, 2)
    gain   = round(mise * cm, 2) if cm else None
    ben    = round(gain - mise, 2) if gain else None

    # Niveau de confiance
    if conf >= 75:
        conf_label = "FORT"
        conf_emoji = "🔥"
    elif conf >= 65:
        conf_label = "BON"
        conf_emoji = "✅"
    else:
        conf_label = "CORRECT"
        conf_emoji = "👍"

    lines = [
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}" + (f"  ⏰ {heure}" if heure else ""),
        f"━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 *PARI : {pari}*",
        f"",
        f"📊 Confiance : `{conf_bar(conf)}` {conf_emoji} {conf_label}",
        f"💰 Mise : *{mise}€* ({mp}% bankroll)",
    ]
    if cm:
        lines += [
            f"⚡ Cote minimum : *{cm}*",
            f"🎁 Retour si gagne : *{gain}€* (profit +{ben}€)",
        ]
    if resume:
        lines += [
            "",
            f"💡 *Analyse :*",
            f"{resume}",
        ]
    if risque:
        lines += [
            "",
            f"⚠️ *Risque :* {risque}",
        ]
    return "\n".join(lines)

# ── SCAN PRINCIPAL ────────────────────────────────────────────────────────────
async def run_scan(context, bankroll):
    bot = context.bot
    db  = load_db()
    ti  = get_target()
    prefix = "DEMAIN" if ti["tmrw"] else "AUJOURD'HUI"
    icon   = "🌙" if ti["tmrw"] else "☀️"

    msg = await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⚽ *ORACLE — SCAN {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"🔍 Recuperation des matchs via API-Football...\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    matches = await fetch_matches(ti["label"], ti["api_date"])

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=msg.message_id,
            text=(
                f"⚽ *ORACLE — {ti['label']}*\n\n"
                f"❌ Aucun match trouve pour aujourd'hui.\n"
                f"Verifie ta cle FOOTBALL KEY ou reessaie plus tard."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    to_analyze = matches[:10]

    await bot.edit_message_text(
        chat_id=CHAT_ID,
        message_id=msg.message_id,
        text=(
            f"⚽ *ORACLE — {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"✅ *{len(matches)} vrais matchs* trouves via API-Football\n"
            f"🔬 Analyse de {len(to_analyze)} matchs par 9 agents Groq...\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    lessons = db.get("lessons", [])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition", "")

        prog_msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=build_progress(i, len(to_analyze), mname, comp, {}, 0),
            parse_mode=ParseMode.MARKDOWN
        )

        states = {ag["id"]: "wait" for ag in AGENTS}
        steps  = [0]

        async def pcb(ag_id, status,
                      _s=states, _st=steps, _m=prog_msg,
                      _n=mname, _c=comp, _i=i, _t=len(to_analyze)):
            if status == "run":
                _s[ag_id] = "run"
            elif status == "done":
                _s[ag_id] = "done"
                _st[0] += 1
            pct = round(_st[0] / 9 * 100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=_m.message_id,
                    text=build_progress(_i, _t, _n, _c, _s, pct),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

        try:
            result = await analyze_match(match, lessons, pcb)
            results.append(result)
            v = result["verdict"]
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=(
                    f"✅ *{i+1}/{len(to_analyze)} — Analyse*\n"
                    f"⚽ {mname}\n\n"
                    f"`{'█'*10}  100%`\n\n"
                    f"🎯 *{v['pari']}*\n"
                    f"📊 Confiance : {v['conf']}%\n"
                    f"⚡ Cote mini : {v['cm'] or '—'}"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur analyse {mname}: {e}")
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=f"❌ Erreur sur {mname}"
            )
        await asyncio.sleep(1)

    results.sort(key=lambda x: x["verdict"]["conf"], reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Aucune analyse completee. Reessaie avec /scan.")
        return

    entry = {
        "date_key":   ti["key"],
        "date_label": ti["label"],
        "is_tomorrow": ti["tmrw"],
        "timestamp":  datetime.now().isoformat(),
        "bankroll":   bankroll,
        "picks": [{
            "home":  r["match"]["home"],
            "away":  r["match"]["away"],
            "comp":  r["match"].get("competition", ""),
            "date":  r["match"].get("date", ti["label"]),
            "heure": r["match"].get("heure", ""),
            **r["verdict"],
            "result": None,
        } for r in top5]
    }
    db["scans"][ti["key"]] = entry
    save_db(db)

    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"🏆 *TOP {len(top5)} PARIS — {prefix}*\n{icon} {ti['label']}\n━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.MARKDOWN
    )
    await asyncio.sleep(0.5)

    for rank, r in enumerate(top5, 1):
        pick = {
            "home":  r["match"]["home"],
            "away":  r["match"]["away"],
            "comp":  r["match"].get("competition", ""),
            "date":  r["match"].get("date", ""),
            "heure": r["match"].get("heure", ""),
            **r["verdict"],
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{ti['key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{ti['key']}:{rank-1}:loss"),
        ]])
        await bot.send_message(
            chat_id=CHAT_ID,
            text=fmt_pick(rank, pick, bankroll),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.5)

    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "✅ *Scan termine !*\n\n"
            "Appuie sur WIN ou LOSS apres chaque match.\n"
            "L'IA apprend de chaque resultat 🧬\n\n"
            "/stats  /resultats  /bankroll"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    ti     = get_target()
    prefix = "demain" if ti["tmrw"] else "aujourd'hui"
    icon   = "🌙" if ti["tmrw"] else "☀️"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{icon} Scanner les matchs de {prefix}", callback_data="launch_scan")
    ]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"9 agents Groq Llama 3.3 70B\n"
        f"Matchs via API-Football — vrais matchs confirmes\n"
        f"Auto-apprentissage WIN/LOSS\n\n"
        f"*Commandes :*\n"
        f"/scan — Lancer le scan\n"
        f"/stats — Statistiques\n"
        f"/resultats — Paris en attente\n"
        f"/bankroll 150 — Changer la bankroll\n\n"
        f"Il est {ti['hour']}h — scan pour {prefix}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    db    = load_db()
    allp  = [p for s in db["scans"].values() for p in s["picks"]]
    dec   = [p for p in allp if p.get("result")]
    wins  = [p for p in dec  if p["result"] == "win"]
    bank  = db.get("bankroll", BANKROLL_DEF)
    wr    = round(len(wins) / len(dec) * 100) if dec else 0
    profit = sum(
        (bank * p.get("mp", 2) / 100) * p["cm"] - (bank * p.get("mp", 2) / 100)
        if p["result"] == "win" and p.get("cm")
        else -(bank * p.get("mp", 2) / 100)
        for p in dec
    )
    nb  = len(db.get("lessons", []))
    lvl = "Expert ⭐" if nb >= 20 else "Bon 🔥" if nb >= 10 else "En cours 📈"
    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joues : *{len(dec)}*\n"
        f"✅ Gagnes : *{len(wins)}*\n"
        f"❌ Perdus : *{len(dec) - len(wins)}*\n"
        f"📈 Win rate : *{wr}%*\n"
        f"💵 Profit : *{'+' if profit >= 0 else ''}{profit:.2f}€*\n\n"
        f"🧬 Lecons : *{nb}*  |  Niveau : *{lvl}*\n"
        f"💰 Bankroll : *{bank:.2f}€*",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    db      = load_db()
    pending = [
        (dk, i, p, s["date_label"])
        for dk, s in db["scans"].items()
        for i, p in enumerate(s["picks"])
        if not p.get("result")
    ]
    if not pending:
        await update.message.reply_text("✅ Tous les resultats ont ete saisis !")
        return
    await update.message.reply_text(
        f"⏳ *{len(pending)} paris en attente*",
        parse_mode=ParseMode.MARKDOWN
    )
    for dk, idx, pick, dlabel in pending[:10]:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
        ]])
        await update.message.reply_text(
            f"📅 {dlabel}\n"
            f"⚽ *{pick['home']} vs {pick['away']}*\n"
            f"🎯 {pick['pari']} ({pick['conf']}%)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.3)

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        amount = float(context.args[0])
        db = load_db()
        db["bankroll"] = amount
        save_db(db)
        await update.message.reply_text(
            f"💰 Bankroll mise a jour : *{amount:.2f}€*",
            parse_mode=ParseMode.MARKDOWN
        )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage : /bankroll 150")

# ── CALLBACKS WIN/LOSS ────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message.chat_id != CHAT_ID:
        return
    data = query.data

    if data == "launch_scan":
        db = load_db()
        await run_scan(context, db.get("bankroll", BANKROLL_DEF))
        return

    if data.startswith("res:"):
        _, dk, idx_s, result = data.split(":")
        idx = int(idx_s)
        db  = load_db()
        scan = db["scans"].get(dk)
        if not scan or idx >= len(scan["picks"]):
            return
        pick = scan["picks"][idx]
        prev = pick.get("result")
        pick["result"] = None if prev == result else result
        save_db(db)

        if pick["result"]:
            icon  = "✅" if pick["result"] == "win" else "❌"
            bank  = db.get("bankroll", BANKROLL_DEF)
            mise  = round(bank * pick.get("mp", 2) / 100, 2)
            cm    = pick.get("cm")
            g_str = f"+{round(mise*cm-mise,2)}€" if cm and pick["result"]=="win" else f"-{mise}€"
            try:
                await query.edit_message_text(
                    text=query.message.text + f"\n\n{icon} *{pick['result'].upper()}* — {g_str}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=None
                )
            except Exception:
                pass
            if not prev:
                await trigger_learning(pick, db, context)
        else:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
            ]])
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except Exception:
                pass

# ── AUTO-LEARNING ─────────────────────────────────────────────────────────────
async def trigger_learning(pick, db, context):
    try:
        won = pick["result"] == "win"
        lesson_text = await call_groq(
            "Systeme auto-amelioration paris sportifs. Francais, concis.",
            f"Pari resolu:\n"
            f"Match: {pick['home']} vs {pick['away']}\n"
            f"Pari: {pick['pari']} | Confiance: {pick['conf']}%\n"
            f"Resultat: {'GAGNE' if won else 'PERDU'}\n\n"
            f"Genere UNE lecon courte (2 phrases) pour ameliorer les prochaines analyses.",
            150
        )
        lesson = {
            "id":     int(datetime.now().timestamp()),
            "date":   datetime.now().strftime("%d/%m/%Y"),
            "match":  f"{pick['home']} vs {pick['away']}",
            "pari":   pick["pari"],
            "result": pick["result"],
            "text":   lesson_text.strip()
        }
        db.setdefault("lessons", [])
        db["lessons"].append(lesson)
        db["lessons"] = db["lessons"][-50:]
        save_db(db)
        icon = "🟢" if won else "🔴"
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"🧬 *Nouvelle lecon apprise !*\n\n"
                f"{icon} {pick['home']} vs {pick['away']} — "
                f"{'WIN' if won else 'LOSS'}\n\n"
                f"💡 {lesson_text.strip()}"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Learning: {e}")

# ── RAPPEL RÉSULTATS ──────────────────────────────────────────────────────────
async def remind_yesterday(context):
    db  = load_db()
    yd  = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    scan = db["scans"].get(yd)
    if not scan:
        return
    pending = [p for p in scan["picks"] if not p.get("result")]
    if not pending:
        return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⏰ *Resultats en attente — {yd}*\n\n"
            f"{len(pending)} paris sans resultat !\n"
            f"Tape /resultats pour les saisir"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

# ── SCAN AUTO ─────────────────────────────────────────────────────────────────
async def auto_scan(context):
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN manquant"); return
    if not GROQ_KEYS:
        logger.error("GROQ_KEYS manquantes"); return
    if not FOOTBALL_KEY:
        logger.error("FOOTBALL_KEY manquante"); return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("bankroll",  cmd_bankroll))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq = app.job_queue
    jq.run_daily(auto_scan,        time=datetime.strptime(f"{SCAN_HOUR:02d}:00",      "%H:%M").time(), name="scan")
    jq.run_daily(remind_yesterday, time=datetime.strptime(f"{(SCAN_HOUR+1)%24:02d}:00", "%H:%M").time(), name="remind")

    logger.info(f"Oracle Bot demarre — {len(GROQ_KEYS)} cles Groq — scan auto {SCAN_HOUR}h")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
