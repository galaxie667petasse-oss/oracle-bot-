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

# ── THE ODDS API ─────────────────────────────────────────────────────────────
async def fetch_matches(iso_date: str, label: str) -> list:
    if not ODDSPAPI_KEY:
        raise RuntimeError("ODDSPAPI_KEY manquante")
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

# ── 12 AGENTS SPÉCIALISÉS (puissant) ────────────────────────────────────────
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

# ── METEO ───────────────────────────────────────────────────────────────────
TEAM_CITY = {
    "Paris Saint Germain":"Paris","PSG":"Paris","Marseille":"Marseille","Lyon":"Lyon","Lille":"Lille","Monaco":"Monaco","Rennes":"Rennes",
    "Manchester City":"Manchester","Manchester United":"Manchester","Arsenal":"London","Chelsea":"London","Liverpool":"Liverpool",
    "Real Madrid":"Madrid","Barcelona":"Barcelona","Bayern Munich":"Munich","Borussia Dortmund":"Dortmund"
}

def get_city(team: str) -> str:
    for k,v in TEAM_CITY.items():
        if k.lower() in team.lower() or team.lower() in k.lower(): return v
    return team.split()[0]

async def fetch_weather(home_team: str) -> str:
    city = get_city(home_team)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://wttr.in/{city.replace(' ','+')}?format=j1", timeout=8) as r:
                if r.status != 200: return "Meteo indisponible"
                d = await r.json(content_type=None)
                c = d.get("current_condition",[{}])[0]
                return f"{c.get('weatherDesc',[{}])[0].get('value','?')}, {c.get('temp_C','?')}°C, Vent {c.get('windspeedKmph','?')}km/h, Pluie {c.get('precipMM','0')}mm"
    except: return "Meteo indisponible"

async def fetch_context(match: dict) -> str:
    prompt = f"Match: {match['home']} vs {match['away']}\nCompetition: {match['competition']} | {match['date']}\nDonne le contexte sportif REEL en français (150 mots max)."
    return await call_groq("Expert football européen 2024-2025. Infos factuelles uniquement.", prompt, 280)

def winrate_by_type(db: dict) -> str:
    picks = [p for s in db.get("scans",{}).values() for p in s.get("picks",[])]
    dec = [p for p in picks if p.get("result") in ["win","loss"]]
    if len(dec) < 3: return ""
    cats = {}
    for p in dec:
        t = p.get("pari","").lower()
        k = ("btts" if "btts" in t else "over" if "plus de" in t else "under" if "moins de" in t else "nul" if "nul" in t else "victoire")
        cats.setdefault(k,[]).append(p["result"]=="win")
    return " | ".join(f"{k}: {round(sum(v)/len(v)*100)}% ({len(v)}j)" for k,v in cats.items() if len(v)>=2)

def build_pr2(lessons, db=None):
    lb = "\n\nLECONS PRECEDENTES:\n" + "\n".join(f"- {l['text']}" for l in lessons[-5:]) if lessons else ""
    hb = f"\n\nHISTORIQUE WIN RATE:\n{winrate_by_type(db)}" if db and winrate_by_type(db) else ""
    return ("Tu es le Professeur Visionnaire, expert value betting football.\nFRANCAIS UNIQUEMENT. Toujours proposer UN pari precis.\n\nJSON UNIQUEMENT :\n" +
            '{"pari": "Victoire [equipe] ou BTTS Oui ou Plus de 2.5 buts", "confiance": <58-92>, "mise_pct": <1-5>, "risque": "...", "resume": "3 phrases"}\n' + lb + hb)

def parse_verdict(text: str) -> dict:
    default = {"pari":"Analyse en cours","conf":65,"mp":2,"risque":"","resume":""}
    try:
        m = re.search(r'\{[\s\S]*?\}', text)
        d = json.loads(m.group(0) if m else text)
        return {"pari":str(d.get("pari","")).strip(), "conf":min(92,max(58,int(d.get("confiance",d.get("conf",65))))), "mp":min(5,max(1,int(d.get("mise_pct",2)))), "risque":str(d.get("risque","")).strip(), "resume":str(d.get("resume","")).strip()}
    except:
        return default

# ── ANALYSE MATCH ───────────────────────────────────────────────────────────
async def analyze_match(match, context, weather, lessons, pcb, db=None):
    def prob(c):
        try: return round(1/float(c)*100,1)
        except: return "?"
    ch = match.get("cote_home","?")
    cd = match.get("cote_draw","?")
    ca = match.get("cote_away","?")
    bk = match.get("bookmaker","?")

    base = (f"MATCH: {match['home']} vs {match['away']}\n"
            f"Competition: {match['competition']} | {match['heure']}\n\n"
            f"METEO: {weather}\n\n"
            f"COTES {bk.upper()}:\n"
            f"{match['home']}: {ch} ({prob(ch)}%) | Nul: {cd} ({prob(cd)}%) | {match['away']}: {ca} ({prob(ca)}%)\n\n"
            f"CONTEXTE: {context}")

    AGENTS[9]["s"] = build_pr2(lessons, db)
    reports = {}

    for ag in AGENTS[:8]:
        await pcb(ag["id"],"run")
        reports[ag["id"]] = await call_groq(ag["s"], base+"\n\nAnalyse 80 mots.", 220)
        await pcb(ag["id"],"done")

    all_r = "\n\n".join(f"[{AGENTS[i]['e']} {AGENTS[i]['n']}]\n{reports.get(AGENTS[i]['id'],'')}" for i in range(8))

    await pcb("juge","run")
    reports["juge"] = await call_groq(AGENTS[7]["s"], base+"\n\nRAPPORTS:\n"+all_r+"\n\nSynthese.", 280)
    await pcb("juge","done")

    await pcb("pr1","run")
    reports["pr1"] = await call_groq(AGENTS[8]["s"], base+"\n\nJUGE:\n"+reports["juge"]+"\n\nCorrige.", 220)
    await pcb("pr1","done")

    await pcb("pr2","run")
    reports["pr2"] = await call_groq(AGENTS[9]["s"], base+"\n\nJUGE:\n"+reports["juge"]+"\n\nPRAGMATIQUE:\n"+reports["pr1"]+"\n\nJSON uniquement.", 420)
    await pcb("pr2","done")

    return {"match":match, "reports":reports, "verdict":parse_verdict(reports.get("pr2",""))}

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
        line("meteo","🌧️","Météo"),line("juge","⚖️","Juge"),
        line("pr1","🎓","Prof Pragma"),line("pr2","🔭","Prof Vision"),
        line("arbitre","⚖️","Arbitre"),line("corners","📐","Corners"),
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
            await bot.send_message(chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN, text=f"💾 *Scan du {ti['key']} déjà effectué*\n\n{len(pks)} paris en mémoire.\n/resultats pour les voir\n/scan force pour forcer")
            return

    msg = await bot.send_message(chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN, text=f"⚽ *ORACLE — SCAN DU JOUR*\n☀️ {ti['label']}\n\n🔍 Récupération matchs + cotes...\n━━━━━━━━━━━━━━━━━━━━━")

    try:
        matches = await fetch_matches(ti["iso_date"], ti["label"])
    except RuntimeError as e:
        await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg.message_id, text=f"❌ *{e}*", parse_mode=ParseMode.MARKDOWN)
        return

    if not matches:
        await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg.message_id, text=f"⚽ *ORACLE*\n\n❌ Aucun match trouvé pour {ti['label']}.")
        return

    to_analyze = matches[:10]
    await bot.edit_message_text(chat_id=CHAT_ID, message_id=msg.message_id, text=f"⚽ *ORACLE — {ti['label']}*\n\n✅ *{len(matches)} matchs* avec cotes\n🔬 Analyse par 12 agents Groq...\n━━━━━━━━━━━━━━━━━━━━━")

    lessons = db.get("lessons",[])
    results = []

    for i, match in enumerate(to_analyze):
        mname = f"{match['home']} vs {match['away']}"
        comp  = match.get("competition","")
        pmsg  = await bot.send_message(chat_id=CHAT_ID, parse_mode=ParseMode.MARKDOWN, text=build_progress(i,len(to_analyze),mname,comp,{},0))
        states={ag["id"]:"wait" for ag in AGENTS}
        steps=[0]

        async def pcb(aid,status,_s=states,_st=steps,_m=pmsg,_n=mname,_c=comp,_i=i,_t=len(to_analyze)):
            if status=="run": _s[aid]="run"
            elif status=="done": _s[aid]="done"; _st[0]+=1
            pct=round(_st[0]/12*100)
            try:
                await bot.edit_message_text(chat_id=CHAT_ID,message_id=_m.message_id,parse_mode=ParseMode.MARKDOWN,text=build_progress(_i,_t,_n,_c,_s,pct))
            except: pass

        try:
            ctx_text, weather = await asyncio.gather(fetch_context(match), fetch_weather(match["home"]), return_exceptions=True)
            if isinstance(ctx_text,Exception): raise RuntimeError(f"ERREUR contexte: {ctx_text}")
            if isinstance(weather,Exception): weather="Meteo indisponible"
        except RuntimeError as e:
            await bot.edit_message_text(chat_id=CHAT_ID,message_id=pmsg.message_id,text=f"❌ {e}")
            continue

        try:
            result = await analyze_match(match,ctx_text,weather,lessons,pcb,db)
            results.append(result)
            v = result["verdict"]
            await bot.edit_message_text(chat_id=CHAT_ID,message_id=pmsg.message_id,parse_mode=ParseMode.MARKDOWN,text=f"✅ *{i+1}/{len(to_analyze)} — {mname}*\n\n`{'█'*10}  100%`\n\n🎯 *{v['pari']}*\n📊 Confiance : {v['conf']}%")
        except RuntimeError as e:
            await bot.edit_message_text(chat_id=CHAT_ID,message_id=pmsg.message_id,text=f"❌ ERREUR {mname}: {e}")
        await asyncio.sleep(1)

    if not results:
        await bot.send_message(chat_id=CHAT_ID,text="❌ Aucune analyse complétée.")
        return

    results.sort(key=lambda x:x["verdict"]["conf"],reverse=True)
    seen,top5=[],[]
    for r in results:
        p=r["verdict"].get("pari","").lower()
        pt=("btts" if "btts" in p else "over" if "plus de" in p else "under" if "moins de" in p else "nul" if "nul" in p else f"vic_{r['match']['home'][:6]}")
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

    await bot.send_message(chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,text=f"🏆 *TOP {len(top5)} PARIS — {ti['label']}*\n━━━━━━━━━━━━━━━━━━━━━")
    await asyncio.sleep(0.5)

    for rank,r in enumerate(top5,1):
        pick={**r["match"], **r["verdict"]}
        kbd=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"res:{ti['key']}:{rank-1}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{ti['key']}:{rank-1}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{ti['key']}:{rank-1}:cancel"),
        ]])
        await bot.send_message(chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,text=fmt_pick(rank,pick),reply_markup=kbd)
        await asyncio.sleep(0.5)

    await bot.send_message(chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,text="✅ *Scan terminé !*\n\nWIN / LOSS / ANNULER après chaque match.\n🧬 L'IA apprend de chaque résultat\n\n/stats  /resultats")

# ── COMMANDES ─────────────────────────────────────────────────────────────────
async def cmd_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    ti = get_target()
    kbd = InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner les matchs du jour", callback_data="launch_scan")]])
    await update.message.reply_text(f"⚽ *ORACLE FOOTBALL*\n━━━━━━━━━━━━━━━━━━━━━\n\n12 agents Groq · Cotes réelles · Auto-apprentissage\n\n/scan — Scan du jour\n/scan force — Forcer\n/stats — Statistiques\n/resultats — Paris en attente", parse_mode=ParseMode.MARKDOWN, reply_markup=kbd)

async def cmd_scan(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    force = len(context.args)>0 and context.args[0].lower()=="force"
    await run_scan(context, force=force)

async def cmd_stats(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db=load_db()
    allp=[p for s in db.get("scans",{}).values() for p in s.get("picks",[])]
    dec=[p for p in allp if p.get("result") in ["win","loss"]]
    wins=[p for p in dec if p["result"]=="win"]
    wr=round(len(wins)/len(dec)*100) if dec else 0
    nb=len(db.get("lessons",[]))
    await update.message.reply_text(f"📊 *STATISTIQUES ORACLE*\n━━━━━━━━━━━━━━━━━━━━━\n\n🎯 Paris joués : *{len(dec)}*\n✅ Gagnés : *{len(wins)}*\n📈 Win rate : *{wr}%*\n🧬 Leçons : *{nb}*", parse_mode=ParseMode.MARKDOWN)

async def cmd_resultats(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db=load_db()
    pnd=[(dk,i,p,s["date_label"]) for dk,s in db.get("scans",{}).items() for i,p in enumerate(s.get("picks",[])) if p.get("result") is None]
    if not pnd:
        await update.message.reply_text("✅ Tous les résultats saisis !")
        return
    await update.message.reply_text(f"⏳ *{len(pnd)} paris en attente*", parse_mode=ParseMode.MARKDOWN)
    for dk,idx,pick,dlabel in pnd[:10]:
        kbd=InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{dk}:{idx}:win"),InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel")]])
        await update.message.reply_text(f"📅 {dlabel}\n⚽ *{pick['home']} vs {pick['away']}*\n🎯 {pick['pari']} ({pick['conf']}%)", parse_mode=ParseMode.MARKDOWN, reply_markup=kbd)
        await asyncio.sleep(0.3)

async def handle_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.message.chat_id != CHAT_ID: return
    data = q.data
    if data == "launch_scan":
        await run_scan(context, force=False)
        return
    if data.startswith("res:"):
        _,dk,idx_s,result = data.split(":")
        idx = int(idx_s)
        db = load_db()
        scan = db.get("scans",{}).get(dk)
        if not scan or idx >= len(scan.get("picks",[])): return
        pick = scan["picks"][idx]
        prev = pick.get("result")
        if result == "cancel":
            pick["result"] = "cancelled"
            save_db(db)
            await q.edit_message_text(text=q.message.text+"\n\n🚫 *Annulé — non compté dans les stats*", parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            return
        pick["result"] = None if prev == result else result
        save_db(db)
        if pick["result"]:
            ic = "✅" if pick["result"]=="win" else "❌"
            await q.edit_message_text(text=q.message.text+f"\n\n{ic} *{pick['result'].upper()} enregistré*", parse_mode=ParseMode.MARKDOWN, reply_markup=None)
            if not prev: await trigger_learning(pick,db,context)
        else:
            kbd=InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{dk}:{idx}:win"),InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"),InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel")]])
            await q.edit_message_reply_markup(reply_markup=kbd)

async def trigger_learning(pick,db,context):
    try:
        won = pick["result"]=="win"
        txt = await call_groq("Auto-amélioration paris sportifs. Français, concis, actionnable.", f"Pari {'GAGNÉ' if won else 'PERDU'}:\nMatch: {pick['home']} vs {pick['away']}\nPari: {pick['pari']} | Confiance: {pick['conf']}%\n\n1 leçon de 2 phrases MAX.",150)
        lesson = {"id":int(datetime.now().timestamp()),"date":datetime.now().strftime("%d/%m/%Y"),"match":f"{pick['home']} vs {pick['away']}","pari":pick["pari"],"result":pick["result"],"text":txt.strip()}
        db.setdefault("lessons",[])
        db["lessons"].append(lesson)
        db["lessons"] = db["lessons"][-50:]
        save_db(db)
        ic = "🟢" if won else "🔴"
        await context.bot.send_message(chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,text=f"🧬 *Leçon apprise !*\n\n{ic} {pick['home']} vs {pick['away']} — {'WIN' if won else 'LOSS'}\n\n💡 {txt.strip()}")
    except Exception as e: log.error(f"Learning: {e}")

async def remind_yesterday(ctx):
    db = load_db()
    yd = (datetime.now()-timedelta(days=1)).strftime("%d/%m/%Y")
    scan = db.get("scans",{}).get(yd)
    if not scan: return
    pnd = [p for p in scan.get("picks",[]) if p.get("result") is None]
    if not pnd: return
    await ctx.bot.send_message(chat_id=CHAT_ID,parse_mode=ParseMode.MARKDOWN,text=f"⏰ *Résultats en attente — {yd}*\n\n{len(pnd)} paris sans résultat !\n/resultats")

async def auto_scan(ctx):
    await run_scan(ctx, force=False)

def main():
    if not TOKEN or not GROQ_KEYS or not ODDSPAPI_KEY:
        log.error("Variables manquantes")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CallbackQueryHandler(handle_callback))

    jq = app.job_queue
    jq.run_daily(auto_scan, time=datetime.strptime(f"{SCAN_HOUR:02d}:00","%H:%M").time())
    jq.run_daily(remind_yesterday, time=datetime.strptime(f"{(SCAN_HOUR+1)%24:02d}:00","%H:%M").time())

    log.info(f"Oracle Bot démarré — {len(GROQ_KEYS)} clés Groq — The Odds API actif")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
