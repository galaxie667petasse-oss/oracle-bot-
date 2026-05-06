import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import google.generativeai as genai
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
GEMINI_KEY     = os.getenv("GEMINI_KEY", "")
GROQ_KEYS      = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]
SCAN_HOUR      = int(os.getenv("SCAN_HOUR", "9"))
DB_FILE        = Path("oracle_db.json")

# ── KEY ROTATION GROQ ─────────────────────────────────────────────────────────
groq_index = 0

def next_groq_key() -> str:
    global groq_index
    if not GROQ_KEYS:
        raise ValueError("Aucune clé GROQ configurée !")
    k = GROQ_KEYS[groq_index % len(GROQ_KEYS)]
    groq_index += 1
    return k

# ── DATABASE ──────────────────────────────────────────────────────────────────
def load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scans": {}, "lessons": [], "bankroll": 100.0}

def save_db(db: dict):
    DB_FILE.write_text(
        json.dumps(db, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

# ── SMART DATE ────────────────────────────────────────────────────────────────
def get_target_date() -> dict:
    """Retourne la date cible selon l'heure actuelle."""
    now = datetime.now()
    h = now.hour
    # Après 21h → matchs de demain
    if h >= 21:
        target = now + timedelta(days=1)
        is_tomorrow = True
    else:
        target = now
        is_tomorrow = False

    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS  = ["janvier","février","mars","avril","mai","juin",
             "juillet","août","septembre","octobre","novembre","décembre"]
    label = f"{JOURS[target.weekday()]} {target.day} {MOIS[target.month-1]} {target.year}"
    date_key = target.strftime("%d/%m/%Y")

    return {
        "label": label,
        "date_key": date_key,
        "is_tomorrow": is_tomorrow,
        "hour": h,
    }

# ── GEMINI — RECHERCHE MATCHS ─────────────────────────────────────────────────
async def fetch_matches_gemini(date_label: str) -> list:
    """Utilise Gemini + Google Search pour trouver les vrais matchs du jour."""
    genai.configure(api_key=GEMINI_KEY)

    prompt = (
        f"Recherche sur le web les matchs de football officiellement programmés "
        f"le {date_label}.\n\n"
        f"RÈGLES ABSOLUES :\n"
        f"1. UNIQUEMENT les matchs confirmés via recherche web pour le {date_label}\n"
        f"2. Ne JAMAIS inventer un match\n"
        f"3. Ne PAS inclure des matchs déjà joués\n"
        f"4. Inclure la date ET l'heure exacte (heure française)\n"
        f"5. Si moins de 5 matchs trouvés, retourner uniquement ceux confirmés\n\n"
        f"Compétitions : Ligue 1, Premier League, La Liga, Serie A, Bundesliga, "
        f"Champions League, Europa League, Conference League, Ligue 2, Championship, "
        f"Eredivisie, Primeira Liga, Super Lig et toutes autres ligues actives ce jour.\n\n"
        f"Retourne UNIQUEMENT ce JSON valide (rien d'autre, 12 matchs max) :\n"
        f'{{"matches":['
        f'{{"home":"Equipe A","away":"Equipe B","competition":"Ligue 1",'
        f'"date":"{date_label}","heure":"20:45","cote_home":1.85,'
        f'"cote_draw":3.40,"cote_away":4.20,'
        f'"contexte":"forme récente, blessés confirmés, enjeux du match"}}'
        f']}}\n\n'
        f"ZERO invention. ZERO match fictif. Uniquement matchs RÉELS et CONFIRMÉS."
    )

    matches = []
    for attempt in range(4):
        try:
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                tools="google_search_retrieval"
            )
            response = await asyncio.to_thread(
                lambda: model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        max_output_tokens=2000,
                        temperature=0.3,
                    )
                )
            )
            raw = response.text.strip()

            import re
            for fn in [
                lambda: json.loads(raw),
                lambda: json.loads(re.search(r"```(?:json)?\s*([\s\S]*?)```", raw).group(1).strip()),
                lambda: json.loads(re.search(r'(\{[\s\S]*?"matches"\s*:\s*\[[\s\S]*?\]\s*\})', raw).group(1)),
            ]:
                try:
                    p = fn()
                    if p and p.get("matches"):
                        matches = p["matches"]
                        break
                except Exception:
                    pass

            if matches:
                break

            # Si parsing échoué, demander reformatage
            if attempt < 3:
                reformat_model = genai.GenerativeModel("gemini-1.5-flash")
                reformat_resp = await asyncio.to_thread(
                    lambda: reformat_model.generate_content(
                        f"Reformate ces données en JSON exact sans texte autour :\n"
                        f'{{"matches":[{{"home":"X","away":"Y","competition":"Z",'
                        f'"date":"{date_label}","heure":"HH:MM","cote_home":1.8,'
                        f'"cote_draw":3.5,"cote_away":4.0,"contexte":"infos"}}]}}\n\n'
                        f"Données brutes :\n{raw[:3000]}",
                        generation_config=genai.GenerationConfig(max_output_tokens=2000)
                    )
                )
                rt = reformat_resp.text.strip()
                for fn in [
                    lambda: json.loads(rt),
                    lambda: json.loads(re.search(r'(\{[\s\S]*?"matches"[\s\S]*?\]\s*\})', rt).group(1)),
                ]:
                    try:
                        p = fn()
                        if p and p.get("matches"):
                            matches = p["matches"]
                            break
                    except Exception:
                        pass
                if matches:
                    break

        except Exception as e:
            logger.warning(f"Gemini attempt {attempt+1}: {e}")
            await asyncio.sleep(3)

    return matches

# ── GROQ — AGENTS ─────────────────────────────────────────────────────────────
async def call_groq(system: str, user: str, max_tokens: int = 400) -> str:
    """Appel API Groq avec rotation des clés et retry."""
    for attempt in range(4):
        try:
            client = Groq(api_key=next_groq_key())
            response = await asyncio.to_thread(
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
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1}: {e}")
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep((attempt + 1) * 6)
            elif attempt == 3:
                raise
            else:
                await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible après 4 tentatives")

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {"id": "tact",   "name": "Tacticien",        "emoji": "🧠",
     "sys": "Expert tacticien football. Formations, pressing, transitions, duels. 80 mots max en français."},
    {"id": "stat",   "name": "Statisticien",      "emoji": "📊",
     "sys": "Analyste statistique football. Forme, H2H, buts, xG, probabilités. 80 mots max en français."},
    {"id": "doc",    "name": "Médecin",            "emoji": "🏃",
     "sys": "Médecin sportif. Fatigue, blessures, rotations. 80 mots max en français."},
    {"id": "scout",  "name": "L'Ancien",           "emoji": "🧓",
     "sys": "Scout légendaire 40 ans. Patterns cachés, équipes pièges. 80 mots max en français."},
    {"id": "market", "name": "Analyste Marché",    "emoji": "💰",
     "sys": "Expert value betting. Probabilité implicite, value bets. 80 mots max en français."},
    {"id": "psycho", "name": "Psychologue",         "emoji": "🎭",
     "sys": "Psychologue sport. Enjeux, pression, motivation. 80 mots max en français."},
    {"id": "juge",   "name": "Juge Arbitre",        "emoji": "⚖️",
     "sys": "Juge Arbitre. Synthétise les 6 rapports. 120 mots max en français."},
    {"id": "prof1",  "name": "Prof. Pragmatique",   "emoji": "🎓",
     "sys": "Professeur Pragmatique. Identifie failles, réaliste. 100 mots max en français."},
    {"id": "prof2",  "name": "Prof. Visionnaire",   "emoji": "🔭", "sys": ""},
]

def build_prof2_sys(lessons: list) -> str:
    base = (
        "Professeur Visionnaire. Analyse courte (60 mots max), puis VERDICT FINAL "
        "OBLIGATOIRE dans ce format exact (sans astérisques) :\n\n"
        "PARI: [ex: Victoire Lyon / Plus de 2.5 buts / BTTS Oui]\n"
        "CONFIANCE: [chiffre 0-100]\n"
        "MISE_PCT: [chiffre 1-5]\n"
        "COTE_MINI: [chiffre décimal ex: 1.75]\n"
        "RISQUE: [une phrase]\n"
        "RESUME: [3 phrases pourquoi ce pari]"
    )
    if lessons:
        base += "\n\nLEÇONS APPRISES (applique-les) :\n"
        base += "\n".join(f"- {l['text']}" for l in lessons[-6:])
    return base

def parse_verdict(text: str) -> dict:
    import re
    if not text:
        return {"pari": "Non disponible", "conf": 50, "mp": 2, "cm": None, "risque": "", "resume": ""}
    t = re.sub(r"\*+", "", text)
    t = re.sub(r"^#+[^\n]*", "", t, flags=re.MULTILINE)

    def g(pattern, fallback=""):
        m = re.search(pattern, t, re.IGNORECASE)
        return m.group(1).strip() if m else fallback

    conf_str = g(r"CONFIANCE\s*:\s*(\d+)", "50")
    mp_str   = g(r"MISE_PCT\s*:\s*(\d+)", "2")
    cm_str   = g(r"COTE[_\s]*MINI\s*:\s*([\d.,]+)", "0").replace(",", ".")

    return {
        "pari":   g(r"PARI\s*:\s*([^\n]+)", "Voir analyse"),
        "conf":   min(100, max(0, int(conf_str) if conf_str.isdigit() else 50)),
        "mp":     min(5,   max(1, int(mp_str)   if mp_str.isdigit()   else 2)),
        "cm":     float(cm_str) if cm_str and cm_str != "0" else None,
        "risque": g(r"RISQUE\s*:\s*([^\n]+)", ""),
        "resume": g(r"RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|$)", ""),
    }

# ── ANALYZE ONE MATCH ─────────────────────────────────────────────────────────
async def analyze_match(match: dict, lessons: list, progress_cb) -> dict:
    base = (
        f"{match['home']} vs {match['away']} | "
        f"{match.get('competition','')} | {match.get('heure','?')}h\n"
        f"Cotes : Dom {match.get('cote_home','?')} | "
        f"Nul {match.get('cote_draw','?')} | "
        f"Ext {match.get('cote_away','?')}\n"
        f"Contexte : {match.get('contexte','Pas d info')}"
    )
    reports = {}
    AGENTS[8]["sys"] = build_prof2_sys(lessons)

    for ag in AGENTS[:6]:
        await progress_cb(ag["id"], "run")
        try:
            reports[ag["id"]] = await call_groq(
                ag["sys"],
                f"{base}\n\nAnalyse experte en 80 mots.",
                220
            )
        except Exception as e:
            reports[ag["id"]] = f"Indisponible ({e})"
        await progress_cb(ag["id"], "done")

    all_r = "\n\n".join(
        f"[{AGENTS[i]['emoji']} {AGENTS[i]['name']}]\n{reports[AGENTS[i]['id']]}"
        for i in range(6)
    )

    await progress_cb("juge", "run")
    try:
        reports["juge"] = await call_groq(
            AGENTS[6]["sys"],
            f"{base}\n\n--- RAPPORTS ---\n{all_r}\n\nSynthèse.",
            280
        )
    except Exception as e:
        reports["juge"] = f"Erreur ({e})"
    await progress_cb("juge", "done")

    await progress_cb("prof1", "run")
    try:
        reports["prof1"] = await call_groq(
            AGENTS[7]["sys"],
            f"{base}\n\nJUGE:\n{reports['juge']}\n\nCorrige.",
            220
        )
    except Exception as e:
        reports["prof1"] = f"Erreur ({e})"
    await progress_cb("prof1", "done")

    await progress_cb("prof2", "run")
    try:
        reports["prof2"] = await call_groq(
            AGENTS[8]["sys"],
            f"{base}\n\nJUGE:\n{reports['juge']}\n\nPRAGMATIQUE:\n{reports['prof1']}\n\nVERDICT FINAL obligatoire.",
            500
        )
    except Exception as e:
        reports["prof2"] = f"Erreur ({e})"
    await progress_cb("prof2", "done")

    return {
        "match":   match,
        "reports": reports,
        "verdict": parse_verdict(reports.get("prof2", ""))
    }

# ── FORMAT PICK ───────────────────────────────────────────────────────────────
def conf_bar(conf: int) -> str:
    filled = round(conf / 10)
    return "█" * filled + "░" * (10 - filled) + f" {conf}%"

def format_pick(rank: int, pick: dict, bankroll: float) -> str:
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    medal  = medals[rank - 1] if rank <= 5 else f"#{rank}"

    home   = pick.get("home",  "?")
    away   = pick.get("away",  "?")
    comp   = pick.get("comp",  "")
    heure  = pick.get("heure", "")
    date   = pick.get("date",  "")
    ch     = pick.get("ch", "?")
    cd     = pick.get("cd", "?")
    ca     = pick.get("ca", "?")
    pari   = pick.get("pari",   "—")
    conf   = pick.get("conf",   50)
    mp     = pick.get("mp",     2)
    cm     = pick.get("cm",     None)
    risque = pick.get("risque", "")
    resume = pick.get("resume", "")

    mise = round(bankroll * mp / 100, 2)
    gain = round(mise * cm, 2) if cm else None
    ben  = round(gain - mise, 2) if gain else None

    lines = [
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}" + (f"  ⏰ {heure}" if heure else "") + (f"  📅 {date}" if date else ""),
        "",
        f"🎯 *PARI : {pari}*",
        f"📊 `{conf_bar(conf)}`",
        "",
        f"💰 Mise : *{mise}€*  \\({mp}% bankroll\\)",
    ]
    if cm:
        lines += [
            f"⚡ Cote mini : *{cm}*",
            f"🎁 Gain total : *{gain}€*  \\(\\+{ben}€ net\\)",
            f"📐 `{mise}€ × {cm} = {gain}€`",
        ]
    if risque:
        lines += ["", f"⚠️ _Risque : {risque}_"]
    if resume:
        lines += ["", f"📝 *Pourquoi :*", f"_{resume}_"]
    lines += ["", f"Cotes → Dom *{ch}* | Nul *{cd}* | Ext *{ca}*"]

    return "\n".join(lines)

# ── SCAN PRINCIPAL ────────────────────────────────────────────────────────────
async def run_scan(context: ContextTypes.DEFAULT_TYPE, bankroll: float):
    bot = context.bot
    db  = load_db()
    ti  = get_target_date()

    prefix = "DEMAIN" if ti["is_tomorrow"] else "AUJOURD'HUI"
    icon   = "🌙" if ti["is_tomorrow"] else "☀️"

    # Message de départ avec bouton ANNULER
    start_msg = await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⚽ *ORACLE — SCAN {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"🔍 Gemini recherche les matchs confirmés...\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    # Fetch matchs via Gemini
    matches = await fetch_matches_gemini(ti["label"])

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=start_msg.message_id,
            text=(
                f"⚽ *ORACLE — {ti['label']}*\n\n"
                f"❌ Aucun match confirmé trouvé\\.\n"
                f"Réessaie avec /scan dans quelques minutes\\."
            ),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    to_analyze = matches[:10]

    await bot.edit_message_text(
        chat_id=CHAT_ID,
        message_id=start_msg.message_id,
        text=(
            f"⚽ *ORACLE — {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"✅ *{len(matches)} matchs confirmés* par Gemini\\+Google\n"
            f"🔬 Analyse de {len(to_analyze)} matchs par 9 agents Groq\\.\\.\\.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN_V2
    )

    lessons = db.get("lessons", [])
    results = []

    # Analyse chaque match
    for i, match in enumerate(to_analyze):
        match_name = f"{match['home']} vs {match['away']}"

        # Message progression
        prog_msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=build_progress_text(i, len(to_analyze), match_name,
                                     match.get("competition",""), {}, 0),
            parse_mode=ParseMode.MARKDOWN
        )

        states = {ag["id"]: "wait" for ag in AGENTS}
        steps  = [0]

        async def progress_cb(ag_id, status,
                               _states=states, _steps=steps,
                               _msg=prog_msg, _name=match_name,
                               _comp=match.get("competition",""),
                               _i=i, _total=len(to_analyze)):
            if status == "run":
                _states[ag_id] = "run"
            elif status == "done":
                _states[ag_id] = "done"
                _steps[0] += 1

            pct = round(_steps[0] / 9 * 100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=_msg.message_id,
                    text=build_progress_text(_i, _total, _name, _comp, _states, pct),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass

        try:
            result = await analyze_match(match, lessons, progress_cb)
            results.append(result)
            v = result["verdict"]

            # Verdict final du match
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=(
                    f"✅ *{i+1}/{len(to_analyze)} — Analysé*\n"
                    f"⚽ {match_name}\n\n"
                    f"`{'█'*10}  100%`\n\n"
                    f"🎯 *{v['pari']}*\n"
                    f"📊 Confiance : {v['conf']}%\n"
                    f"⚡ Cote mini : {v['cm'] or '—'}"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur {match_name}: {e}")
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=f"❌ Erreur sur {match_name}",
            )

        await asyncio.sleep(1)

    # Trier → Top 5
    results.sort(key=lambda x: x["verdict"]["conf"], reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Aucune analyse complétée. Réessaie avec /scan.",
        )
        return

    # Sauvegarder
    scan_entry = {
        "date_key":   ti["date_key"],
        "date_label": ti["label"],
        "is_tomorrow": ti["is_tomorrow"],
        "timestamp":  datetime.now().isoformat(),
        "bankroll":   bankroll,
        "picks": [
            {
                "home":  r["match"]["home"],
                "away":  r["match"]["away"],
                "comp":  r["match"].get("competition", ""),
                "date":  r["match"].get("date", ti["label"]),
                "heure": r["match"].get("heure", ""),
                "ch":    r["match"].get("cote_home"),
                "cd":    r["match"].get("cote_draw"),
                "ca":    r["match"].get("cote_away"),
                **r["verdict"],
                "result": None,
            }
            for r in top5
        ]
    }
    db["scans"][ti["date_key"]] = scan_entry
    save_db(db)

    # Envoyer le Top 5
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"🏆 *TOP {len(top5)} PARIS — {prefix}*\n"
            f"{icon} {ti['label']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )
    await asyncio.sleep(0.5)

    for rank, r in enumerate(top5, 1):
        pick_data = {
            "home":  r["match"]["home"],
            "away":  r["match"]["away"],
            "comp":  r["match"].get("competition",""),
            "date":  r["match"].get("date", ti["label"]),
            "heure": r["match"].get("heure",""),
            "ch":    r["match"].get("cote_home"),
            "cd":    r["match"].get("cote_draw"),
            "ca":    r["match"].get("cote_away"),
            **r["verdict"],
        }
        text = format_pick(rank, pick_data, bankroll)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{ti['date_key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{ti['date_key']}:{rank-1}:loss"),
        ]])
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.5)

    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"✅ *Scan terminé !*\n\n"
            f"Appuie sur WIN ou LOSS après chaque match\\.  \n"
            f"L'IA apprend de chaque résultat 🧬\n\n"
            f"/stats · /resultats · /bankroll"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

# ── BARRE DE PROGRESSION ─────────────────────────────────────────────────────
def build_progress_text(i, total, match_name, comp, states, pct):
    filled = round(pct / 10)
    bar    = "█" * filled + "░" * (10 - filled)

    def line(ag_id, emoji, name):
        s = states.get(ag_id, "wait")
        icon = "✅" if s == "done" else "⚡" if s == "run" else "⏳"
        return f"{emoji} {name:<18} {icon}"

    return "\n".join([
        f"🔬 *Match {i+1}/{total}*",
        f"⚽ {match_name}",
        f"🏆 {comp}",
        "",
        f"`{bar}  {pct}%`",
        "",
        line("tact",   "🧠", "Tacticien"),
        line("stat",   "📊", "Statisticien"),
        line("doc",    "🏃", "Médecin"),
        line("scout",  "🧓", "L'Ancien"),
        line("market", "💰", "Analyste Marché"),
        line("psycho", "🎭", "Psychologue"),
        line("juge",   "⚖️", "Juge Arbitre"),
        line("prof1",  "🎓", "Prof. Pragmatique"),
        line("prof2",  "🔭", "Prof. Visionnaire"),
    ])

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    ti = get_target_date()
    prefix = "demain" if ti["is_tomorrow"] else "aujourd'hui"
    icon   = "🌙" if ti["is_tomorrow"] else "☀️"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"{icon} Scanner les matchs de {prefix}",
            callback_data="launch_scan"
        )
    ]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 9 agents IA · Groq Llama 3.3 70B\n"
        f"🔍 Recherche matchs · Gemini + Google\n"
        f"🧬 Auto\\-apprentissage · WIN/LOSS\n\n"
        f"*Commandes :*\n"
        f"/scan — Lancer le scan\n"
        f"/stats — Statistiques\n"
        f"/resultats — Paris en attente\n"
        f"/bankroll 150 — Changer la bankroll\n\n"
        f"Il est *{ti['hour']}h* — prochain scan pour *{prefix}*",
        parse_mode=ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    db = load_db()
    await run_scan(context, db.get("bankroll", 100.0))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    db        = load_db()
    all_picks = [p for s in db["scans"].values() for p in s["picks"]]
    decided   = [p for p in all_picks if p.get("result")]
    wins      = [p for p in decided if p["result"] == "win"]
    losses    = [p for p in decided if p["result"] == "loss"]
    wr        = round(len(wins) / len(decided) * 100) if decided else 0
    bankroll  = db.get("bankroll", 100.0)
    profit    = 0.0
    for p in decided:
        m = bankroll * p.get("mp", 2) / 100
        if p["result"] == "win" and p.get("cm"):
            profit += m * p["cm"] - m
        elif p["result"] == "loss":
            profit -= m
    nb_les = len(db.get("lessons", []))
    level  = "Expert ⭐" if nb_les >= 20 else "Bon 🔥" if nb_les >= 10 else "En cours 📈"

    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joués : *{len(decided)}*\n"
        f"✅ Gagnés : *{len(wins)}*\n"
        f"❌ Perdus : *{len(losses)}*\n"
        f"📈 Win rate : *{wr}%*\n"
        f"💵 Profit : *{'+' if profit >= 0 else ''}{profit:.2f}€*\n\n"
        f"🧬 Leçons : *{nb_les}*  \\|  Niveau : *{level}*\n"
        f"💰 Bankroll : *{bankroll:.2f}€*",
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
        await update.message.reply_text("✅ Tous les résultats ont été saisis !")
        return

    await update.message.reply_text(
        f"⏳ *{len(pending)} paris en attente*",
        parse_mode=ParseMode.MARKDOWN
    )
    for dk, idx, pick, date_label in pending[:10]:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
        ]])
        await update.message.reply_text(
            f"📅 _{date_label}_\n"
            f"⚽ *{pick['home']} vs {pick['away']}*\n"
            f"🎯 {pick['pari']}  \\({pick['conf']}%\\)",
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
            f"💰 Bankroll mise à jour : *{amount:.2f}€*",
            parse_mode=ParseMode.MARKDOWN
        )
    except (IndexError, ValueError):
        await update.message.reply_text("Usage : /bankroll 150")

# ── CALLBACK BOUTONS ──────────────────────────────────────────────────────────
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.message.chat_id != CHAT_ID:
        return

    data = query.data

    # Bouton lancer scan
    if data == "launch_scan":
        db = load_db()
        await run_scan(context, db.get("bankroll", 100.0))
        return

    # Bouton WIN/LOSS
    if data.startswith("res:"):
        _, date_key, idx_str, result = data.split(":")
        idx = int(idx_str)
        db  = load_db()
        scan = db["scans"].get(date_key)
        if not scan or idx >= len(scan["picks"]):
            return

        pick     = scan["picks"][idx]
        prev     = pick.get("result")
        pick["result"] = None if prev == result else result
        save_db(db)

        if pick["result"]:
            icon     = "✅" if pick["result"] == "win" else "❌"
            bankroll = db.get("bankroll", 100.0)
            mise     = round(bankroll * pick.get("mp", 2) / 100, 2)
            cm       = pick.get("cm")
            gain_str = f"+{round(mise*cm-mise,2)}€" if cm and pick["result"] == "win" else f"-{mise}€"

            try:
                await query.edit_message_text(
                    text=f"{query.message.text}\n\n{icon} *{pick['result'].upper()}* enregistré · {gain_str}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=None
                )
            except Exception:
                pass

            if not prev:
                await trigger_learning(pick, db, context)
        else:
            # Dé-toggle → remettre boutons
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ WIN",  callback_data=f"res:{date_key}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"res:{date_key}:{idx}:loss"),
            ]])
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
            except Exception:
                pass

# ── AUTO-LEARNING ─────────────────────────────────────────────────────────────
async def trigger_learning(pick: dict, db: dict, context: ContextTypes.DEFAULT_TYPE):
    try:
        won    = pick["result"] == "win"
        prompt = (
            f"Pari résolu :\n"
            f"Match : {pick['home']} vs {pick['away']} ({pick.get('comp','')})\n"
            f"Pari : {pick['pari']} | Confiance : {pick['conf']}%\n"
            f"Résultat : {'GAGNÉ' if won else 'PERDU'}\n\n"
            f"Génère UNE leçon courte (2 phrases max) pour améliorer les prochaines analyses. "
            f"{'Qu est-ce qui a bien fonctionné ?' if won else 'Qu est-il faillé éviter ?'}\n"
            f"Réponds uniquement avec la leçon en français."
        )
        lesson_text = await call_groq(
            "Système auto-amélioration paris sportifs. Français, concis.",
            prompt, 150
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
                f"🧬 *Nouvelle leçon apprise !*\n\n"
                f"{icon} {pick['home']} vs {pick['away']} → "
                f"{'WIN' if won else 'LOSS'}\n\n"
                f"💡 _{lesson_text.strip()}_"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Learning error: {e}")

# ── RAPPEL RÉSULTATS ─────────────────────────────────────────────────────────
async def remind_yesterday(context: ContextTypes.DEFAULT_TYPE):
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
            f"⏰ *Résultats en attente — {yd}*\n\n"
            f"{len(pending)} paris sans résultat \\!\n"
            f"Tape /resultats pour les saisir 👇"
        ),
        parse_mode=ParseMode.MARKDOWN_V2
    )

# ── SCAN AUTO ─────────────────────────────────────────────────────────────────
async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    await run_scan(context, db.get("bankroll", 100.0))

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN manquant dans .env")
        return
    if not GEMINI_KEY:
        logger.error("GEMINI_KEY manquante dans .env")
        return
    if not GROQ_KEYS:
        logger.error("GROQ_KEYS manquantes dans .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("bankroll",  cmd_bankroll))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq: JobQueue = app.job_queue
    jq.run_daily(
        auto_scan,
        time=datetime.strptime(f"{SCAN_HOUR:02d}:00", "%H:%M").time(),
        name="daily_scan"
    )
    remind_h = (SCAN_HOUR + 1) % 24
    jq.run_daily(
        remind_yesterday,
        time=datetime.strptime(f"{remind_h:02d}:00", "%H:%M").time(),
        name="remind"
    )

    logger.info(f"Oracle Bot démarré — scan auto à {SCAN_HOUR}h · {len(GROQ_KEYS)} clés Groq")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
