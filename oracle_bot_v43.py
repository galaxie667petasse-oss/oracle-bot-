import os, re, io, json, html, asyncio, logging
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Optional

import aiohttp, pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger("oracle_v43")
TZ = pytz.timezone("Europe/Paris")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
ODDS_KEY = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()
FOOTBALL_KEY = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
FOOTBALL_DATA_KEY = (os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALLDATA_KEY", "")).strip()
BANKROLL = float(os.getenv("BANKROLL", "100"))
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
SETTLE_HOUR = int(os.getenv("SETTLE_HOUR", "8"))
MAX_MATCHES = int(os.getenv("MAX_MATCHES", "80"))
MAX_ANALYZED = int(os.getenv("MAX_ANALYZED", "28"))
TOP_PICKS = int(os.getenv("TOP_PICKS", "4"))
MAX_H2H_TOP = int(os.getenv("MAX_H2H_TOP", "1"))
MODE = os.getenv("ORACLE_MODE", "balanced").lower().strip()
DB = Path(os.getenv("DB_FILE", "oracle_db.json"))
ODDS_MARKETS = os.getenv("ODDS_MARKETS", "h2h,totals,btts")
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
FD_COMPS = ["PL", "FL1", "BL1", "SA", "PD", "CL", "ELC"]
CFG = {"safe": (62, -2), "balanced": (58, -8), "aggressive": (56, -14)}.get(MODE, (58, -8))


def e(x): return html.escape(str(x), quote=False)
def clamp(v,a,b): return max(a,min(b,v))
def ndate(): return datetime.now(TZ).strftime("%Y-%m-%d")

def load_db():
    if DB.exists():
        try:
            d=json.loads(DB.read_text(encoding="utf-8")); d.setdefault("scans",{}); d.setdefault("learning",{}); return d
        except Exception: log.exception("DB unreadable")
    return {"scans":{},"learning":{}}

def save_db(d): DB.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding="utf-8")
def day_target():
    n=datetime.now(TZ); d=n+timedelta(days=1) if n.hour>=21 else n
    return {"key":d.strftime("%Y-%m-%d"),"label":d.strftime("%d/%m/%Y"),"at":n.isoformat()}
def valid_env():
    m=[]
    if not TOKEN:m.append("TELEGRAM_TOKEN")
    if not CHAT_ID:m.append("CHAT_ID")
    if not ODDS_KEY:m.append("ODDSPAPI_KEY")
    if m: raise RuntimeError("Variables Railway manquantes: "+", ".join(m))

async def get_json(s,url,params=None,headers=None):
    try:
        async with s.get(url,params=params,headers=headers,timeout=25) as r:
            txt=await r.text()
            try: return r.status,json.loads(txt),txt[:300]
            except Exception: return r.status,None,txt[:300]
    except Exception as ex: return 0,None,str(ex)

async def sports(s):
    st,data,body=await get_json(s,"https://api.the-odds-api.com/v4/sports",{"apiKey":ODDS_KEY})
    if st!=200 or not isinstance(data,list): log.warning("sports %s %s",st,body); return []
    return [x["key"] for x in data if str(x.get("key","")).startswith("soccer") and x.get("active",True) and "winner" not in str(x.get("key","")).lower()]

def price(outs,*names):
    wanted={x.lower() for x in names}
    for o in outs or []:
        if str(o.get("name","")).lower() in wanted:
            try:return float(o.get("price"))
            except Exception:return None
    return None

def parse_markets(ev,home,away):
    out={"h2h_home":None,"h2h_draw":None,"h2h_away":None,"over25":None,"under25":None,"btts_yes":None,"btts_no":None,"bookmaker":"","real_odds":False}
    books=ev.get("bookmakers",[]) or []; books.sort(key=lambda b:0 if b.get("key")=="pinnacle" else 1)
    for b in books:
        d=dict(out)
        for m in b.get("markets",[]) or []:
            k=m.get("key"); outs=m.get("outcomes",[]) or []
            if k=="h2h":
                d["h2h_home"]=price(outs,home,"Home"); d["h2h_draw"]=price(outs,"Draw","Nul"); d["h2h_away"]=price(outs,away,"Away")
            elif k=="totals":
                for o in outs:
                    try: p=float(o.get("point")); pr=float(o.get("price"))
                    except Exception: continue
                    nm=str(o.get("name","")).lower()
                    if abs(p-2.5)<.01 and nm=="over": d["over25"]=pr
                    if abs(p-2.5)<.01 and nm=="under": d["under25"]=pr
            elif k=="btts":
                d["btts_yes"]=price(outs,"Yes","Oui"); d["btts_no"]=price(outs,"No","Non")
        if any(d.get(x) for x in ["h2h_home","h2h_draw","h2h_away","over25","under25","btts_yes","btts_no"]):
            d["bookmaker"]=b.get("title") or b.get("key") or "bookmaker"; d["real_odds"]=True; return d
    return out

async def odds_matches(day):
    rows=[]; seen=set(); start=f"{day}T00:00:00Z"; end=f"{day}T23:59:59Z"
    async with aiohttp.ClientSession() as s:
        for sp in (await sports(s))[:60]:
            url=f"https://api.the-odds-api.com/v4/sports/{sp}/odds"
            params={"apiKey":ODDS_KEY,"regions":ODDS_REGIONS,"markets":ODDS_MARKETS,"oddsFormat":"decimal","dateFormat":"iso","commenceTimeFrom":start,"commenceTimeTo":end}
            st,data,_=await get_json(s,url,params)
            if st==422:
                params["markets"]="h2h"; st,data,_=await get_json(s,url,params)
            if st!=200 or not isinstance(data,list): continue
            for ev in data:
                h=ev.get("home_team") or "?"; a=ev.get("away_team") or "?"; eid=ev.get("id") or h+a+str(ev.get("commence_time"))
                if eid in seen: continue
                seen.add(eid)
                try: dt=datetime.fromisoformat(ev["commence_time"].replace("Z","+00:00")).astimezone(TZ)
                except Exception: continue
                if dt.strftime("%Y-%m-%d")!=day: continue
                mk=parse_markets(ev,h,a)
                if not mk["real_odds"]: continue
                rows.append({"id":eid,"date_key":day,"home":h,"away":a,"competition":sp.replace("soccer_","").replace("_"," ").title(),"heure":dt.strftime("%H:%M"),"source":"the_odds_api",**mk})
    return sorted(rows,key=lambda x:(x["heure"],x["competition"]))[:MAX_MATCHES]

def norm(x):
    x=str(x).lower().translate(str.maketrans("éèêëàáäâïîíìôöóòûüúùñçł","eeeeaaaaiiiioooouuuuncl"))
    x=re.sub(r"\b(fc|cf|sc|afc|club|f c)\b"," ",x)
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",x)).strip()
def same(a,b):
    a=norm(a); b=norm(b)
    if not a or not b:return False
    if a==b or a in b or b in a:return True
    sa=set(a.split()); sb=set(b.split())
    return bool(sa and sb and len(sa&sb)/max(1,min(len(sa),len(sb)))>=.55)

async def results(day):
    out=[]
    if FOOTBALL_KEY:
        async with aiohttp.ClientSession(headers={"x-apisports-key":FOOTBALL_KEY}) as s:
            st,data,_=await get_json(s,"https://v3.football.api-sports.io/fixtures",{"date":day})
        if st==200 and isinstance(data,dict):
            for it in data.get("response",[]):
                fx=it.get("fixture",{}); tm=it.get("teams",{}); g=it.get("goals",{})
                out.append({"home":tm.get("home",{}).get("name","?"),"away":tm.get("away",{}).get("name","?"),"status":fx.get("status",{}).get("short",""),"hg":g.get("home"),"ag":g.get("away"),"src":"api_football"})
    if not out and FOOTBALL_DATA_KEY:
        async with aiohttp.ClientSession(headers={"X-Auth-Token":FOOTBALL_DATA_KEY}) as s:
            for c in FD_COMPS:
                st,data,_=await get_json(s,f"https://api.football-data.org/v4/competitions/{c}/matches",{"dateFrom":day,"dateTo":day})
                if st==200 and isinstance(data,dict):
                    for it in data.get("matches",[]):
                        sc=it.get("score",{}).get("fullTime",{})
                        out.append({"home":it.get("homeTeam",{}).get("name","?"),"away":it.get("awayTeam",{}).get("name","?"),"status":it.get("status",""),"hg":sc.get("home"),"ag":sc.get("away"),"src":"football_data"})
    return out

def done(st):return str(st).upper() in {"FT","AET","PEN","FINISHED","MATCH FINISHED"}
def eval_pick(p,hg,ag):
    t=p.get("market_type",""); bet=p.get("pari","").lower(); total=hg+ag
    if t=="draw" or "nul" in bet:return "win" if hg==ag else "loss"
    if t=="total":return "win" if (("plus" in bet or "over" in bet) and total>=3) or (("moins" in bet or "under" in bet) and total<=2) else "loss"
    if t=="btts":
        yes="oui" in bet or "yes" in bet; both=hg>0 and ag>0; return "win" if yes==both else "loss"
    if t=="h2h":
        if same(p.get("home",""),bet):return "win" if hg>ag else "loss"
        if same(p.get("away",""),bet):return "win" if ag>hg else "loss"
    return None

def decided(db):return [p for s in db.get("scans",{}).values() for p in s.get("picks",[]) if p.get("result") in ("win","loss")]
def unit(p):return float(p.get("odds",1))-1 if p.get("result")=="win" else -1.0
def ob(o):return "low" if o<1.65 else "mid" if o<2.3 else "high" if o<3.2 else "very_high"
def lb(c):
    c=str(c).lower()
    if any(x in c for x in ["la liga","epl","premier","serie a","bundesliga","ligue 1","champions","europa"]):return "major"
    if any(x in c for x in ["argentina","sweden","poland","korea","japan","greece","cup","friendly"]):return "volatile"
    return "other"
def grouping(rows,fn):
    d={}
    for p in rows:
        k=fn(p); d.setdefault(k,{"n":0,"w":0,"profit":0.0}); d[k]["n"]+=1; d[k]["w"]+=p["result"]=="win"; d[k]["profit"]+=unit(p)
    for v in d.values():v["wr"]=round(v["w"]/v["n"]*100,1); v["roi"]=round(v["profit"]/v["n"]*100,1)
    return d
def learning(db):
    rows=decided(db)
    return {"samples":len(rows),"by_market":grouping(rows,lambda p:p.get("market_type","?")),"by_odds":grouping(rows,lambda p:ob(float(p.get("odds",2)))),"by_league":grouping(rows,lambda p:lb(p.get("competition","")))}
def ml(match,cand,db):
    prof=db.get("learning") or learning(db)
    if prof.get("samples",0)<20:return 0.0
    adj=0.0
    for sec,key in [("by_market",cand["type"]),("by_odds",ob(cand["odds"])),("by_league",lb(match["competition"]))]:
        st=prof.get(sec,{}).get(key)
        if st and st.get("n",0)>=8:adj+=clamp(st.get("roi",0)/100*10,-6,6)
    return round(adj,2)

async def auto_settle(context=None,force=False):
    db=load_db(); today=ndate(); ds=[d for d,s in db["scans"].items() if (force or d<=today) and any(p.get("result") is None for p in s.get("picks",[]))]
    w=l=pnd=sett=0
    for d in sorted(set(ds)):
        fixtures=await results(d)
        for p in db["scans"].get(d,{}).get("picks",[]):
            if p.get("result") is not None:continue
            fx=next((f for f in fixtures if same(p.get("home",""),f.get("home","")) and same(p.get("away",""),f.get("away",""))),None)
            if not fx or not done(fx["status"]) or fx["hg"] is None or fx["ag"] is None:pnd+=1;continue
            r=eval_pick(p,int(fx["hg"]),int(fx["ag"]))
            if not r:pnd+=1;continue
            p["result"]=r;p["score"]=f"{fx['hg']}-{fx['ag']}";p["settlement_source"]=fx["src"];p["settled_at"]=datetime.now(TZ).isoformat();sett+=1;w+=r=="win";l+=r=="loss"
    db["learning"]=learning(db);save_db(db)
    if context and sett:await context.bot.send_message(CHAT_ID,f"🧾 <b>Résultats auto</b>\n✅ {w} WIN · ❌ {l} LOSS · ⏳ {pnd} pending\n🧠 ML: {db['learning']['samples']} résultats",parse_mode=ParseMode.HTML)
    return {"settled":sett,"wins":w,"losses":l,"pending":pnd}

def n2(a,b):pa,pb=1/a,1/b;s=pa+pb;return pa/s,pb/s
def n3(a,b,c):pa,pb,pc=1/a,1/b,1/c;s=pa+pb+pc;return pa/s,pb/s,pc/s
def cands(m):
    out=[]
    if m.get("h2h_home") and m.get("h2h_draw") and m.get("h2h_away"):
        ph,pd,pa=n3(float(m["h2h_home"]),float(m["h2h_draw"]),float(m["h2h_away"]));out+=[{"type":"h2h","pari":f"Victoire {m['home']}","odds":float(m["h2h_home"]),"market_prob":ph},{"type":"draw","pari":"Match nul","odds":float(m["h2h_draw"]),"market_prob":pd},{"type":"h2h","pari":f"Victoire {m['away']}","odds":float(m["h2h_away"]),"market_prob":pa}]
    if m.get("over25") and m.get("under25"):
        po,pu=n2(float(m["over25"]),float(m["under25"]));out+=[{"type":"total","pari":"Plus de 2.5 buts","odds":float(m["over25"]),"market_prob":po},{"type":"total","pari":"Moins de 2.5 buts","odds":float(m["under25"]),"market_prob":pu}]
    if m.get("btts_yes") and m.get("btts_no"):
        py,pn=n2(float(m["btts_yes"]),float(m["btts_no"]));out+=[{"type":"btts","pari":"Les deux équipes marquent - Oui","odds":float(m["btts_yes"]),"market_prob":py},{"type":"btts","pari":"Les deux équipes marquent - Non","odds":float(m["btts_no"]),"market_prob":pn}]
    for x in out:x["match_id"]=m["id"]
    return [x for x in out if 1.35<=x["odds"]<=4.5]
def pre(m,c,db):
    o,p,t=c["odds"],c["market_prob"],c["type"];s=100*p+max(0,o-1.55)*7+(9 if t in ("total","btts") else -5 if t=="draw" else -4)
    s+=8 if 1.6<=o<=2.25 else -12 if o>=3.2 else 0;s-={"major":0,"other":4,"volatile":9}[lb(m["competition"])];s+=ml(m,c,db);return round(s,2)
def pool(matches,db):
    x=[]
    for m in matches:
        for c in cands(m):x.append({"match":m,"candidate":c,"prefilter_score":pre(m,c,db)})
    return sorted(x,key=lambda z:z["prefilter_score"],reverse=True)
def score(m,c,pre_score,db):
    o,p,t=c["odds"],c["market_prob"],c["type"];fused=clamp(p+(0.035 if t in ("total","btts") else 0.015 if t=="h2h" else 0.005),.34,.72);edge=fused-p
    danger=25+{"major":0,"other":4,"volatile":9}[lb(m["competition"])] +(14 if t=="draw" else 7 if t=="h2h" else 2)+(16 if o>=3.2 else 8 if o>=2.7 else 5 if o>=2.25 else 0)
    adj=ml(m,c,db);conf=int(clamp(round(50+fused*34+edge*45-danger*.10+adj*.3),52,78));
    if o>=3.2:conf=min(conf,60)
    ev=fused*o-1;val=ev*100+edge*60+(8 if t in ("total","btts") else 0)+pre_score*.08-danger*.12+adj-(18 if o>=3.2 else 0)
    stake=1 if o>=3.2 else 2 if conf>=64 and danger<66 else 1
    return {"confidence":conf,"danger":int(danger),"value_score":round(val,2),"ev_pct":round(ev*100,1),"p_market":round(p*100,1),"p_fused":round(fused*100,1),"edge_pct":round(edge*100,1),"stake_pct":stake,"learning_adj":adj}
def pick_cards(rows):
    rows=sorted(rows,key=lambda p:(p["value_score"]-.25*p["danger"],p["confidence"]),reverse=True);out=[];seen=set();h2h=0
    order=[p for p in rows if p["market_type"] in ("total","btts")]+[p for p in rows if p["market_type"] in ("draw","h2h")]
    for p in order:
        if p["match_id"] in seen:continue
        if p["market_type"]=="h2h" and h2h>=MAX_H2H_TOP:continue
        if len(out)>=3 and (p["confidence"]<CFG[0] or p["value_score"]<CFG[1]):continue
        out.append(p);seen.add(p["match_id"]);h2h+=p["market_type"]=="h2h"
        if len(out)>=TOP_PICKS:break
    return out
def qual(p):return "A" if p["confidence"]>=70 and p["danger"]<=45 else "B" if p["confidence"]>=62 and p["danger"]<=60 else "C"
def card(i,p):
    st=round(BANKROLL*p["stake_pct"]/100,2);ret=round(st*p["odds"],2);med=["🥇","🥈","🥉","4️⃣","5️⃣"][i-1]
    return f"""{med} <b>{e(p['home'])} vs {e(p['away'])}</b>
🏆 {e(p['competition'])} · ⏰ {e(p['heure'])} · Qualité {qual(p)}

🎯 <b>{e(p['pari'])}</b>
🧩 {e(p['market_type'])} · ⚡ {p['odds']}
📊 Conf <b>{p['confidence']}%</b> · ⚠️ Danger <b>{p['danger']}%</b>
💎 Value {p['value_score']} · EV {p['ev_pct']}% · ML {p['learning_adj']}
📈 Marché {p['p_market']}% → modèle {p['p_fused']}%
💰 Mise {st} EUR · retour {ret} EUR · profit +{round(ret-st,2)} EUR

📝 Enregistré. Résultat auto demain."""
async def run_scan(ctx,force=False):
    await auto_settle(ctx,False);db=load_db();db["learning"]=learning(db);save_db(db);d=day_target()
    if not force and db["scans"].get(d["key"],{}).get("picks"):await ctx.bot.send_message(CHAT_ID,"Scan déjà fait. /scan force pour refaire.");return
    msg=await ctx.bot.send_message(CHAT_ID,f"🔎 <b>Oracle V4.3</b>\n📅 {d['label']} · Mode {MODE}\n🧠 ML samples: {db['learning'].get('samples',0)}\nRecherche...",parse_mode=ParseMode.HTML)
    matches=await odds_matches(d["key"])
    if not matches:await msg.edit_text("Aucun match avec cotes trouvé.");return
    selected=pool(matches,db)[:MAX_ANALYZED]
    await msg.edit_text(f"✅ {len(matches)} matchs avec cotes\n🧪 {len(selected)} marchés filtrés\nTri final...",parse_mode=ParseMode.HTML)
    rows=[]
    for it in selected:
        m,c=it["match"],it["candidate"];sc=score(m,c,it["prefilter_score"],db)
        rows.append({"match_id":m["id"],"date_key":d["key"],"home":m["home"],"away":m["away"],"competition":m["competition"],"heure":m["heure"],"source":m["source"],"bookmaker":m["bookmaker"],"pari":c["pari"],"market_type":c["type"],"odds":round(c["odds"],2),"result":None,**sc})
    picks=pick_cards(rows)
    db["scans"][d["key"]]={"date_key":d["key"],"date_label":d["label"],"scanned_at":d["at"],"mode":MODE,"ml_samples":db["learning"].get("samples",0),"picks":picks};save_db(db)
    await msg.edit_text(f"🏆 <b>TOP {len(picks)} — {e(d['label'])}</b>\n✅ Picks enregistrés · Auto-check demain à {SETTLE_HOUR}h",parse_mode=ParseMode.HTML)
    for i,p in enumerate(picks,1):
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN",callback_data=f"res:{d['key']}:{i-1}:win"),InlineKeyboardButton("❌ LOSS",callback_data=f"res:{d['key']}:{i-1}:loss"),InlineKeyboardButton("🚫 Annuler",callback_data=f"res:{d['key']}:{i-1}:cancel")]])
        await ctx.bot.send_message(CHAT_ID,card(i,p),parse_mode=ParseMode.HTML,reply_markup=kb)
    await ctx.bot.send_message(CHAT_ID,"✅ Scan terminé. /stats pour le suivi, /settle pour vérifier les résultats.")
def stats_text(db):
    prof=learning(db);rows=decided(db);w=sum(p["result"]=="win" for p in rows);profit=sum(unit(p) for p in rows);wr=round(w/len(rows)*100,1) if rows else 0;roi=round(profit/len(rows)*100,1) if rows else 0
    out=["📊 <b>STATS ORACLE V4.3</b>",f"🧠 Résultats appris: <b>{len(rows)}</b>",f"✅ Winrate: <b>{wr}%</b> ({w}/{len(rows)})",f"💰 ROI: <b>{roi}%</b> · profit {round(profit,2)}u",""]
    for title,key in [("Marchés","by_market"),("Cotes","by_odds"),("Ligues","by_league")]:
        out.append(f"<b>{title}</b>")
        for k,v in prof.get(key,{}).items():out.append(f"• {e(k)}: {int(v['w'])}/{int(v['n'])} · WR {v['wr']}% · ROI {v['roi']}%")
        out.append("")
    return "\n".join(out)
async def chart(ctx):
    rows=decided(load_db())
    if not rows:await ctx.bot.send_message(CHAT_ID,"Pas encore assez de résultats.");return
    try:
        import matplotlib.pyplot as plt
        x=[];y=[];c=0
        for i,p in enumerate(rows,1):c+=unit(p);x.append(i);y.append(c)
        fig,ax=plt.subplots(figsize=(8,4));ax.plot(x,y,marker="o");ax.axhline(0,linewidth=1);ax.grid(True,alpha=.3);ax.set_title("Oracle V4.3 - Profit cumulé");bio=io.BytesIO();fig.tight_layout();fig.savefig(bio,format="png",dpi=150);plt.close(fig);bio.seek(0);await ctx.bot.send_photo(CHAT_ID,bio,caption="📈 Performance cumulée")
    except Exception as ex:await ctx.bot.send_message(CHAT_ID,f"Graphique indisponible: {e(ex)}")
async def start(u,c):
    if u.effective_chat.id==CHAT_ID:await u.message.reply_text("⚽ <b>ORACLE FOOTBALL V4.3</b>\n━━━━━━━━━━━━━━\n✅ Interface propre\n✅ Picks enregistrés\n✅ Auto-settle demain\n✅ Stats + graphique\n\n/scan force\n/settle\n/stats\n/chart\n/resultats",parse_mode=ParseMode.HTML)
async def scan_cmd(u,c):
    if u.effective_chat.id==CHAT_ID:await run_scan(c,bool(c.args and c.args[0].lower()=="force"))
async def settle_cmd(u,c):
    if u.effective_chat.id==CHAT_ID:
        r=await auto_settle(c,True);await u.message.reply_text(f"🧾 Settle: {r['settled']} réglés · ✅ {r['wins']} · ❌ {r['losses']} · ⏳ {r['pending']}")
async def stats_cmd(u,c):
    if u.effective_chat.id==CHAT_ID:await u.message.reply_text(stats_text(load_db()),parse_mode=ParseMode.HTML)
async def learn_cmd(u,c):
    if u.effective_chat.id==CHAT_ID:
        db=load_db();db["learning"]=learning(db);save_db(db);await u.message.reply_text("🧠 ML recalculé.\n\n"+stats_text(db),parse_mode=ParseMode.HTML)
async def chart_cmd(u,c):
    if u.effective_chat.id==CHAT_ID:await chart(c)
async def resultats(u,c):
    if u.effective_chat.id!=CHAT_ID:return
    db=load_db();p=[]
    for dk,s in db["scans"].items():
        for i,x in enumerate(s.get("picks",[])):
            if x.get("result") is None:p.append((dk,i,x))
    if not p:await u.message.reply_text("✅ Aucun pick en attente.");return
    await u.message.reply_text(f"⏳ {len(p)} picks en attente. /settle pour vérifier.")
    for dk,i,x in p[:10]:await u.message.reply_text(f"{dk}\n{x['home']} vs {x['away']}\n{x['pari']} · conf {x['confidence']}%")
async def cb(u,c):
    q=u.callback_query;await q.answer()
    if q.message.chat_id!=CHAT_ID or not q.data.startswith("res:"):return
    _,dk,i,res=q.data.split(":");i=int(i);db=load_db();scan=db["scans"].get(dk)
    if not scan or i>=len(scan.get("picks",[])):await q.edit_message_text("Pick introuvable.");return
    scan["picks"][i]["result"]="cancelled" if res=="cancel" else res;scan["picks"][i]["manual_result"]=True;db["learning"]=learning(db);save_db(db)
    await q.edit_message_text((q.message.text_html or q.message.text)+f"\n\n{'✅ WIN' if res=='win' else '❌ LOSS' if res=='loss' else '🚫 Annulé'} enregistré.",parse_mode=ParseMode.HTML)
async def job_settle(c):await auto_settle(c,False)
async def job_scan(c):await run_scan(c,False)
def main():
    valid_env();app=Application.builder().token(TOKEN).build()
    for name,fn in [("start",start),("scan",scan_cmd),("settle",settle_cmd),("stats",stats_cmd),("learn",learn_cmd),("chart",chart_cmd),("resultats",resultats)]:app.add_handler(CommandHandler(name,fn))
    app.add_handler(CallbackQueryHandler(cb));app.job_queue.run_daily(job_settle,time=time(hour=SETTLE_HOUR,minute=0,tzinfo=TZ),days=(0,1,2,3,4,5,6),chat_id=CHAT_ID);app.job_queue.run_daily(job_scan,time=time(hour=SCAN_HOUR,minute=0,tzinfo=TZ),days=(0,1,2,3,4,5,6),chat_id=CHAT_ID)
    log.info("Oracle Bot V4.3 started mode=%s",MODE);app.run_polling(allowed_updates=Update.ALL_TYPES,drop_pending_updates=True)
if __name__=="__main__":main()
