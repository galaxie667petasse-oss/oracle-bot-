import os, json, asyncio, logging, re
from datetime import datetime, timedelta
from pathlib import Path
import google.generativeai as genai
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue
from telegram.constants import ParseMode
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = int(os.getenv("CHAT_ID", "0"))
GEMINI_KEY     = os.getenv("GEMINI_KEY", "")
GROQ_KEYS      = [k.strip() for k in os.getenv("GROQ_KEYS", "").split(",") if k.strip()]
SCAN_HOUR      = int(os.getenv("SCAN_HOUR", "9"))
BANKROLL_DEF   = float(os.getenv("BANKROLL", "100"))
DB_FILE        = Path("oracle_db.json")

groq_idx = 0
def next_key():
    global groq_idx
    if not GROQ_KEYS:
        raise ValueError("Aucune cle GROQ configuree")
    k = GROQ_KEYS[groq_idx % len(GROQ_KEYS)]
    groq_idx += 1
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
    target = now + timedelta(days=1) if h >= 21 else now
    tmrw = h >= 21
    JOURS = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    MOIS  = ["janvier","fevrier","mars","avril","mai","juin","juillet","aout","septembre","octobre","novembre","decembre"]
    label = f"{JOURS[target.weekday()]} {target.day} {MOIS[target.month-1]} {target.year}"
    return {"label": label, "key": target.strftime("%d/%m/%Y"), "tmrw": tmrw, "hour": h}

AGENTS = [
    {"id":"tact",  "n":"Tacticien",       "e":"🧠", "s":"Expert tacticien football. Formations, pressing, transitions. 80 mots max en francais."},
    {"id":"stat",  "n":"Statisticien",    "e":"📊", "s":"Analyste statistique football. Forme, H2H, buts, probabilites. 80 mots max en francais."},
    {"id":"doc",   "n":"Medecin",         "e":"🏃", "s":"Medecin sportif. Fatigue, blessures, rotations. 80 mots max en francais."},
    {"id":"scout", "n":"L'Ancien",        "e":"🧓", "s":"Scout legendaire 40 ans. Patterns caches, pieges. 80 mots max en francais."},
    {"id":"mkt",   "n":"Marche",          "e":"💰", "s":"Expert paris. Value bets, probabilite implicite. 80 mots max en francais."},
    {"id":"psy",   "n":"Psychologue",     "e":"🎭", "s":"Psychologue sport. Enjeux, pression, motivation. 80 mots max en francais."},
    {"id":"juge",  "n":"Juge",            "e":"⚖️", "s":"Juge Arbitre. Synthetise les 6 rapports. 120 mots max en francais."},
    {"id":"pr1",   "n":"Prof Pragma",     "e":"🎓", "s":"Professeur Pragmatique. Identifie failles, realiste. 100 mots max en francais."},
    {"id":"pr2",   "n":"Prof Vision",     "e":"🔭", "s":""},
]

def pr2sys(lessons):
    s = (
        "Professeur Visionnaire. Analyse courte (60 mots), puis VERDICT FINAL OBLIGATOIRE:\n\n"
        "PARI: [ex: Victoire Lyon / Plus de 2.5 buts / BTTS Oui]\n"
        "CONFIANCE: [chiffre 0-100]\n"
        "MISE_PCT: [chiffre 1-5]\n"
        "COTE_MINI: [chiffre decimal ex: 1.75]\n"
        "RISQUE: [une phrase]\n"
        "RESUME: [3 phrases pourquoi ce pari]"
    )
    if lessons:
        s += "\n\nLECONS APPRISES:\n" + "\n".join(f"- {l['text']}" for l in lessons[-5:])
    return s

def parse_v(text):
    if not text:
        return {"pari":"Non disponible","conf":50,"mp":2,"cm":None,"risque":"","resume":""}
    t = re.sub(r"\*+","",text)
    t = re.sub(r"^#+[^\n]*","",t,flags=re.MULTILINE)
    def g(rx, fb=""):
        m = re.search(rx, t, re.IGNORECASE)
        return m.group(1).strip() if m else fb
    cs = g(r"CONFIANCE\s*:\s*(\d+)","50")
    ms = g(r"MISE_PCT\s*:\s*(\d+)","2")
    cms = g(r"COTE[_\s]*MINI\s*:\s*([\d.,]+)","0").replace(",",".")
    return {
        "pari":   g(r"PARI\s*:\s*([^\n]+)","Voir analyse"),
        "conf":   min(100,max(0,int(cs) if cs.isdigit() else 50)),
        "mp":     min(5,max(1,int(ms) if ms.isdigit() else 2)),
        "cm":     float(cms) if cms and cms!="0" else None,
        "risque": g(r"RISQUE\s*:\s*([^\n]+)",""),
        "resume": g(r"RESUME\s*:\s*([\s\S]+?)(?=\n[A-Z_]+\s*:|$)",""),
    }

async def fetch_matches(label):
    genai.configure(api_key=GEMINI_KEY)
    prompt = (
        f"Recherche sur le web les matchs de football confirmes le {label}.\n"
        f"REGLES: 1.UNIQUEMENT matchs confirmes via web. 2.JAMAIS inventer. "
        f"3.Pas matchs deja joues. 4.Heure exacte obligatoire.\n"
        f"Competitions: Ligue 1, Premier League, La Liga, Serie A, Bundesliga, "
        f"Champions League, Europa League, Conference League, Ligue 2, Championship.\n"
        f"JSON UNIQUEMENT (12 matchs max):\n"
        f'{"{"}"matches":[{"{"}"home":"X","away":"Y","competition":"Z","date":"{label}",'
        f'"heure":"20:45","cote_home":1.85,"cote_draw":3.40,"cote_away":4.20,'
        f'"contexte":"forme, blesses, enjeux"{"}"}]{"}"}\n'
        f"ZERO invention. Uniquement matchs REELS."
    )
    matches = []
    for attempt in range(4):
        try:
            model = genai.GenerativeModel("gemini-1.5-flash", tools="google_search_retrieval")
            resp = await asyncio.to_thread(
                lambda: model.generate_content(prompt,
                    generation_config=genai.GenerationConfig(max_output_tokens=2000, temperature=0.3))
            )
            raw = resp.text.strip()
            for fn in [
                lambda: json.loads(raw),
                lambda: json.loads(re.search(r"```(?:json)?\s*([\s\S]*?)```",raw).group(1).strip()),
                lambda: json.loads(re.search(r'(\{[\s\S]*?"matches"\s*:\s*\[[\s\S]*?\]\s*\})',raw).group(1)),
            ]:
                try:
                    p = fn()
                    if p and p.get("matches"):
                        matches = p["matches"]
                        break
                except: pass
            if matches:
                break
            # Reformatage
            m2 = genai.GenerativeModel("gemini-1.5-flash")
            r2 = await asyncio.to_thread(
                lambda: m2.generate_content(
                    f'Reformate en JSON: {"{"}"matches":[{"{"}"home":"X","away":"Y","competition":"Z","date":"{label}","heure":"HH:MM","cote_home":1.8,"cote_draw":3.5,"cote_away":4.0,"contexte":"infos"{"}"}]{"}"}\n\n{raw[:3000]}',
                    generation_config=genai.GenerationConfig(max_output_tokens=2000))
            )
            rt = r2.text.strip()
            for fn in [
                lambda: json.loads(rt),
                lambda: json.loads(re.search(r'(\{[\s\S]*?"matches"[\s\S]*?\]\s*\})',rt).group(1)),
            ]:
                try:
                    p = fn()
                    if p and p.get("matches"):
                        matches = p["matches"]
                        break
                except: pass
            if matches:
                break
        except Exception as e:
            logger.warning(f"Gemini attempt {attempt+1}: {e}")
            await asyncio.sleep(3)
    return matches

async def call_groq(system, user, max_tokens=400):
    for attempt in range(4):
        try:
            client = Groq(api_key=next_key())
            resp = await asyncio.to_thread(
                lambda: client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role":"system","content":system},{"role":"user","content":user}],
                    max_tokens=max_tokens, temperature=0.7,
                )
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Groq attempt {attempt+1}: {e}")
            if "429" in str(e) or "rate" in str(e).lower():
                await asyncio.sleep((attempt+1)*6)
            elif attempt==3: raise
            else: await asyncio.sleep(2)
    raise RuntimeError("Groq indisponible")

def prog_bar(pct):
    f = round(pct/10)
    return "█"*f + "░"*(10-f)

def ag_line(eid, ename, states):
    s = states.get(eid,"wait")
    icon = "✅" if s=="done" else "⚡" if s=="run" else "⏳"
    return f"{ename:<20} {icon}"

def build_prog(i, total, mname, comp, states, pct):
    return "\n".join([
        f"🔬 *Match {i+1}/{total}*",
        f"⚽ {mname}",
        f"🏆 {comp}",
        "",
        f"`{prog_bar(pct)}  {pct}%`",
        "",
        ag_line("tact",  "🧠 Tacticien",       states),
        ag_line("stat",  "📊 Statisticien",     states),
        ag_line("doc",   "🏃 Medecin",          states),
        ag_line("scout", "🧓 L'Ancien",         states),
        ag_line("mkt",   "💰 Marche",           states),
        ag_line("psy",   "🎭 Psychologue",      states),
        ag_line("juge",  "⚖️ Juge",             states),
        ag_line("pr1",   "🎓 Prof Pragma",      states),
        ag_line("pr2",   "🔭 Prof Vision",      states),
    ])

def conf_bar(conf):
    f = round(conf/10)
    return "█"*f + "░"*(10-f) + f" {conf}%"

def fmt_pick(rank, pick, bankroll):
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    medal = medals[rank-1] if rank<=5 else f"#{rank}"
    home   = pick.get("home","?")
    away   = pick.get("away","?")
    comp   = pick.get("comp","")
    heure  = pick.get("heure","")
    date   = pick.get("date","")
    ch     = pick.get("ch","?")
    cd     = pick.get("cd","?")
    ca     = pick.get("ca","?")
    pari   = pick.get("pari","—")
    conf   = pick.get("conf",50)
    mp     = pick.get("mp",2)
    cm     = pick.get("cm",None)
    risque = pick.get("risque","")
    resume = pick.get("resume","")
    mise   = round(bankroll*mp/100,2)
    gain   = round(mise*cm,2) if cm else None
    ben    = round(gain-mise,2) if gain else None
    lines = [
        f"{medal} *{home} vs {away}*",
        f"🏆 {comp}" + (f"  ⏰ {heure}" if heure else "") + (f"  📅 {date}" if date else ""),
        "",
        f"🎯 *PARI : {pari}*",
        f"📊 `{conf_bar(conf)}`",
        "",
        f"💰 Mise : *{mise}€* ({mp}% bankroll)",
    ]
    if cm:
        lines += [
            f"⚡ Cote mini : *{cm}*",
            f"🎁 Gain total : *{gain}€* (+{ben}€ net)",
            f"📐 {mise}€ x {cm} = {gain}€",
        ]
    if risque:
        lines += ["", f"⚠️ Risque : {risque}"]
    if resume:
        lines += ["", f"📝 *Pourquoi :*", f"{resume}"]
    lines += ["", f"Cotes — Dom *{ch}* | Nul *{cd}* | Ext *{ca}*"]
    return "\n".join(lines)

async def analyze_match(match, lessons, progress_cb):
    base = (
        f"{match['home']} vs {match['away']} | "
        f"{match.get('competition','')} | {match.get('heure','?')}h\n"
        f"Cotes: Dom {match.get('cote_home','?')} | "
        f"Nul {match.get('cote_draw','?')} | "
        f"Ext {match.get('cote_away','?')}\n"
        f"Contexte: {match.get('contexte','Pas d info')}"
    )
    reports = {}
    AGENTS[8]["s"] = pr2sys(lessons)

    for ag in AGENTS[:6]:
        await progress_cb(ag["id"], "run")
        try: reports[ag["id"]] = await call_groq(ag["s"], base+"\n\nAnalyse experte en 80 mots.", 220)
        except Exception as e: reports[ag["id"]] = f"Indisponible ({e})"
        await progress_cb(ag["id"], "done")

    all_r = "\n\n".join(f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports[AGENTS[i]['id']]}" for i in range(6))

    await progress_cb("juge","run")
    try: reports["juge"] = await call_groq(AGENTS[6]["s"], base+"\n\nRAPPORTS:\n"+all_r+"\n\nSynthese.", 280)
    except Exception as e: reports["juge"] = f"Erreur ({e})"
    await progress_cb("juge","done")

    await progress_cb("pr1","run")
    try: reports["pr1"] = await call_groq(AGENTS[7]["s"], base+"\n\nJUGE:\n"+reports["juge"]+"\n\nCorrige.", 220)
    except Exception as e: reports["pr1"] = f"Erreur ({e})"
    await progress_cb("pr1","done")

    await progress_cb("pr2","run")
    try: reports["pr2"] = await call_groq(AGENTS[8]["s"],
        base+"\n\nJUGE:\n"+reports["juge"]+"\n\nPRAGMATIQUE:\n"+reports["pr1"]+"\n\nVERDICT FINAL obligatoire.", 500)
    except Exception as e: reports["pr2"] = f"Erreur ({e})"
    await progress_cb("pr2","done")

    return {"match":match, "reports":reports, "verdict":parse_v(reports.get("pr2",""))}

async def run_scan(context, bankroll):
    bot = context.bot
    db  = load_db()
    ti  = get_target()
    prefix = "DEMAIN" if ti["tmrw"] else "AUJOURD'HUI"
    icon   = "🌙" if ti["tmrw"] else "☀️"

    start_msg = await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"⚽ *ORACLE — SCAN {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"🔍 Gemini recherche les matchs confirmes...\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    matches = await fetch_matches(ti["label"])

    if not matches:
        await bot.edit_message_text(
            chat_id=CHAT_ID, message_id=start_msg.message_id,
            text=(
                f"⚽ *ORACLE — {ti['label']}*\n\n"
                f"❌ Aucun match confirme trouve.\n"
                f"Reessaie avec /scan dans quelques minutes."
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        return

    to_analyze = matches[:10]

    await bot.edit_message_text(
        chat_id=CHAT_ID, message_id=start_msg.message_id,
        text=(
            f"⚽ *ORACLE — {prefix}*\n"
            f"{icon} {ti['label']}\n\n"
            f"✅ *{len(matches)} matchs confirmes* par Gemini Google\n"
            f"🔬 Analyse de {len(to_analyze)} matchs en cours...\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

    lessons = db.get("lessons",[])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition","")

        prog_msg = await bot.send_message(
            chat_id=CHAT_ID,
            text=build_prog(i, len(to_analyze), mname, comp, {}, 0),
            parse_mode=ParseMode.MARKDOWN
        )

        states = {ag["id"]:"wait" for ag in AGENTS}
        steps  = [0]

        async def pcb(ag_id, status,
                      _s=states, _st=steps, _m=prog_msg,
                      _n=mname, _c=comp, _i=i, _t=len(to_analyze)):
            if status=="run": _s[ag_id]="run"
            elif status=="done": _s[ag_id]="done"; _st[0]+=1
            pct = round(_st[0]/9*100)
            try:
                await bot.edit_message_text(
                    chat_id=CHAT_ID, message_id=_m.message_id,
                    text=build_prog(_i, _t, _n, _c, _s, pct),
                    parse_mode=ParseMode.MARKDOWN
                )
            except: pass

        try:
            result = await analyze_match(match, lessons, pcb)
            results.append(result)
            v = result["verdict"]
            await bot.edit_message_text(
                chat_id=CHAT_ID, message_id=prog_msg.message_id,
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
            logger.error(f"Erreur {mname}: {e}")
            await bot.edit_message_text(
                chat_id=CHAT_ID, message_id=prog_msg.message_id,
                text=f"❌ Erreur sur {mname}"
            )
        await asyncio.sleep(1)

    results.sort(key=lambda x: x["verdict"]["conf"], reverse=True)
    top5 = results[:5]

    if not top5:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Aucune analyse completee. Reessaie avec /scan.")
        return

    entry = {
        "date_key": ti["key"], "date_label": ti["label"],
        "is_tomorrow": ti["tmrw"], "timestamp": datetime.now().isoformat(),
        "bankroll": bankroll,
        "picks": [{
            "home":r["match"]["home"],"away":r["match"]["away"],
            "comp":r["match"].get("competition",""),
            "date":r["match"].get("date",ti["label"]),
            "heure":r["match"].get("heure",""),
            "ch":r["match"].get("cote_home"),"cd":r["match"].get("cote_draw"),"ca":r["match"].get("cote_away"),
            **r["verdict"], "result":None
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
            "home":r["match"]["home"],"away":r["match"]["away"],
            "comp":r["match"].get("competition",""),
            "date":r["match"].get("date",""),"heure":r["match"].get("heure",""),
            "ch":r["match"].get("cote_home"),"cd":r["match"].get("cote_draw"),"ca":r["match"].get("cote_away"),
            **r["verdict"]
        }
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{ti['key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{ti['key']}:{rank-1}:loss"),
        ]])
        await bot.send_message(chat_id=CHAT_ID, text=fmt_pick(rank, pick, bankroll),
                               parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        await asyncio.sleep(0.5)

    await bot.send_message(
        chat_id=CHAT_ID,
        text=(
            f"✅ *Scan termine !*\n\n"
            f"Appuie sur WIN ou LOSS apres chaque match.\n"
            f"L'IA apprend de chaque resultat 🧬\n\n"
            f"/stats  /resultats  /bankroll"
        ),
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    ti = get_target()
    prefix = "demain" if ti["tmrw"] else "aujourd'hui"
    icon   = "🌙" if ti["tmrw"] else "☀️"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"{icon} Scanner les matchs de {prefix}", callback_data="launch_scan")
    ]])
    await update.message.reply_text(
        f"⚽ *ORACLE FOOTBALL*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"9 agents Groq Llama 3.3 70B\n"
        f"Recherche matchs Gemini + Google\n"
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
    if update.effective_chat.id != CHAT_ID: return
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db = load_db()
    all_p = [p for s in db["scans"].values() for p in s["picks"]]
    dec   = [p for p in all_p if p.get("result")]
    wins  = [p for p in dec if p["result"]=="win"]
    losses= [p for p in dec if p["result"]=="loss"]
    wr    = round(len(wins)/len(dec)*100) if dec else 0
    bank  = db.get("bankroll", BANKROLL_DEF)
    profit= sum(
        (bank*p.get("mp",2)/100)*p["cm"]-(bank*p.get("mp",2)/100)
        if p["result"]=="win" and p.get("cm")
        else -(bank*p.get("mp",2)/100)
        for p in dec
    )
    nb = len(db.get("lessons",[]))
    lvl = "Expert ⭐" if nb>=20 else "Bon 🔥" if nb>=10 else "En cours 📈"
    await update.message.reply_text(
        f"📊 *STATISTIQUES ORACLE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Paris joues : *{len(dec)}*\n"
        f"✅ Gagnes : *{len(wins)}*\n"
        f"❌ Perdus : *{len(losses)}*\n"
        f"📈 Win rate : *{wr}%*\n"
        f"💵 Profit : *{'+' if profit>=0 else ''}{profit:.2f}€*\n\n"
        f"🧬 Lecons : *{nb}*  |  Niveau : *{lvl}*\n"
        f"💰 Bankroll : *{bank:.2f}€*",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db = load_db()
    pending = [(dk,i,p,s["date_label"]) for dk,s in db["scans"].items()
               for i,p in enumerate(s["picks"]) if not p.get("result")]
    if not pending:
        await update.message.reply_text("✅ Tous les resultats ont ete saisis !")
        return
    await update.message.reply_text(f"⏳ *{len(pending)} paris en attente*", parse_mode=ParseMode.MARKDOWN)
    for dk, idx, pick, dlabel in pending[:10]:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
        ]])
        await update.message.reply_text(
            f"📅 {dlabel}\n⚽ *{pick['home']} vs {pick['away']}*\n🎯 {pick['pari']} ({pick['conf']}%)",
            parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
        )
        await asyncio.sleep(0.3)

async def cmd_bankroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    try:
        amount = float(context.args[0])
        db = load_db(); db["bankroll"] = amount; save_db(db)
        await update.message.reply_text(f"💰 Bankroll mise a jour : *{amount:.2f}€*", parse_mode=ParseMode.MARKDOWN)
    except (IndexError, ValueError):
        await update.message.reply_text("Usage : /bankroll 150")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.message.chat_id != CHAT_ID: return
    data = query.data

    if data == "launch_scan":
        db = load_db()
        await run_scan(context, db.get("bankroll", BANKROLL_DEF))
        return

    if data.startswith("res:"):
        _, dk, idx_s, result = data.split(":")
        idx = int(idx_s)
        db = load_db()
        scan = db["scans"].get(dk)
        if not scan or idx >= len(scan["picks"]): return
        pick = scan["picks"][idx]
        prev = pick.get("result")
        pick["result"] = None if prev==result else result
        save_db(db)

        if pick["result"]:
            icon  = "✅" if pick["result"]=="win" else "❌"
            bank  = db.get("bankroll", BANKROLL_DEF)
            mise  = round(bank*pick.get("mp",2)/100, 2)
            cm    = pick.get("cm")
            g_str = f"+{round(mise*cm-mise,2)}€" if cm and pick["result"]=="win" else f"-{mise}€"
            try:
                await query.edit_message_text(
                    text=query.message.text+f"\n\n{icon} *{pick['result'].upper()}* enregistre — {g_str}",
                    parse_mode=ParseMode.MARKDOWN, reply_markup=None
                )
            except: pass
            if not prev:
                await trigger_learning(pick, db, context)
        else:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ WIN",  callback_data=f"res:{dk}:{idx}:win"),
                InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),
            ]])
            try: await query.edit_message_reply_markup(reply_markup=keyboard)
            except: pass

async def trigger_learning(pick, db, context):
    try:
        won = pick["result"]=="win"
        lesson_text = await call_groq(
            "Systeme auto-amelioration paris sportifs. Francais, concis.",
            f"Pari resolu:\nMatch: {pick['home']} vs {pick['away']}\n"
            f"Pari: {pick['pari']} | Confiance: {pick['conf']}%\n"
            f"Resultat: {'GAGNE' if won else 'PERDU'}\n\n"
            f"Genere UNE lecon courte (2 phrases) pour ameliorer les prochaines analyses.",
            150
        )
        lesson = {
            "id":int(datetime.now().timestamp()),
            "date":datetime.now().strftime("%d/%m/%Y"),
            "match":f"{pick['home']} vs {pick['away']}",
            "pari":pick["pari"],"result":pick["result"],
            "text":lesson_text.strip()
        }
        db.setdefault("lessons",[])
        db["lessons"].append(lesson)
        db["lessons"] = db["lessons"][-50:]
        save_db(db)
        icon = "🟢" if won else "🔴"
        await context.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🧬 *Nouvelle lecon apprise !*\n\n{icon} {pick['home']} vs {pick['away']} — {'WIN' if won else 'LOSS'}\n\n💡 {lesson_text.strip()}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Learning: {e}")

async def remind_yesterday(context):
    db = load_db()
    yd = (datetime.now()-timedelta(days=1)).strftime("%d/%m/%Y")
    scan = db["scans"].get(yd)
    if not scan: return
    pending = [p for p in scan["picks"] if not p.get("result")]
    if not pending: return
    await context.bot.send_message(
        chat_id=CHAT_ID,
        text=f"⏰ *Resultats en attente — {yd}*\n\n{len(pending)} paris sans resultat !\nTape /resultats pour les saisir 👇",
        parse_mode=ParseMode.MARKDOWN
    )

async def auto_scan(context):
    db = load_db()
    await run_scan(context, db.get("bankroll", BANKROLL_DEF))

def main():
    if not TELEGRAM_TOKEN: logger.error("TELEGRAM_TOKEN manquant"); return
    if not GEMINI_KEY:     logger.error("GEMINI_KEY manquante"); return
    if not GROQ_KEYS:      logger.error("GROQ_KEYS manquantes"); return

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("scan",      cmd_scan))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("bankroll",  cmd_bankroll))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq = app.job_queue
    jq.run_daily(auto_scan,       time=datetime.strptime(f"{SCAN_HOUR:02d}:00","%H:%M").time(), name="scan")
    jq.run_daily(remind_yesterday,time=datetime.strptime(f"{(SCAN_HOUR+1)%24:02d}:00","%H:%M").time(), name="remind")

    logger.info(f"Oracle Bot demarre — scan auto a {SCAN_HOUR}h — {len(GROQ_KEYS)} cles Groq")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
