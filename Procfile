import os, re, io, json, html, asyncio, logging
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger("oracle_bot_v42")
TZ = pytz.timezone("Europe/Paris")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS = [x.strip() for x in os.getenv("GROQ_KEYS", "").replace("\n", ",").split(",") if x.strip()]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
ODDS_KEY = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()
FOOTBALL_KEY = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
FOOTBALL_DATA_KEY = (os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALLDATA_KEY", "")).strip()

BANKROLL = float(os.getenv("BANKROLL", "100"))
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
SETTLE_HOUR = int(os.getenv("SETTLE_HOUR", "8"))
MAX_MATCHES = int(os.getenv("MAX_MATCHES", "80"))
MAX_ANALYZED = int(os.getenv("MAX_ANALYZED", "30"))
TOP_PICKS = int(os.getenv("TOP_PICKS", "5"))
ORACLE_MODE = os.getenv("ORACLE_MODE", "aggressive").strip().lower()
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "56"))
MIN_VALUE_SCORE = float(os.getenv("MIN_VALUE_SCORE", "-14"))
MAX_H2H_TOP = int(os.getenv("MAX_H2H_TOP", "1"))
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
ODDS_MARKETS = os.getenv("ODDS_MARKETS", "h2h,totals,btts")
DB_FILE = Path(os.getenv("DB_FILE", "oracle_db.json"))
FD_COMPS = ["PL", "FL1", "BL1", "SA", "PD", "CL", "ELC"]
KEY_IDX = 0

MODES = {
    "safe": {"danger_mult": 0.23, "llm_weight": 0.20, "max_conf": 78, "min_conf": max(MIN_CONFIDENCE, 64), "min_value": max(MIN_VALUE_SCORE, -2)},
    "balanced": {"danger_mult": 0.14, "llm_weight": 0.34, "max_conf": 80, "min_conf": MIN_CONFIDENCE, "min_value": MIN_VALUE_SCORE},
    "aggressive": {"danger_mult": 0.09, "llm_weight": 0.42, "max_conf": 82, "min_conf": min(MIN_CONFIDENCE, 56), "min_value": min(MIN_VALUE_SCORE, -14)},
}
CFG = MODES.get(ORACLE_MODE, MODES["balanced"])


def esc(x: Any) -> str:
    return html.escape(str(x), quote=False)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def db_load() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            db = json.loads(DB_FILE.read_text(encoding="utf-8"))
            db.setdefault("scans", {})
            db.setdefault("learning", {})
            return db
        except Exception:
            log.exception("DB unreadable")
    return {"scans": {}, "learning": {}}


def db_save(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_env() -> None:
    missing = []
    if not TOKEN: missing.append("TELEGRAM_TOKEN")
    if not CHAT_ID: missing.append("CHAT_ID")
    if not GROQ_KEYS: missing.append("GROQ_KEYS")
    if not any([ODDS_KEY, FOOTBALL_KEY, FOOTBALL_DATA_KEY]): missing.append("ODDSPAPI_KEY or FOOTBALL_KEY or FOOTBALL_DATA_KEY")
    if missing: raise RuntimeError("Missing Railway variables: " + ", ".join(missing))


def target_day() -> Dict[str, str]:
    now = datetime.now(TZ)
    target = now + timedelta(days=1) if now.hour >= 21 else now
    return {"key": target.strftime("%Y-%m-%d"), "iso_date": target.strftime("%Y-%m-%d"), "label": target.strftime("%Y-%m-%d"), "scanned_at": now.isoformat()}


def next_key() -> str:
    global KEY_IDX
    key = GROQ_KEYS[KEY_IDX % len(GROQ_KEYS)]
    KEY_IDX += 1
    return key


async def groq(system: str, user: str, max_tokens: int = 450, temp: float = 0.2, json_mode: bool = False) -> str:
    payload = {"model": GROQ_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": max_tokens, "temperature": temp}
    if json_mode: payload["response_format"] = {"type": "json_object"}
    last = ""
    for attempt in range(5):
        try:
            headers = {"Authorization": f"Bearer {next_key()}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=45) as r:
                    raw = await r.text()
                    if r.status == 429:
                        await asyncio.sleep(4 + attempt * 5); continue
                    if r.status >= 400:
                        last = raw[:300]; await asyncio.sleep(2); continue
                    return json.loads(raw)["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last = str(e); await asyncio.sleep(2)
    raise RuntimeError("Groq unavailable: " + last[:160])


def parse_json(text: str) -> Dict[str, Any]:
    try: return json.loads(text)
    except Exception: pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: raise ValueError("No JSON")
    return json.loads(m.group(0))


async def fetch_json(session: aiohttp.ClientSession, url: str, params=None, headers=None, timeout=20) -> Tuple[int, Any, str]:
    try:
        async with session.get(url, params=params, headers=headers, timeout=timeout) as r:
            text = await r.text()
            try: data = json.loads(text)
            except Exception: data = None
            return r.status, data, text[:500]
    except Exception as e:
        return 0, None, str(e)


async def odds_sports(session: aiohttp.ClientSession) -> List[str]:
    if not ODDS_KEY: return []
    st, data, body = await fetch_json(session, "https://api.the-odds-api.com/v4/sports", {"apiKey": ODDS_KEY})
    if st != 200 or not isinstance(data, list):
        log.warning("sports status=%s body=%s", st, body); return []
    return [x.get("key") for x in data if str(x.get("key", "")).startswith("soccer") and x.get("active", True) and "winner" not in str(x.get("key", ""))]


def outcome(outcomes: List[Dict[str, Any]], *names: str) -> Optional[float]:
    wanted = {n.lower() for n in names if n}
    for o in outcomes:
        if str(o.get("name", "")).lower() in wanted:
            try: return float(o.get("price"))
            except Exception: return None
    return None


def markets_from_event(ev: Dict[str, Any], home: str, away: str) -> Dict[str, Any]:
    out = {"h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None, "bookmaker": "", "real_odds": False}
    books = ev.get("bookmakers", []) or []
    pref = ["pinnacle", "bet365", "unibet", "williamhill", "bwin"]
    books.sort(key=lambda b: pref.index(b.get("key")) if b.get("key") in pref else 99)
    for b in books:
        local = dict(out)
        for m in b.get("markets", []) or []:
            key = m.get("key"); outs = m.get("outcomes", []) or []
            if key == "h2h":
                local["h2h_home"] = outcome(outs, home, "Home")
                local["h2h_draw"] = outcome(outs, "Draw", "Nul")
                local["h2h_away"] = outcome(outs, away, "Away")
            elif key == "totals":
                for o in outs:
                    try: point, price = float(o.get("point")), float(o.get("price"))
                    except Exception: continue
                    nm = str(o.get("name", "")).lower()
                    if abs(point - 2.5) < 0.01 and nm == "over": local["over25"] = price
                    if abs(point - 2.5) < 0.01 and nm == "under": local["under25"] = price
            elif key == "btts":
                local["btts_yes"] = outcome(outs, "Yes", "Oui")
                local["btts_no"] = outcome(outs, "No", "Non")
        if any(local.get(k) for k in ["h2h_home", "h2h_draw", "h2h_away", "over25", "under25", "btts_yes", "btts_no"]):
            local["bookmaker"] = b.get("title") or b.get("key") or "Odds API"
            local["real_odds"] = True
            return local
    return out


async def fetch_odds_matches(date_key: str) -> List[Dict[str, Any]]:
    if not ODDS_KEY: return []
    start, end = f"{date_key}T00:00:00Z", f"{date_key}T23:59:59Z"
    rows, seen = [], set()
    async with aiohttp.ClientSession() as s:
        sports = await odds_sports(s)
        log.info("active soccer sports=%s", len(sports))
        for sport in sports[:60]:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {"apiKey": ODDS_KEY, "regions": ODDS_REGIONS, "markets": ODDS_MARKETS, "oddsFormat": "decimal", "dateFormat": "iso", "commenceTimeFrom": start, "commenceTimeTo": end}
            st, data, body = await fetch_json(s, url, params)
            if st == 422:
                params["markets"] = "h2h"; st, data, body = await fetch_json(s, url, params)
            if st != 200 or not isinstance(data, list):
                continue
            for ev in data:
                home, away = ev.get("home_team") or "?", ev.get("away_team") or "?"
                eid = ev.get("id") or f"{home}-{away}-{ev.get('commence_time')}"
                if eid in seen: continue
                seen.add(eid)
                try: dt = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(TZ)
                except Exception: continue
                if dt.strftime("%Y-%m-%d") != date_key: continue
                mk = markets_from_event(ev, home, away)
                if not mk["real_odds"]: continue
                rows.append({"id": eid, "date_key": date_key, "home": home, "away": away, "competition": sport.replace("soccer_", "").replace("_", " ").title(), "heure": dt.strftime("%H:%M"), "source": "the_odds_api", "commence_time": ev.get("commence_time"), **mk})
    rows.sort(key=lambda x: (x.get("heure", "99:99"), x.get("competition", "")))
    return rows[:MAX_MATCHES]


def norm_team(name: str) -> str:
    name = str(name).lower()
    repl = {"é":"e","è":"e","ê":"e","ë":"e","á":"a","à":"a","ä":"a","ã":"a","å":"a","í":"i","ï":"i","ó":"o","ö":"o","ò":"o","ú":"u","ü":"u","ñ":"n","ç":"c","ø":"o","ł":"l"}
    for a, b in repl.items(): name = name.replace(a, b)
    name = re.sub(r"\b(fc|cf|sc|afc|club|f c)\b", " ", name)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name)).strip()


def team_match(a: str, b: str) -> bool:
    na, nb = norm_team(a), norm_team(b)
    if not na or not nb: return False
    if na == nb or na in nb or nb in na: return True
    wa, wb = set(na.split()), set(nb.split())
    return bool(wa and wb and len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.55)


async def api_football_results(date_key: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_KEY: return []
    headers = {"x-apisports-key": FOOTBALL_KEY}
    async with aiohttp.ClientSession(headers=headers) as s:
        st, data, body = await fetch_json(s, "https://v3.football.api-sports.io/fixtures", {"date": date_key})
    if st != 200 or not isinstance(data, dict): return []
    out = []
    for it in data.get("response", []):
        fx, teams, goals = it.get("fixture", {}), it.get("teams", {}), it.get("goals", {})
        out.append({"source": "api_football", "home": teams.get("home", {}).get("name", "?"), "away": teams.get("away", {}).get("name", "?"), "status": fx.get("status", {}).get("short", ""), "home_goals": goals.get("home"), "away_goals": goals.get("away")})
    return out


async def football_data_results(date_key: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_DATA_KEY: return []
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    out = []
    async with aiohttp.ClientSession(headers=headers) as s:
        for comp in FD_COMPS:
            st, data, body = await fetch_json(s, f"https://api.football-data.org/v4/competitions/{comp}/matches", {"dateFrom": date_key, "dateTo": date_key}, headers)
            if st != 200 or not isinstance(data, dict): continue
            for it in data.get("matches", []):
                sc = it.get("score", {}).get("fullTime", {})
                out.append({"source": "football_data", "home": it.get("homeTeam", {}).get("name", "?"), "away": it.get("awayTeam", {}).get("name", "?"), "status": it.get("status", ""), "home_goals": sc.get("home"), "away_goals": sc.get("away")})
    return out


def is_finished(status: str) -> bool:
    return str(status).upper() in {"FT", "AET", "PEN", "FINISHED", "MATCH FINISHED"}


def evaluate_pick(p: Dict[str, Any], hg: int, ag: int) -> Optional[str]:
    pari, typ = str(p.get("pari", "")).lower(), str(p.get("market_type", "")).lower()
    total = hg + ag
    if typ == "draw" or "nul" in pari: return "win" if hg == ag else "loss"
    if typ == "total" or "2.5" in pari:
        if "plus" in pari or "over" in pari: return "win" if total > 2 else "loss"
        if "moins" in pari or "under" in pari: return "win" if total < 3 else "loss"
    if typ == "btts" or "marquent" in pari:
        yes = "oui" in pari or "yes" in pari
        both = hg > 0 and ag > 0
        return "win" if both == yes else "loss"
    if typ == "h2h":
        if team_match(p.get("home", ""), pari): return "win" if hg > ag else "loss"
        if team_match(p.get("away", ""), pari): return "win" if ag > hg else "loss"
    return None


def all_decided(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [p for s in db.get("scans", {}).values() for p in s.get("picks", []) if p.get("result") in ("win", "loss")]


def unit_profit(p: Dict[str, Any]) -> float:
    return (float(p.get("odds", 1.0)) - 1.0) if p.get("result") == "win" else -1.0


def odds_bucket(odds: float) -> str:
    if odds < 1.65: return "low"
    if odds < 2.30: return "mid"
    if odds < 3.20: return "high"
    return "very_high"


def league_group(comp: str) -> str:
    c = str(comp).lower()
    if any(k in c for k in ["la liga", "epl", "premier", "serie a", "bundesliga", "ligue 1", "champions", "europa"]): return "major"
    if any(k in c for k in ["korea", "japan", "greece", "argentina", "sweden", "poland", "cup", "friendly"]): return "volatile"
    return "other"


def group_stats(rows: List[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, float]]:
    out = {}
    for p in rows:
        k = key_fn(p)
        out.setdefault(k, {"n": 0, "w": 0, "profit": 0.0})
        out[k]["n"] += 1
        out[k]["w"] += 1 if p.get("result") == "win" else 0
        out[k]["profit"] += unit_profit(p)
    for v in out.values():
        v["wr"] = round(v["w"] / v["n"] * 100, 1) if v["n"] else 0
        v["roi"] = round(v["profit"] / v["n"] * 100, 1) if v["n"] else 0
    return out


def learning_profile(db: Dict[str, Any]) -> Dict[str, Any]:
    rows = all_decided(db)
    return {"samples": len(rows), "by_market": group_stats(rows, lambda p: str(p.get("market_type", "?"))), "by_odds": group_stats(rows, lambda p: odds_bucket(float(p.get("odds", 2.0) or 2.0))), "by_league": group_stats(rows, lambda p: league_group(p.get("competition", "")))}


def learn_adj(match: Dict[str, Any], cand: Dict[str, Any], db: Dict[str, Any]) -> float:
    prof = db.get("learning") or learning_profile(db)
    if prof.get("samples", 0) < 10: return 0.0
    keys = [("by_market", cand["type"]), ("by_odds", odds_bucket(float(cand["odds"]))), ("by_league", league_group(match.get("competition", "")))]
    adj = 0.0
    for sec, key in keys:
        st = prof.get(sec, {}).get(key)
        if st and st.get("n", 0) >= 5:
            adj += clamp((float(st.get("roi", 0)) / 100) * 12, -8, 8)
    return round(adj, 2)


async def auto_settle(context: Optional[ContextTypes.DEFAULT_TYPE] = None, force: bool = False) -> Dict[str, int]:
    db = db_load()
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    dates = [dk for dk, s in db.get("scans", {}).items() if (force or dk <= today) and any(p.get("result") is None for p in s.get("picks", []))]
    settled = wins = losses = pending = 0
    for dk in sorted(set(dates)):
        fixtures = await api_football_results(dk)
        if not fixtures: fixtures = await football_data_results(dk)
        scan = db.get("scans", {}).get(dk, {})
        for p in scan.get("picks", []):
            if p.get("result") is not None: continue
            fx = next((f for f in fixtures if team_match(p.get("home", ""), f.get("home", "")) and team_match(p.get("away", ""), f.get("away", ""))), None)
            if not fx or not is_finished(fx.get("status")) or fx.get("home_goals") is None or fx.get("away_goals") is None:
                pending += 1; continue
            res = evaluate_pick(p, int(fx["home_goals"]), int(fx["away_goals"]))
            if not res:
                pending += 1; continue
            p["result"] = res
            p["score"] = f"{fx['home_goals']}-{fx['away_goals']}"
            p["settled_at"] = datetime.now(TZ).isoformat()
            p["settlement_source"] = fx.get("source")
            settled += 1; wins += 1 if res == "win" else 0; losses += 1 if res == "loss" else 0
    db["learning"] = learning_profile(db)
    db_save(db)
    if context and settled:
        await context.bot.send_message(CHAT_ID, f"Auto-settle: {settled} settled | WIN {wins} | LOSS {losses} | pending {pending}")
    return {"settled": settled, "wins": wins, "losses": losses, "pending": pending}


def implied(o: float) -> float: return 1.0 / o


def norm2(a: float, b: float) -> Tuple[float, float]:
    pa, pb = implied(a), implied(b); s = pa + pb
    return (pa / s, pb / s) if s else (pa, pb)


def norm3(a: float, b: float, c: float) -> Tuple[float, float, float]:
    pa, pb, pc = implied(a), implied(b), implied(c); s = pa + pb + pc
    return (pa / s, pb / s, pc / s) if s else (pa, pb, pc)


def league_penalty(match: Dict[str, Any]) -> int:
    return {"major": 0, "other": 4, "volatile": 8}.get(league_group(match.get("competition", "")), 4)


def candidates(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not match.get("real_odds"): return []
    h, a = match["home"], match["away"]
    rows = []
    if match.get("h2h_home") and match.get("h2h_draw") and match.get("h2h_away"):
        ph, pd, pa = norm3(float(match["h2h_home"]), float(match["h2h_draw"]), float(match["h2h_away"]))
        rows += [{"type": "h2h", "pari": f"Victoire {h}", "odds": float(match["h2h_home"]), "market_prob": ph}, {"type": "draw", "pari": "Match nul", "odds": float(match["h2h_draw"]), "market_prob": pd}, {"type": "h2h", "pari": f"Victoire {a}", "odds": float(match["h2h_away"]), "market_prob": pa}]
    if match.get("over25") and match.get("under25"):
        po, pu = norm2(float(match["over25"]), float(match["under25"]))
        rows += [{"type": "total", "pari": "Plus de 2.5 buts", "odds": float(match["over25"]), "market_prob": po}, {"type": "total", "pari": "Moins de 2.5 buts", "odds": float(match["under25"]), "market_prob": pu}]
    if match.get("btts_yes") and match.get("btts_no"):
        py, pn = norm2(float(match["btts_yes"]), float(match["btts_no"]))
        rows += [{"type": "btts", "pari": "Les deux equipes marquent - Oui", "odds": float(match["btts_yes"]), "market_prob": py}, {"type": "btts", "pari": "Les deux equipes marquent - Non", "odds": float(match["btts_no"]), "market_prob": pn}]
    clean = []
    for r in rows:
        if 1.35 <= r["odds"] <= 4.80:
            r["match_id"] = match["id"]; r["implied_prob_pct"] = round(100 / r["odds"], 1); clean.append(r)
    return clean


def pre_score(match: Dict[str, Any], cand: Dict[str, Any], db: Dict[str, Any]) -> float:
    o, p, typ = float(cand["odds"]), float(cand["market_prob"]), cand["type"]
    s = 100 * p + max(0, o - 1.55) * 9
    s += 8 if typ in ("total", "btts") else -4 if typ == "draw" else -3
    s += 7 if 1.60 <= o <= 2.35 else -7 if o > 3.20 else -8 if o < 1.50 else 0
    s -= league_penalty(match) * 0.8
    s += learn_adj(match, cand, db)
    return round(s, 2)


def market_pool(matches: List[Dict[str, Any]], db: Dict[str, Any]) -> List[Dict[str, Any]]:
    pool = []
    for m in matches:
        for c in candidates(m): pool.append({"match": m, "candidate": c, "prefilter_score": pre_score(m, c, db)})
    return sorted(pool, key=lambda x: x["prefilter_score"], reverse=True)


def danger(match: Dict[str, Any], cand: Dict[str, Any], ai_risk: int) -> int:
    o, typ = float(cand["odds"]), cand["type"]
    d = 24 + league_penalty(match) + (14 if typ == "draw" else 7 if typ == "h2h" else 2)
    d += 16 if o >= 3.20 else 12 if o >= 2.80 else 7 if o >= 2.25 else 6 if o < 1.50 else 0
    d += int((ai_risk - 50) * 0.25)
    return int(clamp(d, 10, 88))


def score_candidate(match: Dict[str, Any], cand: Dict[str, Any], llm_prob: float, ai_risk: int, prefilter: float, db: Dict[str, Any]) -> Dict[str, Any]:
    o, p, typ = float(cand["odds"]), float(cand["market_prob"]), cand["type"]
    llm_prob = clamp(llm_prob, 0.38, 0.74)
    fused = (1 - CFG["llm_weight"]) * p + CFG["llm_weight"] * llm_prob
    fused += 0.025 if typ in ("total", "btts") else -0.015 if typ == "draw" else -0.005
    fused = clamp(fused, 0.34, 0.77)
    edge = fused - p
    d = danger(match, cand, ai_risk)
    adj = learn_adj(match, cand, db)
    conf = int(clamp(round(48 + fused * 42 + edge * 45 - d * 0.10 + adj * 0.25), 52, CFG["max_conf"]))
    if o >= 3.20: conf = min(conf, 61)
    elif o >= 2.70: conf = min(conf, 73)
    if league_penalty(match) >= 8: conf = min(conf, 76)
    ev = fused * o - 1
    value = ev * 100 + edge * 70 + (6 if typ in ("total", "btts") else 0) + max(0, o - 1.65) * 2 + prefilter * 0.08 - d * CFG["danger_mult"] + adj
    if o >= 3.20: value -= 18
    stake = 1 if o >= 3.20 else 3 if conf >= 74 and value >= 0 and d < 54 else 2 if conf >= 64 and value >= CFG["min_value"] and d < 66 else 1
    return {"p_market": round(p * 100, 1), "p_fused": round(fused * 100, 1), "edge_pct": round(edge * 100, 1), "confidence": conf, "danger": d, "value_score": round(value, 2), "stake_pct": stake, "ev_pct": round(ev * 100, 1), "learning_adj": adj}


async def analyze_item(item: Dict[str, Any], db: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    m, c = item["match"], item["candidate"]
    alt = [x for x in candidates(m) if x["pari"] != c["pari"]]
    profile = db.get("learning") or learning_profile(db)
    sys = "You are a cautious football value judge. Think as Market, Risk, Tempo and Final Judge. Output JSON only. Do not invent injuries or facts."
    user = f"Match: {m['home']} vs {m['away']} | {m['competition']} | {m['heure']}\nCandidate: {json.dumps(c, ensure_ascii=False)}\nAlternatives: {json.dumps(alt, ensure_ascii=False)}\nLearning profile: {json.dumps(profile, ensure_ascii=False)}\nReturn JSON: {{\"llm_prob\":0.38-0.74,\"ai_risk\":10-90,\"resume\":\"2 short reasons\",\"risque\":\"main risk\"}}. Rules: simple H2H without edge <=0.56; odds>3.20 high risk; volatile leagues cautious; prefer BTTS/total when more coherent."
    raw = await groq(sys, user, 430, 0.18, True)
    try: data = parse_json(raw)
    except Exception: data = {"llm_prob": 0.54, "ai_risk": 58, "resume": "JSON incomplete, cautious score.", "risque": "Incomplete analysis."}
    scores = score_candidate(m, c, float(data.get("llm_prob", 0.54)), int(float(data.get("ai_risk", 58))), item["prefilter_score"], db)
    return {"match": m, "candidate": c, "verdict": {"pari": c["pari"], "market_type": c["type"], "odds": round(float(c["odds"]), 2), "resume": str(data.get("resume", ""))[:700], "risque": str(data.get("risque", ""))[:300], **scores}, "prefilter_score": item["prefilter_score"]}


def diversify(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected, seen, h2h = [], set(), 0
    ordered = [p for p in rows if p["market_type"] in ("total", "btts")] + [p for p in rows if p["market_type"] in ("draw", "h2h")]
    for p in ordered:
        if p["match_id"] in seen: continue
        if p["market_type"] == "h2h" and h2h >= MAX_H2H_TOP: continue
        if p["confidence"] < CFG["min_conf"] and len(selected) >= 3: continue
        if p["value_score"] < CFG["min_value"] and len(selected) >= 3: continue
        selected.append(p); seen.add(p["match_id"])
        if p["market_type"] == "h2h": h2h += 1
        if len(selected) >= TOP_PICKS: break
    if len(selected) < min(3, TOP_PICKS):
        for p in rows:
            if p["match_id"] not in seen and p["confidence"] >= 54:
                selected.append(p); seen.add(p["match_id"])
            if len(selected) >= min(3, TOP_PICKS): break
    return selected[:TOP_PICKS]


def bar(pct: int) -> str:
    f = int(round(10 * pct / 100)); return "#" * f + "-" * (10 - f)


def pick_text(i: int, p: Dict[str, Any]) -> str:
    stake = round(BANKROLL * p["stake_pct"] / 100, 2); ret = round(stake * p["odds"], 2); profit = round(ret - stake, 2)
    return "\n".join([f"TOP {i} - {esc(p['home'])} vs {esc(p['away'])}", f"League: {esc(p['competition'])} | Time: {esc(p['heure'])}", "----------------------", f"BET: {esc(p['pari'])}", f"Market: {esc(p['market_type'])}", f"Confidence: {bar(int(p['confidence']))} {p['confidence']}%", f"Danger: {bar(int(p['danger']))} {p['danger']}%", f"Value: {p['value_score']} | EV {p['ev_pct']}% | ML {p.get('learning_adj', 0)}", f"Market prob: {p['p_market']}% | Fused: {p['p_fused']}% | Edge: {p['edge_pct']}%", f"Odds: {p['odds']}", f"Stake: {stake} EUR ({p['stake_pct']}%)", f"Potential return: {ret} EUR | profit +{profit} EUR", f"Source: {esc(p['source'])} | bookmaker: {esc(p['bookmaker'])}", "", f"Why: {esc(p['resume'])}", f"Risk: {esc(p['risque'])}"])


async def run_scan(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    await auto_settle(context, force=False)
    db = db_load(); db["learning"] = learning_profile(db); db_save(db)
    t = target_day()
    if not force and db.get("scans", {}).get(t["key"], {}).get("picks"):
        await context.bot.send_message(CHAT_ID, f"Scan already done for {t['label']}. Use /scan force."); return
    msg = await context.bot.send_message(CHAT_ID, f"ORACLE V4.2 - {t['label']}\nMode: {ORACLE_MODE} | ML samples: {db['learning'].get('samples', 0)}\nSearching odds...")
    matches = await fetch_odds_matches(t["key"])
    if not matches:
        await msg.edit_text(f"No odds matches found for {t['label']}."); return
    pool = market_pool(matches, db)[:MAX_ANALYZED]
    total = sum(len(candidates(m)) for m in matches)
    await msg.edit_text(f"{len(matches)} matches with odds\n{len(pool)} markets selected over {total}\nML samples: {db['learning'].get('samples', 0)}\nAnalyzing...")
    analyzed = []
    for idx, item in enumerate(pool):
        m, c = item["match"], item["candidate"]
        pmsg = await context.bot.send_message(CHAT_ID, f"Market {idx+1}/{len(pool)}\n{esc(m['home'])} vs {esc(m['away'])}\n{esc(c['pari'])} @ {c['odds']}")
        try:
            res = await analyze_item(item, db)
            if res:
                analyzed.append(res); v = res["verdict"]
                await pmsg.edit_text(f"OK {esc(m['home'])} vs {esc(m['away'])}\n{esc(v['pari'])}\nConf {v['confidence']}% | danger {v['danger']}% | value {v['value_score']} | ML {v.get('learning_adj', 0)}")
        except Exception as e:
            log.exception("analysis failed"); await pmsg.edit_text(f"Analysis error: {esc(e)}")
        await asyncio.sleep(0.25)
    raw = []
    for res in analyzed:
        m, v = res["match"], res["verdict"]
        raw.append({"match_id": m["id"], "date_key": t["key"], "home": m["home"], "away": m["away"], "competition": m["competition"], "heure": m["heure"], "source": m["source"], "bookmaker": m["bookmaker"], "prefilter_score": res["prefilter_score"], "result": None, **v})
    raw.sort(key=lambda p: (p["value_score"] - 0.25 * p["danger"], p["confidence"], p["prefilter_score"]), reverse=True)
    picks = diversify(raw)
    if not picks:
        await context.bot.send_message(CHAT_ID, "No pick passed filters."); return
    db.setdefault("scans", {})[t["key"]] = {"date_key": t["key"], "date_label": t["label"], "scanned_at": t["scanned_at"], "mode": ORACLE_MODE, "ml_samples": db["learning"].get("samples", 0), "picks": picks}
    db_save(db)
    await context.bot.send_message(CHAT_ID, f"TOP {len(picks)} - {t['label']}\nMode {ORACLE_MODE} | ML samples {db['learning'].get('samples', 0)}")
    for idx, p in enumerate(picks):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("WIN", callback_data=f"res:{t['key']}:{idx}:win"), InlineKeyboardButton("LOSS", callback_data=f"res:{t['key']}:{idx}:loss"), InlineKeyboardButton("CANCEL", callback_data=f"res:{t['key']}:{idx}:cancel")]])
        await context.bot.send_message(CHAT_ID, pick_text(idx + 1, p), reply_markup=kb)
    await context.bot.send_message(CHAT_ID, "Scan done. Tomorrow /settle will auto-check results and update learning.")


def stats_text(db: Dict[str, Any]) -> str:
    prof = learning_profile(db); rows = all_decided(db); wins = sum(1 for p in rows if p.get("result") == "win"); profit = sum(unit_profit(p) for p in rows)
    wr = round(wins / len(rows) * 100, 1) if rows else 0; roi = round(profit / len(rows) * 100, 1) if rows else 0
    lines = ["STATS ORACLE V4.2", f"Samples ML: {len(rows)}", f"Winrate: {wr}% ({wins}/{len(rows)})", f"ROI unit: {roi}% | profit {round(profit, 2)}u", "", "By market"]
    for k, v in prof.get("by_market", {}).items(): lines.append(f"- {k}: {int(v['w'])}/{int(v['n'])} | WR {v['wr']}% | ROI {v['roi']}%")
    lines.append("\nBy odds")
    for k, v in prof.get("by_odds", {}).items(): lines.append(f"- {k}: {int(v['w'])}/{int(v['n'])} | WR {v['wr']}% | ROI {v['roi']}%")
    lines.append("\nBy league")
    for k, v in prof.get("by_league", {}).items(): lines.append(f"- {k}: {int(v['w'])}/{int(v['n'])} | WR {v['wr']}% | ROI {v['roi']}%")
    return "\n".join(lines)


async def send_chart(context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = all_decided(db_load())
    if not rows:
        await context.bot.send_message(CHAT_ID, "No settled picks yet for chart."); return
    try:
        import matplotlib.pyplot as plt
        x, y, cum = [], [], 0.0
        for i, p in enumerate(rows, 1): cum += unit_profit(p); x.append(i); y.append(cum)
        fig, ax = plt.subplots(figsize=(8, 4)); ax.plot(x, y, marker="o"); ax.axhline(0, linewidth=1); ax.grid(True, alpha=0.3)
        ax.set_title("Oracle V4.2 - cumulative unit profit"); ax.set_xlabel("Settled picks"); ax.set_ylabel("Units")
        bio = io.BytesIO(); fig.tight_layout(); fig.savefig(bio, format="png", dpi=150); plt.close(fig); bio.seek(0)
        await context.bot.send_photo(CHAT_ID, photo=bio, caption="Performance chart")
    except Exception as e:
        await context.bot.send_message(CHAT_ID, f"Chart unavailable: {e}")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Scan now", callback_data="launch_scan")]])
    await update.message.reply_text("ORACLE FOOTBALL V4.2\n----------------------\nScan large\nAuto-settle results\nLearning from WIN/LOSS\nStats + chart\n\n/scan force\n/settle\n/stats\n/learn\n/chart\n/resultats", reply_markup=kb)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    force = bool(context.args and context.args[0].lower() == "force")
    await run_scan(context, force=force)


async def cmd_settle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    r = await auto_settle(context, force=True)
    await update.message.reply_text(f"Settle done: {r['settled']} settled | WIN {r['wins']} | LOSS {r['losses']} | pending {r['pending']}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    await update.message.reply_text(stats_text(db_load()))


async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); db["learning"] = learning_profile(db); db_save(db)
    await update.message.reply_text("Learning profile recalculated.\n\n" + stats_text(db))


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    await send_chart(context)


async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); pending = []
    for dk, scan in db.get("scans", {}).items():
        for idx, p in enumerate(scan.get("picks", [])):
            if p.get("result") is None: pending.append((dk, idx, p))
    if not pending:
        await update.message.reply_text("No pending picks."); return
    await update.message.reply_text(f"{len(pending)} pending picks. Use /settle to auto-check.")
    for dk, idx, p in pending[:15]:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("WIN", callback_data=f"res:{dk}:{idx}:win"), InlineKeyboardButton("LOSS", callback_data=f"res:{dk}:{idx}:loss"), InlineKeyboardButton("CANCEL", callback_data=f"res:{dk}:{idx}:cancel")]])
        await update.message.reply_text(f"{dk}\n{p['home']} vs {p['away']}\n{p['pari']} | conf {p['confidence']}%", reply_markup=kb)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query; await q.answer()
    if q.message.chat_id != CHAT_ID: return
    if q.data == "launch_scan": await run_scan(context, force=False); return
    if not q.data.startswith("res:"): return
    _, dk, idx_s, res = q.data.split(":"); idx = int(idx_s)
    db = db_load(); scan = db.get("scans", {}).get(dk)
    if not scan or idx >= len(scan.get("picks", [])): await q.edit_message_text("Pick not found."); return
    pick = scan["picks"][idx]; pick["result"] = "cancelled" if res == "cancel" else res; pick["manual_result"] = True
    db["learning"] = learning_profile(db); db_save(db)
    suffix = "CANCELLED" if res == "cancel" else f"{res.upper()} saved. ML recalculated."
    try: await q.edit_message_text(q.message.text + "\n\n" + suffix)
    except Exception: await q.message.reply_text(suffix)


async def job_scan(context: ContextTypes.DEFAULT_TYPE) -> None: await run_scan(context, force=False)
async def job_settle(context: ContextTypes.DEFAULT_TYPE) -> None: await auto_settle(context, force=False)


def main() -> None:
    validate_env()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start)); app.add_handler(CommandHandler("scan", cmd_scan)); app.add_handler(CommandHandler("settle", cmd_settle)); app.add_handler(CommandHandler("stats", cmd_stats)); app.add_handler(CommandHandler("learn", cmd_learn)); app.add_handler(CommandHandler("chart", cmd_chart)); app.add_handler(CommandHandler("resultats", cmd_resultats)); app.add_handler(CallbackQueryHandler(callback))
    app.job_queue.run_daily(job_settle, time=time(hour=SETTLE_HOUR, minute=0, tzinfo=TZ), days=(0,1,2,3,4,5,6), chat_id=CHAT_ID)
    app.job_queue.run_daily(job_scan, time=time(hour=SCAN_HOUR, minute=0, tzinfo=TZ), days=(0,1,2,3,4,5,6), chat_id=CHAT_ID)
    log.info("Oracle Bot V4.2 started mode=%s scan=%s settle=%s max_matches=%s max_analyzed=%s", ORACLE_MODE, SCAN_HOUR, SETTLE_HOUR, MAX_MATCHES, MAX_ANALYZED)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__": main()
