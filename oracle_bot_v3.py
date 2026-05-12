import os
import json
import re
import asyncio
import logging
import html
import hashlib
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger("oracle_bot_v3")

TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS", "").replace("\n", ",").split(",") if k.strip()]
ODDS_KEY = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()
FOOTBALL_KEY = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
FOOTBALL_DATA_KEY = (os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALLDATA_KEY", "")).strip()
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
BANKROLL = float(os.getenv("BANKROLL", "100"))
DB_FILE = Path(os.getenv("DB_FILE", "oracle_db.json"))
PARIS_TZ = pytz.timezone("Europe/Paris")
GROQ_IDX = 0

ODDS_MARKETS = "h2h,totals,btts"
FOOTBALL_DATA_COMPS = ["PL", "FL1", "BL1", "SA", "PD", "CL", "ELC"]

AGENTS = [
    ("tact", "Tacticien", "🧠"), ("stat", "Statisticien", "📊"),
    ("phys", "Médecin/Fatigue", "🏃"), ("scout", "Ancien Scout", "🧓"),
    ("market", "Marché/Value", "💰"), ("psy", "Psychologue", "🎭"),
    ("tempo", "Rythme/Buts", "⚽"), ("risk", "Red Team", "🛡️"),
    ("judge", "Juge", "⚖️"), ("prof", "Professeur Final", "🎓"),
]

SYSTEM_BY_AGENT = {
    "tact": "Tacticien football. Styles, pressing, transitions, match-up. 60 mots max.",
    "stat": "Statisticien football. Forme, xG approximatif, dynamique, variance. 60 mots max.",
    "phys": "Médecin/coach physique. Fatigue, rotations, calendrier, intensité. 55 mots max.",
    "scout": "Ancien scout. Pièges, habitudes, lecture terrain, motivation cachée. 55 mots max.",
    "market": "Analyste value betting. Compare probas implicites, cote, pièges de marché. 65 mots max.",
    "psy": "Psychologue sportif. Pression, enjeu, motivation, domicile. 50 mots max.",
    "tempo": "Expert buts/BTTS. Rythme, Over/Under 2.5, BTTS Oui/Non. 65 mots max.",
    "risk": "Red team. Donne le meilleur contre-argument et comment le pari peut perdre. 55 mots max.",
    "judge": "Juge arbitre. Synthèse sobre des meilleurs signaux, sans certitude excessive. 75 mots max.",
}

def esc(x: Any) -> str:
    return html.escape(str(x), quote=False)

def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))

def db_load() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"scans": {}, "lessons": []}

def db_save(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def next_key() -> str:
    global GROQ_IDX
    if not GROQ_KEYS:
        raise RuntimeError("GROQ_KEYS manquante")
    key = GROQ_KEYS[GROQ_IDX % len(GROQ_KEYS)]
    GROQ_IDX += 1
    return key

def target_day() -> Dict[str, Any]:
    now = datetime.now(PARIS_TZ)
    target = now + timedelta(days=1) if now.hour >= 21 else now
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    return {
        "mode": "DEMAIN" if target.date() != now.date() else "AUJOURD'HUI",
        "label": f"{jours[target.weekday()]} {target.day} {mois[target.month - 1]} {target.year}",
        "key": target.strftime("%Y-%m-%d"),
        "iso_date": target.strftime("%Y-%m-%d"),
        "scanned_at": now.strftime("%Y-%m-%d %H:%M"),
    }

async def groq(system: str, user: str, max_tokens: int = 450, temperature: float = 0.35, json_mode: bool = False) -> str:
    payload: Dict[str, Any] = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {next_key()}", "Content-Type": "application/json"}
    last = ""
    for attempt in range(5):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=45) as r:
                    raw = await r.text()
                    if r.status == 429:
                        await asyncio.sleep(5 + 6 * attempt); continue
                    if r.status >= 400:
                        last = raw[:250]
                        await asyncio.sleep(2); continue
                    data = json.loads(raw)
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last = str(e)
            await asyncio.sleep(2)
    raise RuntimeError(f"Groq indisponible: {last[:160]}")

def outcome_price(outcomes: List[Dict[str, Any]], *names: str) -> Optional[float]:
    wants = [n.lower() for n in names if n]
    for o in outcomes:
        if str(o.get("name", "")).lower() in wants:
            try: return float(o.get("price"))
            except Exception: return None
    return None

def extract_odds_markets(event: Dict[str, Any], home: str, away: str) -> Dict[str, Any]:
    out = {"h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None, "bookmaker": ""}
    books = event.get("bookmakers", []) or []
    preferred = ["pinnacle", "bet365", "unibet", "williamhill", "bwin"]
    books.sort(key=lambda b: preferred.index(b.get("key")) if b.get("key") in preferred else 99)
    for b in books:
        local = dict(out)
        for m in b.get("markets", []) or []:
            key = m.get("key")
            outcomes = m.get("outcomes", []) or []
            if key == "h2h":
                local["h2h_home"] = outcome_price(outcomes, home, "Home")
                local["h2h_draw"] = outcome_price(outcomes, "Draw", "Nul")
                local["h2h_away"] = outcome_price(outcomes, away, "Away")
            elif key == "totals":
                for o in outcomes:
                    try: point = float(o.get("point"))
                    except Exception: continue
                    name = str(o.get("name", "")).lower()
                    if abs(point - 2.5) < 0.01 and name == "over": local["over25"] = float(o.get("price"))
                    if abs(point - 2.5) < 0.01 and name == "under": local["under25"] = float(o.get("price"))
            elif key == "btts":
                local["btts_yes"] = outcome_price(outcomes, "Yes", "Oui")
                local["btts_no"] = outcome_price(outcomes, "No", "Non")
        if any(local.get(k) for k in ["h2h_home", "over25", "btts_yes"]):
            local["bookmaker"] = b.get("title") or b.get("key") or "Odds API"
            return local
    return out

async def odds_active_sports(session: aiohttp.ClientSession) -> List[str]:
    if not ODDS_KEY: return []
    try:
        async with session.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": ODDS_KEY}, timeout=15) as r:
            if r.status != 200:
                log.warning("Odds sports list status=%s body=%s", r.status, (await r.text())[:180])
                return []
            data = await r.json()
    except Exception as e:
        log.warning("Odds sports list error: %s", e); return []
    keys = [s.get("key") for s in data if str(s.get("key", "")).startswith("soccer") and s.get("active", True)]
    return [k for k in keys if k]

async def fetch_odds_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not ODDS_KEY: return []
    start, end = f"{iso_date}T00:00:00Z", f"{iso_date}T23:59:59Z"
    matches, seen = [], set()
    async with aiohttp.ClientSession() as s:
        sports = await odds_active_sports(s)
        log.info("Odds active soccer sports=%s", len(sports))
        for sport in sports[:30]:
            params = {"apiKey": ODDS_KEY, "regions": "eu", "markets": ODDS_MARKETS, "oddsFormat": "decimal", "dateFormat": "iso", "commenceTimeFrom": start, "commenceTimeTo": end}
            try:
                async with s.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds", params=params, timeout=18) as r:
                    if r.status == 422:
                        params["markets"] = "h2h"
                        async with s.get(f"https://api.the-odds-api.com/v4/sports/{sport}/odds", params=params, timeout=18) as r2:
                            if r2.status != 200:
                                log.warning("Odds %s fallback status=%s body=%s", sport, r2.status, (await r2.text())[:120]); continue
                            data = await r2.json()
                    elif r.status != 200:
                        log.warning("Odds %s status=%s body=%s", sport, r.status, (await r.text())[:120]); continue
                    else:
                        data = await r.json()
            except Exception as e:
                log.warning("Odds %s error=%s", sport, e); continue
            for ev in data:
                home, away = ev.get("home_team") or "?", ev.get("away_team") or "?"
                eid = ev.get("id") or f"{home}-{away}-{ev.get('commence_time')}"
                if eid in seen: continue
                seen.add(eid)
                try: dt = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception: continue
                if dt.strftime("%Y-%m-%d") != iso_date: continue
                markets = extract_odds_markets(ev, home, away)
                if any(markets.get(k) for k in ["h2h_home", "over25", "under25", "btts_yes", "btts_no"]):
                    matches.append({"id": eid, "source": "the_odds_api", "home": home, "away": away, "competition": sport.replace("soccer_", "").replace("_", " ").title(), "date": label, "heure": dt.strftime("%H:%M"), **markets})
    matches.sort(key=lambda m: (m.get("heure", "99:99"), m.get("competition", "")))
    return matches[:12]

async def fetch_api_football_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_KEY: return []
    headers = {"x-apisports-key": FOOTBALL_KEY}
    url = "https://v3.football.api-sports.io/fixtures"
    matches = []
    async with aiohttp.ClientSession(headers=headers) as s:
        try:
            async with s.get(url, params={"date": iso_date}, timeout=18) as r:
                body = await r.text()
                if r.status != 200:
                    log.warning("API-Football fixtures status=%s body=%s", r.status, body[:160]); return []
                data = json.loads(body)
        except Exception as e:
            log.warning("API-Football fixtures error=%s", e); return []
    for item in data.get("response", [])[:30]:
        fixture, teams, league = item.get("fixture", {}), item.get("teams", {}), item.get("league", {})
        try: dt = datetime.fromisoformat(fixture.get("date", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
        except Exception: continue
        if dt.strftime("%Y-%m-%d") != iso_date: continue
        home = teams.get("home", {}).get("name", "?")
        away = teams.get("away", {}).get("name", "?")
        matches.append({"id": str(fixture.get("id")), "source": "api_football", "home": home, "away": away, "competition": league.get("name", "Football"), "date": label, "heure": dt.strftime("%H:%M"), "bookmaker": "no_odds", "h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None})
    return matches[:12]

async def fetch_football_data_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_DATA_KEY: return []
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    matches = []
    async with aiohttp.ClientSession(headers=headers) as s:
        for comp in FOOTBALL_DATA_COMPS:
            try:
                url = f"https://api.football-data.org/v4/competitions/{comp}/matches"
                async with s.get(url, params={"dateFrom": iso_date, "dateTo": iso_date}, timeout=15) as r:
                    body = await r.text()
                    if r.status != 200:
                        log.warning("football-data %s status=%s body=%s", comp, r.status, body[:120]); continue
                    data = json.loads(body)
            except Exception as e:
                log.warning("football-data %s error=%s", comp, e); continue
            for item in data.get("matches", []):
                try: dt = datetime.fromisoformat(item.get("utcDate", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception: continue
                home = item.get("homeTeam", {}).get("name", "?")
                away = item.get("awayTeam", {}).get("name", "?")
                matches.append({"id": str(item.get("id")), "source": "football_data", "home": home, "away": away, "competition": item.get("competition", {}).get("name", comp), "date": label, "heure": dt.strftime("%H:%M"), "bookmaker": "no_odds", "h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None})
    return matches[:12]

async def fetch_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    odds = await fetch_odds_matches(iso_date, label)
    if odds:
        log.info("Using The Odds API: %s matches", len(odds)); return odds
    api = await fetch_api_football_matches(iso_date, label)
    if api:
        log.info("Using API-Football fallback: %s matches", len(api)); return api
    fd = await fetch_football_data_matches(iso_date, label)
    if fd:
        log.info("Using football-data fallback: %s matches", len(fd)); return fd
    return []

def fallback_odds_for_no_odds(match: Dict[str, Any]) -> Dict[str, Any]:
    home = match.get("home", "")
    seed = int(hashlib.sha1(f"{home}-{match.get('away','')}-{match.get('competition','')}".encode()).hexdigest(), 16)
    fav_home = seed % 100 < 55
    h, d, a = (1.85, 3.35, 4.10) if fav_home else (2.65, 3.20, 2.35)
    o, u = (1.92, 1.88) if seed % 2 else (1.78, 2.02)
    bty, btn = (1.82, 1.95) if seed % 3 else (2.05, 1.72)
    match.update({"h2h_home": h, "h2h_draw": d, "h2h_away": a, "over25": o, "under25": u, "btts_yes": bty, "btts_no": btn, "bookmaker": "estimated"})
    return match

def build_candidates(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not any(match.get(k) for k in ["h2h_home", "over25", "btts_yes"]):
        match = fallback_odds_for_no_odds(match)
    home, away = match["home"], match["away"]
    raw = [("h2h", f"Victoire {home}", match.get("h2h_home")), ("draw", "Match nul", match.get("h2h_draw")), ("h2h", f"Victoire {away}", match.get("h2h_away")), ("total", "Plus de 2.5 buts", match.get("over25")), ("total", "Moins de 2.5 buts", match.get("under25")), ("btts", "Les deux équipes marquent — Oui", match.get("btts_yes")), ("btts", "Les deux équipes marquent — Non", match.get("btts_no"))]
    out = []
    for typ, pari, odds in raw:
        try: price = float(odds)
        except Exception: continue
        if 1.2 <= price <= 7:
            out.append({"type": typ, "pari": pari, "odds": round(price, 2), "implied_prob": round(100 / price, 1)})
    return out

def summarize_history(db: Dict[str, Any]) -> str:
    picks = [p for s in db.get("scans", {}).values() for p in s.get("picks", [])]
    decided = [p for p in picks if p.get("result") in ("win", "loss")]
    if not decided: return "Pas assez d'historique."
    parts = []
    for typ in ["h2h", "draw", "total", "btts"]:
        rows = [p for p in decided if p.get("market_type") == typ]
        if rows:
            wins = sum(1 for p in rows if p.get("result") == "win")
            parts.append(f"{typ}: {wins}/{len(rows)}={round(wins/len(rows)*100)}%")
    return " | ".join(parts) or "Historique insuffisant."

async def short_agent(agent_id: str, match: Dict[str, Any], candidates: List[Dict[str, Any]], context: str) -> str:
    return await groq(SYSTEM_BY_AGENT[agent_id], f"Match: {match['home']} vs {match['away']}\nCompétition: {match['competition']} {match['heure']}\nSource données: {match.get('source')} / bookmaker: {match.get('bookmaker')}\nCandidats: {json.dumps(candidates, ensure_ascii=False)}\nContexte: {context}\nChoisis les signaux utiles, pas de certitude excessive.", 170, 0.30)

def parse_json(text: str) -> Dict[str, Any]:
    try: return json.loads(text)
    except Exception: pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: raise ValueError("JSON absent")
    return json.loads(m.group(0))

def normalize_pick(raw: Dict[str, Any], match: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    pari = str(raw.get("pari") or "").strip()
    chosen = next((c for c in candidates if c["pari"].lower() == pari.lower()), None)
    if not chosen:
        p = pari.lower()
        for c in candidates:
            cl = c["pari"].lower()
            if ("btts" in p or "marquent" in p) and c["type"] == "btts": chosen = c; break
            if "plus de 2.5" in p and cl.startswith("plus"): chosen = c; break
            if "moins de 2.5" in p and cl.startswith("moins"): chosen = c; break
            if match["home"].lower() in p and match["home"].lower() in cl: chosen = c; break
            if match["away"].lower() in p and match["away"].lower() in cl: chosen = c; break
    if not chosen:
        candidates_sorted = sorted(candidates, key=lambda c: (c["type"] in ("btts", "total"), -abs(c["odds"] - 1.85)), reverse=True)
        chosen = candidates_sorted[0]
    pari = chosen["pari"]
    odds = float(chosen["odds"])
    typ = chosen["type"]
    conf = int(float(raw.get("confiance", raw.get("conf", 66))))
    if typ == "h2h": conf -= 4
    if typ in ("total", "btts"): conf += 3
    if match.get("bookmaker") == "estimated": conf -= 6
    if odds < 1.45: conf -= 7
    if 1.60 <= odds <= 2.20: conf += 2
    if odds > 3.2: conf -= 8
    seed = int(hashlib.sha1(f"{match['home']}-{match['away']}-{pari}".encode()).hexdigest(), 16)
    conf = clamp(conf + (seed % 9) - 4, 57, 90)
    mp = clamp(int(raw.get("mise_pct", 2)), 1, 5)
    if conf >= 83: mp = max(mp, 4)
    elif conf >= 74: mp = max(mp, 3)
    elif conf < 66: mp = min(mp, 2)
    value = round(conf + max(0, odds - 1.55) * 4 + (3 if typ in ("total", "btts") else 0) - (4 if match.get("bookmaker") == "estimated" else 0), 2)
    return {"pari": pari, "market_type": typ, "conf": conf, "cote_mini": round(odds, 2), "mp": mp, "value_score": value, "resume": str(raw.get("resume") or raw.get("analyse") or "Analyse courte indisponible.")[:700], "risque": str(raw.get("risque") or "Variance du football.")[:280]}

async def final_pick(match: Dict[str, Any], candidates: List[Dict[str, Any]], reports: Dict[str, str], db: Dict[str, Any]) -> Dict[str, Any]:
    system = "Professeur expert value betting football. Choisis le meilleur pari parmi les candidats. Pas forcément vainqueur: compare BTTS, Over/Under, nul, victoire. JSON seulement."
    user = f"""
MATCH: {match['home']} vs {match['away']} | {match['competition']} | {match['heure']} | source={match.get('source')} bookmaker={match.get('bookmaker')}
CANDIDATS AUTORISES:
{json.dumps(candidates, ensure_ascii=False, indent=2)}
RAPPORTS:
{json.dumps(reports, ensure_ascii=False, indent=2)}
HISTORIQUE:
{summarize_history(db)}
Réponds seulement:
{{"pari":"copie exacte d'un candidat", "confiance":58-90, "mise_pct":1-5, "resume":"3 phrases courtes: logique du pari, pourquoi ce marché, pourquoi pas les autres", "risque":"risque principal"}}
Calibration: 83+ rare. Varie les scores. Si cotes estimées, reste prudent.
"""
    raw = await groq(system, user, 430, 0.22, True)
    try: data = parse_json(raw)
    except Exception:
        log.warning("Bad JSON final: %s", raw[:300]); data = {"pari": candidates[0]["pari"], "confiance": 64, "mise_pct": 2, "resume": raw[:300], "risque": "Parsing incomplet."}
    return normalize_pick(data, match, candidates)

async def analyze_match(match: Dict[str, Any], db: Dict[str, Any], progress_cb) -> Optional[Dict[str, Any]]:
    candidates = build_candidates(match)
    if not candidates: return None
    context = await groq("Analyste football factuel. Pas d'invention précise de blessure.", f"Contexte court pour {match['home']} vs {match['away']} ({match['competition']}, {match['heure']}). 80 mots max.", 150, 0.25)
    reports = {}
    core = ["tact", "stat", "phys", "scout", "market", "psy", "tempo", "risk", "judge"]
    total = len(core) + 1
    done = 0
    for aid in core:
        await progress_cb(aid, done, total)
        reports[aid] = await short_agent(aid, match, candidates, context)
        done += 1
        await progress_cb(aid, done, total)
    await progress_cb("prof", done, total)
    verdict = await final_pick(match, candidates, reports, db)
    done += 1
    await progress_cb("prof", done, total)
    return {"match": match, "verdict": verdict, "reports": reports}

def bar(pct: int, size: int = 10) -> str:
    f = round(size * pct / 100)
    return "█" * f + "░" * (size - f)

def progress_text(i: int, total: int, m: Dict[str, Any], states: Dict[str, str], pct: int) -> str:
    lines = [f"🔬 <b>Analyse {i+1}/{total}</b> — {esc(m['home'])} vs {esc(m['away'])}", f"🏆 {esc(m['competition'])} · ⏰ {esc(m['heure'])} · source {esc(m.get('source'))}", f"<code>{bar(pct)} {pct}%</code>", ""]
    for aid, name, emoji in AGENTS:
        s = states.get(aid, "wait")
        lines.append(f"{emoji} {esc(name)} {'✅' if s == 'done' else '⚡' if s == 'run' else '⏳'}")
    return "\n".join(lines)

def pick_text(rank: int, p: Dict[str, Any]) -> str:
    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][rank-1]
    stake = round(BANKROLL * p.get("mp", 2) / 100, 2)
    odds = float(p.get("cote_mini", 1.75))
    ret = round(stake * odds, 2)
    profit = round(ret - stake, 2)
    conf = int(p.get("conf", 65))
    label = "🔥 ELITE" if conf >= 84 else "🔥 FORT" if conf >= 76 else "✅ BON" if conf >= 68 else "👍 CORRECT"
    src = p.get("source", "")
    bk = p.get("bookmaker", "")
    if bk == "estimated": bkline = "⚠️ Cotes estimées (source calendrier sans odds)"
    else: bkline = f"📡 Source: {esc(src)} · bookmaker: {esc(bk)}"
    return "\n".join([f"{medal} <b>{esc(p['home'])} vs {esc(p['away'])}</b>", f"🏆 {esc(p['comp'])} · ⏰ {esc(p['heure'])}", "━━━━━━━━━━━━━━━━━━━━━", f"🎯 <b>PARI : {esc(p['pari'])}</b>", f"🧩 Marché : <b>{esc(p.get('market_type'))}</b>", f"📊 Confiance : <code>{bar(conf)}</code> <b>{conf}%</b> {label}", f"💎 Score value : <b>{p.get('value_score')}</b>", f"⚡ Cote mini : <b>{odds}</b>", f"💰 Mise : <b>{stake}€</b> ({p.get('mp')}% de {BANKROLL}€)", f"🎁 Si gagne : <b>{ret}€</b> · profit <b>+{profit}€</b>", bkline, "", f"💡 <b>Pourquoi :</b>\n{esc(p.get('resume',''))}", "", f"⚠️ <b>Risque :</b> {esc(p.get('risque',''))}"])

async def run_scan(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    db, t, bot = db_load(), target_day(), context.bot
    if not force and db.get("scans", {}).get(t["key"], {}).get("picks"):
        await bot.send_message(CHAT_ID, f"💾 Scan déjà fait pour {esc(t['label'])}. /scan force pour refaire.", parse_mode=ParseMode.HTML); return
    msg = await bot.send_message(CHAT_ID, f"⚽ <b>ORACLE V3 — {esc(t['mode'])}</b>\n☀️ {esc(t['label'])}\n\n🔍 Multi-source: Odds API → API-Football → football-data...", parse_mode=ParseMode.HTML)
    matches = await fetch_matches(t["iso_date"], t["label"])
    if not matches:
        await msg.edit_text(f"❌ Aucun match trouvé pour {esc(t['label'])}. Vérifie tes clés APIs et quotas.", parse_mode=ParseMode.HTML); return
    await msg.edit_text(f"✅ <b>{len(matches)} matchs trouvés</b>\nSources: {esc(', '.join(sorted(set(m.get('source','?') for m in matches))))}\n🔬 Analyse Groq en cours...", parse_mode=ParseMode.HTML)
    results = []
    for i, m in enumerate(matches[:10]):
        states = {aid: "wait" for aid, _, _ in AGENTS}
        pmsg = await bot.send_message(CHAT_ID, progress_text(i, min(10, len(matches)), m, states, 0), parse_mode=ParseMode.HTML)
        async def pcb(aid: str, done: int, total: int):
            states[aid] = "done" if done > 0 else "run"
            pct = clamp(round(done / total * 100), 0, 100)
            try: await pmsg.edit_text(progress_text(i, min(10, len(matches)), m, states, pct), parse_mode=ParseMode.HTML)
            except Exception: pass
        try:
            res = await analyze_match(m, db, pcb)
            if res:
                results.append(res); v = res["verdict"]
                await pmsg.edit_text(f"✅ <b>{esc(m['home'])} vs {esc(m['away'])}</b>\n<code>{bar(100)} 100%</code>\n🎯 {esc(v['pari'])}\n📊 {v['conf']}% · value {v['value_score']}", parse_mode=ParseMode.HTML)
        except Exception as e:
            log.exception("Analyze failed")
            await pmsg.edit_text(f"❌ {esc(m['home'])} vs {esc(m['away'])}: {esc(e)}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
    if not results:
        await bot.send_message(CHAT_ID, "❌ Aucune analyse exploitable."); return
    results.sort(key=lambda r: (r["verdict"].get("conf", 0), r["verdict"].get("value_score", 0)), reverse=True)
    picks = []
    for r in results[:5]:
        m, v = r["match"], r["verdict"]
        picks.append({"home": m["home"], "away": m["away"], "comp": m["competition"], "heure": m["heure"], "source": m.get("source"), "bookmaker": m.get("bookmaker"), **v, "result": None})
    db.setdefault("scans", {})[t["key"]] = {"date_key": t["key"], "date_label": t["label"], "mode": t["mode"], "scanned_at": t["scanned_at"], "picks": picks}
    db_save(db)
    await bot.send_message(CHAT_ID, f"🏆 <b>TOP {len(picks)} — {esc(t['label'])}</b>\nTri: confiance + value score.", parse_mode=ParseMode.HTML)
    for idx, p in enumerate(picks):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{t['key']}:{idx}:win"), InlineKeyboardButton("❌ LOSS", callback_data=f"res:{t['key']}:{idx}:loss"), InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{t['key']}:{idx}:cancel")]])
        await bot.send_message(CHAT_ID, pick_text(idx+1, p), parse_mode=ParseMode.HTML, reply_markup=kb)
    await bot.send_message(CHAT_ID, "✅ Scan terminé. /resultats pour saisir WIN/LOSS.")

async def learn(pick: Dict[str, Any], db: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE):
    lesson = {"ts": datetime.now(PARIS_TZ).isoformat(), "market_type": pick.get("market_type"), "result": pick.get("result"), "text": f"{pick.get('market_type')} {pick.get('pari')} sur {pick.get('home')} vs {pick.get('away')} => {pick.get('result')} conf {pick.get('conf')}"}
    db.setdefault("lessons", []).append(lesson); db["lessons"] = db["lessons"][-100:]; db_save(db)
    await context.bot.send_message(CHAT_ID, f"🧬 Leçon enregistrée: {esc(lesson['text'])}", parse_mode=ParseMode.HTML)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner maintenant", callback_data="launch_scan")]])
    await update.message.reply_text("⚽ <b>ORACLE FOOTBALL V3</b>\n━━━━━━━━━━━━━━━━━━━━━\nMulti-source gratuit: Odds API + API-Football + football-data.\nGroq agents, marchés variés, classement value.\n\n/scan\n/scan force\n/resultats\n/stats", parse_mode=ParseMode.HTML, reply_markup=kb)

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    await run_scan(context, force=bool(context.args and context.args[0].lower() == "force"))

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); pending = []
    for dk, scan in db.get("scans", {}).items():
        for idx, p in enumerate(scan.get("picks", [])):
            if p.get("result") is None: pending.append((dk, scan.get("date_label", dk), idx, p))
    if not pending: await update.message.reply_text("✅ Aucun résultat en attente."); return
    await update.message.reply_text(f"⏳ {len(pending)} paris en attente.")
    for dk, label, idx, p in pending[:12]:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{dk}:{idx}:win"), InlineKeyboardButton("❌ LOSS", callback_data=f"res:{dk}:{idx}:loss"), InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{dk}:{idx}:cancel")]])
        await update.message.reply_text(f"📅 {esc(label)}\n⚽ <b>{esc(p['home'])} vs {esc(p['away'])}</b>\n🎯 {esc(p['pari'])} · {p['conf']}%", parse_mode=ParseMode.HTML, reply_markup=kb)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); picks = [p for s in db.get("scans", {}).values() for p in s.get("picks", [])]
    dec = [p for p in picks if p.get("result") in ("win", "loss")]; wins = [p for p in dec if p.get("result") == "win"]
    wr = round(len(wins) / len(dec) * 100, 1) if dec else 0
    await update.message.reply_text(f"📊 <b>STATS</b>\nParis décidés: {len(dec)}\nWins: {len(wins)}\nWinrate: {wr}%\nMarchés: {esc(summarize_history(db))}\nLeçons: {len(db.get('lessons', []))}", parse_mode=ParseMode.HTML)

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.message.chat_id != CHAT_ID: return
    if q.data == "launch_scan": await run_scan(context, force=False); return
    if not q.data.startswith("res:"): return
    _, dk, idx_s, result = q.data.split(":"); idx = int(idx_s)
    db = db_load(); scan = db.get("scans", {}).get(dk)
    if not scan or idx >= len(scan.get("picks", [])): return
    p = scan["picks"][idx]
    p["result"] = "cancelled" if result == "cancel" else result
    db_save(db)
    suffix = "🚫 Annulé." if result == "cancel" else f"{'✅' if result == 'win' else '❌'} <b>{result.upper()} enregistré</b>"
    await q.edit_message_text(q.message.text_html + "\n\n" + suffix, parse_mode=ParseMode.HTML)
    if result in ("win", "loss"): await learn(p, db, context)

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    await run_scan(context, force=False)

def main():
    if not TOKEN: raise SystemExit("TELEGRAM_TOKEN manquant")
    if not CHAT_ID: raise SystemExit("CHAT_ID manquant")
    if not GROQ_KEYS: raise SystemExit("GROQ_KEYS manquante")
    if not any([ODDS_KEY, FOOTBALL_KEY, FOOTBALL_DATA_KEY]): raise SystemExit("Ajoute au moins ODDSPAPI_KEY ou FOOTBALL_KEY ou FOOTBALL_DATA_KEY")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start)); app.add_handler(CommandHandler("scan", cmd_scan)); app.add_handler(CommandHandler("resultats", cmd_resultats)); app.add_handler(CommandHandler("stats", cmd_stats)); app.add_handler(CallbackQueryHandler(callback))
    app.job_queue.run_daily(daily_job, time=time(hour=SCAN_HOUR, minute=0, tzinfo=PARIS_TZ), days=(0,1,2,3,4,5,6), chat_id=CHAT_ID)
    log.info("Oracle Bot V3 démarré — scan auto à %sh Paris", SCAN_HOUR)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__": main()
