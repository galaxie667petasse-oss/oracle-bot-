import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, JobQueue
)
from telegram.constants import ParseMode

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TON_TOKEN_ICI")
CHAT_ID        = int(os.getenv("CHAT_ID", "TON_CHAT_ID_ICI"))
GROQ_KEYS      = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]
SCAN_HOUR      = int(os.getenv("SCAN_HOUR", "9"))   # heure du scan auto
DB_FILE        = Path("oracle_db.json")

# ── KEY ROTATION ──────────────────────────────────────────────────────────────
key_index = 0

def next_key():
    global key_index
    if not GROQ_KEYS:
        raise ValueError("Aucune clé GROQ configurée !")
    k = GROQ_KEYS[key_index % len(GROQ_KEYS)]
    key_index += 1
    return k

# ── DATABASE ──────────────────────────────────────────────────────────────────
def load_db() -> dict:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scans": {}, "lessons": []}

def save_db(db: dict):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

# ── GROQ CALL ─────────────────────────────────────────────────────────────────
async def call_groq(system: str, user: str, max_tokens: int = 400) -> str:
    """Appel API Groq avec retry automatique."""
    for attempt in range(4):
        try:
            client = Groq(api_key=next_key())
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
            logger.warning(f"Groq attempt {attempt+1} failed: {e}")
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep((attempt + 1) * 6)
            elif attempt == 3:
                raise
            else:
                await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible après 4 tentatives")

# ── AGENTS ────────────────────────────────────────────────────────────────────
AGENTS = [
    {
        "id": "tact",
        "name": "Tacticien",
        "emoji": "🧠",
        "sys": "Expert tacticien football. Formations, pressing, transitions, duels. Analyse en 80 mots max en français."
    },
    {
        "id": "stat",
        "name": "Statisticien",
        "emoji": "📊",
        "sys": "Analyste statistique football. Forme récente, H2H, buts, xG, probabilités. 80 mots max en français."
    },
    {
        "id": "doc",
        "name": "Médecin",
        "emoji": "🏃",
        "sys": "Médecin sportif. Fatigue, blessures connues, rotations probables. 80 mots max en français."
    },
    {
        "id": "scout",
        "name": "L'Ancien Scout",
        "emoji": "🧓",
        "sys": "Scout légendaire 40 ans terrain. Patterns cachés, équipes pièges, tendances longues. 80 mots max en français."
    },
    {
        "id": "market",
        "name": "Analyste Marché",
        "emoji": "💰",
        "sys": "Expert value betting. Probabilité implicite des cotes, value bets, biais bookmaker. 80 mots max en français."
    },
    {
        "id": "psycho",
        "name": "Psychologue",
        "emoji": "🎭",
        "sys": "Psychologue sport. Enjeux, pression, motivation, derby, fatigue mentale. 80 mots max en français."
    },
    {
        "id": "juge",
        "name": "Juge Arbitre",
        "emoji": "⚖️",
        "sys": "Juge Arbitre. Synthétise les 6 rapports en consensus clair. 120 mots max en français."
    },
    {
        "id": "prof1",
        "name": "Prof. Pragmatique",
        "emoji": "🎓",
        "sys": "Professeur Pragmatique, 40 ans d'analyse. Identifie les failles, réaliste et critique. 100 mots max en français."
    },
    {
        "id": "prof2",
        "name": "Prof. Visionnaire",
        "emoji": "🔭",
        "sys": ""  # Rempli dynamiquement avec les leçons
    },
]

def build_prof2_sys(lessons: list) -> str:
    base = (
        "Professeur Visionnaire. Analyse courte (60 mots max), puis VERDICT FINAL OBLIGATOIRE "
        "dans ce format exact (sans astérisques ni markdown) :\n\n"
        "PARI: [ex: Victoire Lyon / Plus de 2.5 buts / BTTS Oui]\n"
        "CONFIANCE: [chiffre 0-100]\n"
        "MISE_PCT: [chiffre 1-5]\n"
        "COTE_MINI: [chiffre décimal ex: 1.75]\n"
        "RISQUE: [une phrase]\n"
        "RESUME: [3 phrases pourquoi ce pari]"
    )
    if lessons:
        recent = lessons[-6:]
        base += "\n\nLEÇONS APPRISES (applique-les impérativement) :\n"
        base += "\n".join(f"- {l['text']}" for l in recent)
    return base

# ── PARSE VERDICT ─────────────────────────────────────────────────────────────
def parse_verdict(text: str) -> dict:
    if not text:
        return {"pari": "Non disponible", "conf": 50, "mp": 2, "cm": None, "risque": "", "resume": ""}
    import re
    t = re.sub(r"\*+", "", text)
    t = re.sub(r"^#+[^\n]*", "", t, flags=re.MULTILINE)

    def g(pattern, fallback=""):
        m = re.search(pattern, t, re.IGNORECASE)
        return m.group(1).strip() if m else fallback

    conf_raw  = g(r"CONFIANCE\s*:\s*(\d+)", "50")
    mp_raw    = g(r"MISE_PCT\s*:\s*(\d+)", "2")
    cm_raw    = g(r"COTE[_\s]*MINI\s*:\s*([\d.,]+)", "0").replace(",", ".")

    return {
        "pari":   g(r"PARI\s*:\s*([^\n]+)", "Voir analyse"),
        "conf":   min(100, max(0, int(conf_raw) if conf_raw.isdigit() else 50)),
        "mp":     min(5,   max(1, int(mp_raw)   if mp_raw.isdigit()   else 2)),
        "cm":     float(cm_raw) if cm_raw and cm_raw != "0" else None,
        "risque": g(r"RISQUE\s*:\s*([^\n]+)", ""),
        "resume": g(r"RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|$)", ""),
    }

# ── FETCH MATCHES ─────────────────────────────────────────────────────────────
async def fetch_matches(date_label: str) -> list:
    """Récupère les matchs du jour — uniquement ceux confirmés pour cette date."""
    prompt = (
        f"Tu es un expert du calendrier football européen saison 2025-2026.\n"
        f"La date est : {date_label}\n\n"
        f"Liste UNIQUEMENT les matchs de football officiellement programmés pour AUJOURD'HUI {date_label}.\n"
        f"Toutes ligues confondues : Ligue 1, Premier League, La Liga, Serie A, Bundesliga, "
        f"Ligue des Champions, Europa League, Conference League, Ligue 2, Championship, "
        f"Eredivisie, Primeira Liga, Super Lig, etc.\n\n"
        f"RÈGLES STRICTES :\n"
        f"1. UNIQUEMENT les matchs du {date_label} — ni hier, ni demain\n"
        f"2. N'invente AUCUN match — si tu n'es pas sûr, ne l'inclus pas\n"
        f"3. Inclus l'heure exacte (heure française)\n"
        f"4. Maximum 12 matchs, les plus importants en premier\n\n"
        f"Retourne UNIQUEMENT ce JSON valide (rien d'autre) :\n"
        f'{{"matches":[{{'
        f'"home":"Equipe A","away":"Equipe B","competition":"Ligue 1",'
        f'"heure":"20:45","cote_home":1.85,"cote_draw":3.40,"cote_away":4.20,'
        f'"contexte":"forme, blessés connus, enjeux"'
        f'}}]}}'
    )

    matches = []
    for attempt in range(4):
        try:
            raw = await call_groq(
                "Expert football 2025-2026. Réponds UNIQUEMENT en JSON valide sans markdown ni texte.",
                prompt,
                max_tokens=2000
            )
            # Tentatives de parsing
            import re
            for fn in [
                lambda: json.loads(raw.strip()),
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
        except Exception as e:
            logger.warning(f"fetchMatches attempt {attempt+1}: {e}")
            await asyncio.sleep(3)

    return matches

# ── ANALYZE ONE MATCH ─────────────────────────────────────────────────────────
async def analyze_match(match: dict, lessons: list, progress_cb) -> dict:
    """Analyse un match avec les 9 agents."""
    base = (
        f"{match['home']} vs {match['away']} | {match['competition']} | {match.get('heure','?')}h\n"
        f"Cotes : Dom {match.get('cote_home','?')} | Nul {match.get('cote_draw','?')} | "
        f"Ext {match.get('cote_away','?')}\n"
        f"Contexte : {match.get('contexte','Pas d info')}"
    )
    reports = {}
    AGENTS[8]["sys"] = build_prof2_sys(lessons)

    # 6 agents spécialistes
    for ag in AGENTS[:6]:
        await progress_cb(ag["emoji"], ag["name"], "run")
        try:
            reports[ag["id"]] = await call_groq(ag["sys"], f"{base}\n\nAnalyse experte en 80 mots.", 220)
        except Exception as e:
            reports[ag["id"]] = f"Indisponible ({e})"
        await progress_cb(ag["emoji"], ag["name"], "done")
        await asyncio.sleep(0.3)

    all_reports = "\n\n".join(
        f"[{AGENTS[i]['emoji']} {AGENTS[i]['name']}]\n{reports[AGENTS[i]['id']]}"
        for i in range(6)
    )

    # Juge
    await progress_cb("⚖️", "Juge Arbitre", "run")
    try:
        reports["juge"] = await call_groq(
            AGENTS[6]["sys"],
            f"{base}\n\n--- RAPPORTS ---\n{all_reports}\n\nSynthèse.",
            280
        )
    except Exception as e:
        reports["juge"] = f"Erreur ({e})"
    await progress_cb("⚖️", "Juge Arbitre", "done")

    # Prof Pragmatique
    await progress_cb("🎓", "Prof. Pragmatique", "run")
    try:
        reports["prof1"] = await call_groq(
            AGENTS[7]["sys"],
            f"{base}\n\nJUGE:\n{reports['juge']}\n\nCorrige et identifie les failles.",
            220
        )
    except Exception as e:
        reports["prof1"] = f"Erreur ({e})"
    await progress_cb("🎓", "Prof. Pragmatique", "done")

    # Prof Visionnaire + Verdict
    await progress_cb("🔭", "Prof. Visionnaire", "run")
    try:
        reports["prof2"] = await call_groq(
            AGENTS[8]["sys"],
            f"{base}\n\nJUGE:\n{reports['juge']}\n\nPRAGMATIQUE:\n{reports['prof1']}\n\nVERDICT FINAL obligatoire.",
            500
        )
    except Exception as e:
        reports["prof2"] = f"Erreur ({e})"
    await progress_cb("🔭", "Prof. Visionnaire", "done")

    return {
        "match": match,
        "reports": reports,
        "verdict": parse_verdict(reports.get("prof2", ""))
    }

# ── FORMAT MESSAGES ───────────────────────────────────────────────────────────
def conf_bar(conf: int) -> str:
    filled = round(conf / 10)
    return "█" * filled + "░" * (10 - filled) + f" {conf}%"

def format_pick(rank: int, pick: dict, bankroll: float) -> str:
    v = pick.get("verdict", pick)  # compatibilité DB
    pari   = v.get("pari",   pick.get("pari",   "—"))
    conf   = v.get("conf",   pick.get("conf",   50))
    mp     = v.get("mp",     pick.get("mp",     2))
    cm     = v.get("cm",     pick.get("cm",     None))
    risque = v.get("risque", pick.get("risque", ""))
    resume = v.get("resume", pick.get("resume", ""))

    m = pick.get("match", pick)
    home  = m.get("home",        pick.get("home",  "?"))
    away  = m.get("away",        pick.get("away",  "?"))
    comp  = m.get("competition", pick.get("comp",  ""))
    heure = m.get("heure",       pick.get("heure", ""))
    ch    = m.get("cote_home",   pick.get("ch",    "?"))
    cd    = m.get("cote_draw",   pick.get("cd",    "?"))
    ca    = m.get("cote_away",   pick.get("ca",    "?"))

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    medal  = medals[rank - 1] if rank <= 5 else f"#{rank}"
    mise   = round(bankroll * mp / 100, 2)
    gain   = round(mise * cm, 2) if cm else None
    ben    = round(gain - mise, 2) if gain else None

    lines = [
        f"{medal} *{home} vs {away}*",
        f"📌 {comp}" + (f"  ⏰ {heure}" if heure else ""),
        f"",
        f"🎯 *PARI : {pari}*",
        f"📊 Confiance : `{conf_bar(conf)}`",
        f"",
        f"💰 Mise : *{mise}€*  ({mp}% bankroll)",
    ]
    if cm:
        lines += [
            f"⚡ Cote mini : *{cm}*",
            f"🎁 Gain total : *{gain}€*  (+{ben}€ net)",
            f"📐 Calcul : {mise}€ × {cm} = {gain}€",
        ]
    if risque:
        lines += ["", f"⚠️ _Risque : {risque}_"]
    if resume:
        lines += ["", f"📝 *Pourquoi :*", f"_{resume}_"]
    lines += [
        "",
        f"Cotes · Dom {ch} | Nul {cd} | Ext {ca}",
    ]
    return "\n".join(lines)

# ── MAIN SCAN ─────────────────────────────────────────────────────────────────
async def run_scan(context: ContextTypes.DEFAULT_TYPE, bankroll: float = 100.0):
    """Lance le scan complet et envoie les résultats sur Telegram."""
    bot = context.bot
    db  = load_db()

    today_key = datetime.now().strftime("%d/%m/%Y")
    today_label = datetime.now().strftime("%A %d %B %Y")

    # ── Message de départ ────────────────────────────────────────────────────
    start_msg = await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⚽ *ORACLE FOOTBALL — SCAN DU JOUR*\n"
            f"📅 {today_label}\n\n"
            f"🔍 Recherche des matchs en cours...\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    # ── Récupération des matchs ───────────────────────────────────────────────
    matches = await fetch_matches(today_label)

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=start_msg.message_id,
            text=(
                f"⚽ *ORACLE — {today_label}*\n\n"
                f"❌ Aucun match trouvé pour aujourd'hui.\n"
                f"Réessaie avec /scan dans quelques minutes."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    to_analyze = matches[:10]

    await bot.edit_message_text(
        chat_id=CHAT_ID,
        message_id=start_msg.message_id,
        text=(
            f"⚽ *ORACLE — {today_label}*\n\n"
            f"✅ {len(matches)} matchs trouvés\n"
            f"🔬 Analyse de {len(to_analyze)} matchs en cours...\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    lessons = db.get("lessons", [])
    results = []

    # ── Analyse de chaque match ───────────────────────────────────────────────
    for i, match in enumerate(to_analyze):
        match_name = f"{match['home']} vs {match['away']}"

        # Message de progression pour ce match
        prog_msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"🔬 *Match {i+1}/{len(to_analyze)}*\n"
                f"⚽ {match_name}\n"
                f"🏆 {match.get('competition','')}\n\n"
                f"{'▓' * 0}{'░' * 9}  0%\n\n"
                f"🧠 Tacticien       ⏳\n"
                f"📊 Statisticien    ⏳\n"
                f"🏃 Médecin         ⏳\n"
                f"🧓 L'Ancien        ⏳\n"
                f"💰 Marché          ⏳\n"
                f"🎭 Psychologue     ⏳\n"
                f"⚖️ Juge            ⏳\n"
                f"🎓 Prof. Pragma.   ⏳\n"
                f"🔭 Prof. Vision.   ⏳"
            ),
            parse_mode=ParseMode.MARKDOWN
        )

        agent_states = {ag["id"]: "wait" for ag in AGENTS}
        agent_states.update({
            "juge": "wait", "prof1": "wait", "prof2": "wait"
        })
        step = [0]

        async def progress_cb(emoji, name, status, _step=step, _states=agent_states, _msg=prog_msg, _match=match_name, _i=i, _total=len(to_analyze)):
            # Trouver l'id de l'agent
            ag_map = {ag["name"]: ag["id"] for ag in AGENTS}
            ag_id = ag_map.get(name, name.lower().replace(" ", "_"))

            if status == "run":
                _states[ag_id] = "run"
            elif status == "done":
                _states[ag_id] = "done"
                _step[0] += 1

            pct = round(_step[0] / 9 * 100)
            filled = round(pct / 10)
            bar = "▓" * filled + "░" * (10 - filled)

            def ag_line(aid, ag_emoji, ag_name):
                s = _states.get(aid, "wait")
                icon = "✅" if s == "done" else "⚡" if s == "run" else "⏳"
                return f"{ag_emoji} {ag_name:<16} {icon}"

            lines = [
                f"🔬 *Match {_i+1}/{_total}*",
                f"⚽ {_match}",
                f"",
                f"`{bar}  {pct}%`",
                f"",
                ag_line("tact",   "🧠", "Tacticien"),
                ag_line("stat",   "📊", "Statisticien"),
                ag_line("doc",    "🏃", "Médecin"),
                ag_line("scout",  "🧓", "L'Ancien"),
                ag_line("market", "💰", "Marché"),
                ag_line("psycho", "🎭", "Psychologue"),
                ag_line("juge",   "⚖️", "Juge"),
                ag_line("prof1",  "🎓", "Prof. Pragma."),
                ag_line("prof2",  "🔭", "Prof. Vision."),
            ]

            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID,
                    message_id=_msg.message_id,
                    text="\n".join(lines),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception:
                pass  # Ignore si pas de changement

        try:
            result = await analyze_match(match, lessons, progress_cb)
            results.append(result)

            # Verdict final sur ce match
            v = result["verdict"]
            pct = 100
            bar = "▓" * 10
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=(
                    f"✅ *Match {i+1}/{len(to_analyze)} — Analysé*\n"
                    f"⚽ {match_name}\n\n"
                    f"`{bar}  {pct}%`\n\n"
                    f"🎯 *{v['pari']}*\n"
                    f"📊 Confiance : {v['conf']}%\n"
                    f"⚡ Cote mini : {v['cm'] or '—'}"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur analyse {match_name}: {e}")
            await bot.edit_message_text(
                chat_id=CHAT_ID,
                message_id=prog_msg.message_id,
                text=f"❌ Erreur sur {match_name} : {e}",
                parse_mode=ParseMode.MARKDOWN
            )

        await asyncio.sleep(1)

    # ── Trier et garder le Top 5 ──────────────────────────────────────────────
    results.sort(key=lambda x: x["verdict"]["conf"], reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Aucune analyse n'a pu être complétée. Réessaie avec /scan.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Sauvegarder en DB ─────────────────────────────────────────────────────
    scan_entry = {
        "date_key": today_key,
        "date_label": today_label,
        "timestamp": datetime.now().isoformat(),
        "bankroll": bankroll,
        "picks": [
            {
                "home":  r["match"]["home"],
                "away":  r["match"]["away"],
                "comp":  r["match"].get("competition", ""),
                "heure": r["match"].get("heure", ""),
                "ch":    r["match"].get("cote_home"),
                "cd":    r["match"].get("cote_draw"),
                "ca":    r["match"].get("cote_away"),
                "pari":  r["verdict"]["pari"],
                "conf":  r["verdict"]["conf"],
                "mp":    r["verdict"]["mp"],
                "cm":    r["verdict"]["cm"],
                "risque":  r["verdict"]["risque"],
                "resume":  r["verdict"]["resume"],
                "result":  None,
            }
            for r in top5
        ]
    }
    db["scans"][today_key] = scan_entry
    save_db(db)

    # ── Envoyer le Top 5 ──────────────────────────────────────────────────────
    header = (
        f"🏆 *TOP {len(top5)} PARIS DU JOUR*\n"
        f"📅 {today_label}\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )
    await bot.send_message(chat_id=CHAT_ID, text=header, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.5)

    for rank, r in enumerate(top5, 1):
        pick_data = {
            "match": r["match"],
            "verdict": r["verdict"],
        }
        text = format_pick(rank, pick_data, bankroll)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ WIN",  callback_data=f"result:{today_key}:{rank-1}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"result:{today_key}:{rank-1}:loss"),
            ]
        ])
        await bot.send_message(
            chat_id=CHAT_ID,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.5)

    # ── Message récap final ───────────────────────────────────────────────────
    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"✅ *Scan terminé !*\n\n"
            f"Clique WIN ou LOSS sur chaque pari après le match.\n"
            f"Le bot apprend de chaque résultat 🧬\n\n"
            f"_Commandes : /scan · /stats · /resultats_"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

# ── COMMANDES BOT ─────────────────────────────────────────────────────────────
async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /scan — lance le scan manuellement."""
    if update.effective_chat.id != CHAT_ID:
        return
    db = load_db()
    # Bankroll depuis DB ou défaut
    bankroll = db.get("bankroll", 100.0)
    await run_scan(context, bankroll)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /stats — affiche les statistiques."""
    if update.effective_chat.id != CHAT_ID:
        return
    db = load_db()
    all_picks = [p for s in db["scans"].values() for p in s["picks"]]
    decided   = [p for p in all_picks if p["result"] is not None]
    wins      = [p for p in decided if p["result"] == "win"]
    losses    = [p for p in decided if p["result"] == "loss"]
    wr        = round(len(wins) / len(decided) * 100) if decided else 0
    bankroll  = db.get("bankroll", 100.0)
    profit    = sum(
        (bankroll * p["mp"] / 100) * p["cm"] - (bankroll * p["mp"] / 100)
        if p["result"] == "win" and p.get("cm")
        else -(bankroll * p["mp"] / 100)
        for p in decided
    )
    nb_lessons = len(db.get("lessons", []))
    level = "Expert ⭐" if nb_lessons >= 20 else "Bon 🔥" if nb_lessons >= 10 else "En cours 📈"

    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joués : *{len(decided)}*\n"
        f"✅ Gagnés : *{len(wins)}*\n"
        f"❌ Perdus : *{len(losses)}*\n"
        f"📈 Win rate : *{wr}%*\n"
        f"💵 Profit : *{'+' if profit >= 0 else ''}{profit:.2f}€*\n\n"
        f"🧬 Leçons apprises : *{nb_lessons}*\n"
        f"🎓 Niveau IA : *{level}*\n\n"
        f"💰 Bankroll : *{bankroll:.2f}€*",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /resultats — affiche les picks en attente."""
    if update.effective_chat.id != CHAT_ID:
        return
    db = load_db()
    pending = []
    for date_key, scan in db["scans"].items():
        for i, p in enumerate(scan["picks"]):
            if p["result"] is None:
                pending.append((date_key, i, p, scan["date_label"]))

    if not pending:
        await update.message.reply_text("✅ Tous les résultats ont été saisis !")
        return

    await update.message.reply_text(
        f"⏳ *{len(pending)} paris en attente de résultat*\n"
        f"━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.MARKDOWN
    )

    for date_key, idx, pick, date_label in pending[:10]:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ WIN",  callback_data=f"result:{date_key}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"result:{date_key}:{idx}:loss"),
            ]
        ])
        await update.message.reply_text(
            f"📅 _{date_label}_\n"
            f"⚽ *{pick['home']} vs {pick['away']}*\n"
            f"🎯 {pick['pari']} ({pick['conf']}%)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        await asyncio.sleep(0.3)

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /bankroll <montant> — met à jour la bankroll."""
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        amount = float(context.args[0])
        db = load_db()
        db["bankroll"] = amount
        save_db(db)
        await update.message.reply_text(f"💰 Bankroll mise à jour : *{amount:.2f}€*", parse_mode=ParseMode.MARKDOWN)
    except (IndexError, ValueError):
        await update.message.reply_text("Usage : /bankroll 150")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help."""
    if update.effective_chat.id != CHAT_ID:
        return
    await update.message.reply_text(
        "⚽ *ORACLE FOOTBALL — AIDE*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 /scan — Lance le scan du jour\n"
        "📊 /stats — Statistiques & win rate\n"
        "⏳ /resultats — Paris en attente\n"
        "💰 /bankroll 150 — Changer la bankroll\n"
        "❓ /help — Cette aide\n\n"
        "🤖 _Le scan automatique tourne chaque matin._\n"
        "🧬 _L'IA apprend de chaque résultat WIN/LOSS._",
        parse_mode=ParseMode.MARKDOWN
    )

# ── CALLBACK WIN/LOSS ─────────────────────────────────────────────────────────
async def handle_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère les boutons WIN / LOSS."""
    query = update.callback_query
    await query.answer()

    if query.message.chat_id != CHAT_ID:
        return

    _, date_key, idx_str, result = query.data.split(":")
    idx = int(idx_str)

    db = load_db()
    scan = db["scans"].get(date_key)
    if not scan or idx >= len(scan["picks"]):
        await query.edit_message_reply_markup(reply_markup=None)
        return

    pick = scan["picks"][idx]
    prev_result = pick["result"]

    # Toggle
    pick["result"] = None if pick["result"] == result else result
    save_db(db)

    # Confirmer visuellement
    if pick["result"]:
        icon = "✅" if pick["result"] == "win" else "❌"
        bankroll = db.get("bankroll", 100.0)
        mise = round(bankroll * pick["mp"] / 100, 2)
        gain = round(mise * pick["cm"], 2) if pick.get("cm") and pick["result"] == "win" else None

        result_text = (
            f"✅ *WIN +{gain}€* !" if gain else
            f"✅ *WIN !*" if pick["result"] == "win" else
            f"❌ *LOSS -{mise}€*"
        )

        await query.edit_message_text(
            text=query.message.text + f"\n\n{icon} *Résultat enregistré : {result_text}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=None
        )

        # Déclencher l'apprentissage
        if prev_result is None:
            await trigger_learning(pick, db, context)
    else:
        # Dé-toggle → remettre les boutons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ WIN",  callback_data=f"result:{date_key}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"result:{date_key}:{idx}:loss"),
            ]
        ])
        await query.edit_message_reply_markup(reply_markup=keyboard)

# ── AUTO-LEARNING ─────────────────────────────────────────────────────────────
async def trigger_learning(pick: dict, db: dict, context: ContextTypes.DEFAULT_TYPE):
    """Génère une leçon après un résultat et l'injecte dans les prochains scans."""
    try:
        won = pick["result"] == "win"
        prompt = (
            f"Pari résolu :\n"
            f"Match : {pick['home']} vs {pick['away']} ({pick.get('comp','')})\n"
            f"Pari : {pick['pari']} | Confiance : {pick['conf']}%\n"
            f"Résultat : {'GAGNÉ ✅' if won else 'PERDU ❌'}\n\n"
            f"Génère UNE leçon courte (2 phrases max) pour améliorer les prochaines analyses. "
            f"{'Qu\'est-ce qui a bien fonctionné ?' if won else 'Qu\'est-il faillé éviter ?'}\n"
            f"Réponds uniquement avec la leçon en français."
        )
        lesson_text = await call_groq(
            "Système d'auto-amélioration pour paris sportifs. Français, concis.",
            prompt,
            max_tokens=150
        )
        lesson = {
            "id": int(datetime.now().timestamp()),
            "date": datetime.now().strftime("%d/%m/%Y"),
            "match": f"{pick['home']} vs {pick['away']}",
            "pari": pick["pari"],
            "result": pick["result"],
            "text": lesson_text.strip()
        }
        if "lessons" not in db:
            db["lessons"] = []
        db["lessons"].append(lesson)
        db["lessons"] = db["lessons"][-50:]  # Garder les 50 dernières
        save_db(db)

        # Notifier
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

# ── RAPPEL RESULTATS VEILLE ───────────────────────────────────────────────────
async def remind_yesterday(context: ContextTypes.DEFAULT_TYPE):
    """Rappel le lendemain pour les paris sans résultat."""
    db = load_db()
    yesterday_key = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
    scan = db["scans"].get(yesterday_key)
    if not scan:
        return

    pending = [(i, p) for i, p in enumerate(scan["picks"]) if p["result"] is None]
    if not pending:
        return

    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⏰ *Résultats en attente — {yesterday_key}*\n\n"
            f"{len(pending)} paris d'hier sans résultat !\n"
            f"Tape /resultats pour les saisir 👇"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

# ── SCAN AUTOMATIQUE ─────────────────────────────────────────────────────────
async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    """Scan automatique quotidien."""
    db = load_db()
    bankroll = db.get("bankroll", 100.0)
    await run_scan(context, bankroll)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    if not GROQ_KEYS:
        logger.error("❌ Aucune clé GROQ trouvée. Configure GROQ_KEYS dans .env")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("bankroll",  cmd_bankroll))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("start",     cmd_help))

    # Boutons WIN/LOSS
    app.add_handler(CallbackQueryHandler(handle_result, pattern=r"^result:"))

    # Jobs planifiés
    job_queue: JobQueue = app.job_queue
    # Scan auto chaque matin à SCAN_HOUR h
    job_queue.run_daily(
        auto_scan,
        time=datetime.strptime(f"{SCAN_HOUR:02d}:00", "%H:%M").time(),
        name="daily_scan"
    )
    # Rappel résultats chaque matin à SCAN_HOUR+1 h
    remind_hour = (SCAN_HOUR + 1) % 24
    job_queue.run_daily(
        remind_yesterday,
        time=datetime.strptime(f"{remind_hour:02d}:00", "%H:%M").time(),
        name="remind_yesterday"
    )

    logger.info(f"⚽ Oracle Bot démarré — scan auto à {SCAN_HOUR}h00")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
