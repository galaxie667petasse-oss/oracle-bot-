import os
import re
import json
import html
import math
import asyncio
import logging
import hashlib
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
log = logging.getLogger("oracle_bot_v4")

PARIS_TZ = pytz.timezone("Europe/Paris")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
GROQ_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS", "").replace("\n", ",").split(",") if k.strip()]
ODDS_KEY = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()
FOOTBALL_KEY = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
FOOTBALL_DATA_KEY = (os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALLDATA_KEY", "")).strip()
BANKROLL = float(os.getenv("BANKROLL", "100"))
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
MAX_MATCHES = int(os.getenv("MAX_MATCHES", "12"))
MAX_ANALYZED = int(os.getenv("MAX_ANALYZED", "10"))
DB_FILE = Path(os.getenv("DB_FILE", "oracle_db.json"))
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_INDEX = 0
ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
ODDS_MARKETS = os.getenv("ODDS_MARKETS", "h2h,totals,btts")
FOOTBALL_DATA_COMPS = ["PL", "FL1", "BL1", "SA", "PD", "CL", "ELC"]
AGENTS = [("market", "Marché / value", "💰"), ("risk", "Red team / danger", "🛡️"), ("tempo", "Buts / BTTS / rythme", "⚽"), ("judge", "Juge final", "⚖️")]
SYSTEM_PROMPTS = {
    "market": "Tu es analyste value betting football. Tu compares uniquement les marchés disponibles, les cotes, les probabilités implicites et les pièges de marché. Tu ne dois jamais inventer de blessure ou d'information non fournie. 80 mots max.",
    "risk": "Tu es analyste risque football. Tu dois chercher pourquoi le pari peut perdre : variance, match nul, rotation, motivation, faible liquidité, piège de cote. 80 mots max.",
    "tempo": "Tu es expert buts, over/under et BTTS. Tu analyses le rythme probable du match, mais uniquement à partir des marchés et du contexte fourni. 80 mots max.",
}

def esc(x: Any) -> str:
    return html.escape(str(x), quote=False)

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def now_paris() -> datetime:
    return datetime.now(PARIS_TZ)

def db_load() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.exception("Impossible de lire la DB JSON")
    return {"scans": {}, "lessons": []}

def db_save(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def validate_env() -> None:
    missing = []
    if not TELEGRAM_TOKEN: missing.append("TELEGRAM_TOKEN")
    if not CHAT_ID: missing.append("CHAT_ID")
    if not GROQ_KEYS: missing.append("GROQ_KEYS")
    if not any([ODDS_KEY, FOOTBALL_KEY, FOOTBALL_DATA_KEY]): missing.append("ODDSPAPI_KEY ou FOOTBALL_KEY ou FOOTBALL_DATA_KEY")
    if missing:
        raise RuntimeError("Variables Railway manquantes: " + ", ".join(missing))

def target_day(force_tomorrow: bool = False) -> Dict[str, str]:
    n = now_paris()
    target = n + timedelta(days=1) if force_tomorrow or n.hour >= 21 else n
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    return {"mode": "DEMAIN" if target.date() != n.date() else "AUJOURD'HUI", "iso_date": target.strftime("%Y-%m-%d"), "key": target.strftime("%Y-%m-%d"), "label": f"{jours[target.weekday()]} {target.day} {mois[target.month - 1]} {target.year}", "scanned_at": n.strftime("%Y-%m-%d %H:%M:%S")}

def next_groq_key() -> str:
    global GROQ_INDEX
    if not GROQ_KEYS: raise RuntimeError("GROQ_KEYS manquant")
    key = GROQ_KEYS[GROQ_INDEX % len(GROQ_KEYS)]
    GROQ_INDEX += 1
    return key

async def groq_call(system: str, user: str, max_tokens: int = 450, temperature: float = 0.25, json_mode: bool = False) -> str:
    payload: Dict[str, Any] = {"model": GROQ_MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": max_tokens, "temperature": temperature}
    if json_mode: payload["response_format"] = {"type": "json_object"}
    last_error = ""
    for attempt in range(5):
        headers = {"Authorization": f"Bearer {next_groq_key()}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=45) as response:
                    raw = await response.text()
                    if response.status == 429:
                        await asyncio.sleep(4 + attempt * 4); continue
                    if response.status >= 400:
                        last_error = raw[:300]; await asyncio.sleep(2); continue
                    data = json.loads(raw)
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last_error = str(exc); await asyncio.sleep(2)
    raise RuntimeError(f"Groq indisponible: {last_error[:180]}")

def parse_json_object(text: str) -> Dict[str, Any]:
    try: return json.loads(text)
    except Exception: pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match: raise ValueError("JSON absent dans la réponse IA")
    return json.loads(match.group(0))

async def fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Tuple[int, Any, str]:
    try:
        async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
            text = await response.text()
            try: data = json.loads(text)
            except Exception: data = None
            return response.status, data, text[:500]
    except Exception as exc:
        return 0, None, str(exc)

async def odds_active_sports(session: aiohttp.ClientSession) -> List[str]:
    if not ODDS_KEY: return []
    status, data, body = await fetch_json(session, "https://api.the-odds-api.com/v4/sports", params={"apiKey": ODDS_KEY})
    if status != 200 or not isinstance(data, list):
        log.warning("Odds sports list status=%s body=%s", status, body); return []
    return [str(item.get("key", "")) for item in data if str(item.get("key", "")).startswith("soccer") and item.get("active", True)]

def outcome_price(outcomes: List[Dict[str, Any]], *names: str) -> Optional[float]:
    wanted = {name.lower() for name in names if name}
    for outcome in outcomes:
        if str(outcome.get("name", "")).lower() in wanted:
            try: return float(outcome.get("price"))
            except Exception: return None
    return None

def extract_markets(event: Dict[str, Any], home: str, away: str) -> Dict[str, Any]:
    result = {"h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None, "bookmaker": "", "real_odds": False}
    bookmakers = event.get("bookmakers", []) or []
    preferred = ["pinnacle", "bet365", "unibet", "williamhill", "bwin"]
    bookmakers.sort(key=lambda b: preferred.index(b.get("key")) if b.get("key") in preferred else 99)
    for bookmaker in bookmakers:
        local = dict(result)
        for market in bookmaker.get("markets", []) or []:
            key = market.get("key"); outcomes = market.get("outcomes", []) or []
            if key == "h2h":
                local["h2h_home"] = outcome_price(outcomes, home, "Home")
                local["h2h_draw"] = outcome_price(outcomes, "Draw", "Nul")
                local["h2h_away"] = outcome_price(outcomes, away, "Away")
            elif key == "totals":
                for outcome in outcomes:
                    try: point = float(outcome.get("point")); price = float(outcome.get("price"))
                    except Exception: continue
                    name = str(outcome.get("name", "")).lower()
                    if abs(point - 2.5) < 0.01 and name == "over": local["over25"] = price
                    elif abs(point - 2.5) < 0.01 and name == "under": local["under25"] = price
            elif key == "btts":
                local["btts_yes"] = outcome_price(outcomes, "Yes", "Oui")
                local["btts_no"] = outcome_price(outcomes, "No", "Non")
        if any(local.get(k) for k in ["h2h_home", "h2h_draw", "h2h_away", "over25", "under25", "btts_yes", "btts_no"]):
            local["bookmaker"] = bookmaker.get("title") or bookmaker.get("key") or "Odds API"; local["real_odds"] = True; return local
    return result

async def fetch_odds_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not ODDS_KEY: return []
    start = f"{iso_date}T00:00:00Z"; end = f"{iso_date}T23:59:59Z"; matches: List[Dict[str, Any]] = []; seen = set()
    async with aiohttp.ClientSession() as session:
        sports = await odds_active_sports(session); log.info("The Odds API active soccer sports=%s", len(sports))
        for sport in sports[:35]:
            params = {"apiKey": ODDS_KEY, "regions": ODDS_REGIONS, "markets": ODDS_MARKETS, "oddsFormat": "decimal", "dateFormat": "iso", "commenceTimeFrom": start, "commenceTimeTo": end}
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            status, data, body = await fetch_json(session, url, params=params)
            if status == 422:
                params["markets"] = "h2h"; status, data, body = await fetch_json(session, url, params=params)
            if status != 200 or not isinstance(data, list):
                log.warning("Odds API sport=%s status=%s body=%s", sport, status, body); continue
            for event in data:
                home = event.get("home_team") or "?"; away = event.get("away_team") or "?"; event_id = event.get("id") or f"{home}-{away}-{event.get('commence_time')}"
                if event_id in seen: continue
                seen.add(event_id)
                try: dt = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception: continue
                if dt.strftime("%Y-%m-%d") != iso_date: continue
                markets = extract_markets(event, home, away)
                if not markets["real_odds"]: continue
                matches.append({"id": event_id, "source": "the_odds_api", "home": home, "away": away, "competition": sport.replace("soccer_", "").replace("_", " ").title(), "date": label, "heure": dt.strftime("%H:%M"), **markets})
    matches.sort(key=lambda m: (m.get("heure", "99:99"), m.get("competition", "")))
    return matches[:MAX_MATCHES]

async def fetch_api_football_fixtures(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_KEY: return []
    headers = {"x-apisports-key": FOOTBALL_KEY}
    async with aiohttp.ClientSession(headers=headers) as session:
        status, data, body = await fetch_json(session, "https://v3.football.api-sports.io/fixtures", params={"date": iso_date})
    if status != 200 or not isinstance(data, dict): log.warning("API-Football fixtures status=%s body=%s", status, body); return []
    matches = []
    for item in data.get("response", [])[:MAX_MATCHES]:
        fixture = item.get("fixture", {}); teams = item.get("teams", {}); league = item.get("league", {})
        try: dt = datetime.fromisoformat(fixture.get("date", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
        except Exception: continue
        if dt.strftime("%Y-%m-%d") != iso_date: continue
        matches.append({"id": str(fixture.get("id")), "source": "api_football_fixture_only", "home": teams.get("home", {}).get("name", "?"), "away": teams.get("away", {}).get("name", "?"), "competition": league.get("name", "Football"), "date": label, "heure": dt.strftime("%H:%M"), "bookmaker": "no_real_odds", "real_odds": False, "h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None})
    return matches

async def fetch_football_data_fixtures(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_DATA_KEY: return []
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}; matches = []
    async with aiohttp.ClientSession(headers=headers) as session:
        for comp in FOOTBALL_DATA_COMPS:
            status, data, body = await fetch_json(session, f"https://api.football-data.org/v4/competitions/{comp}/matches", params={"dateFrom": iso_date, "dateTo": iso_date})
            if status != 200 or not isinstance(data, dict): log.warning("football-data comp=%s status=%s body=%s", comp, status, body); continue
            for item in data.get("matches", []):
                try: dt = datetime.fromisoformat(item.get("utcDate", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception: continue
                matches.append({"id": str(item.get("id")), "source": "football_data_fixture_only", "home": item.get("homeTeam", {}).get("name", "?"), "away": item.get("awayTeam", {}).get("name", "?"), "competition": item.get("competition", {}).get("name", comp), "date": label, "heure": dt.strftime("%H:%M"), "bookmaker": "no_real_odds", "real_odds": False, "h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None})
    return matches[:MAX_MATCHES]

async def fetch_matches(iso_date: str, label: str) -> Dict[str, List[Dict[str, Any]]]:
    real_odds = await fetch_odds_matches(iso_date, label)
    if real_odds: return {"pickable": real_odds, "info_only": [], "sources": ["the_odds_api"]}
    info = []
    info.extend(await fetch_api_football_fixtures(iso_date, label))
    info.extend(await fetch_football_data_fixtures(iso_date, label))
    return {"pickable": [], "info_only": info[:MAX_MATCHES], "sources": sorted({m["source"] for m in info}) if info else []}

def implied_prob(odds: float) -> float:
    return 1.0 / odds

def remove_margin_three_way(home_odds: float, draw_odds: float, away_odds: float) -> Tuple[float, float, float]:
    ph = implied_prob(home_odds); pd = implied_prob(draw_odds); pa = implied_prob(away_odds); total = ph + pd + pa
    return (ph / total, pd / total, pa / total) if total > 0 else (ph, pd, pa)

def build_candidates(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not match.get("real_odds"): return []
    candidates = []; home = match["home"]; away = match["away"]
    if match.get("h2h_home") and match.get("h2h_draw") and match.get("h2h_away"):
        ph, pd, pa = remove_margin_three_way(float(match["h2h_home"]), float(match["h2h_draw"]), float(match["h2h_away"]))
        candidates.extend([{"type": "h2h", "pari": f"Victoire {home}", "odds": float(match["h2h_home"]), "market_prob": ph}, {"type": "draw", "pari": "Match nul", "odds": float(match["h2h_draw"]), "market_prob": pd}, {"type": "h2h", "pari": f"Victoire {away}", "odds": float(match["h2h_away"]), "market_prob": pa}])
    if match.get("over25") and match.get("under25"):
        over = float(match["over25"]); under = float(match["under25"]); po = implied_prob(over); pu = implied_prob(under); total = po + pu
        if total > 0: candidates.extend([{"type": "total", "pari": "Plus de 2.5 buts", "odds": over, "market_prob": po / total}, {"type": "total", "pari": "Moins de 2.5 buts", "odds": under, "market_prob": pu / total}])
    if match.get("btts_yes") and match.get("btts_no"):
        yes = float(match["btts_yes"]); no = float(match["btts_no"]); py = implied_prob(yes); pn = implied_prob(no); total = py + pn
        if total > 0: candidates.extend([{"type": "btts", "pari": "Les deux équipes marquent — Oui", "odds": yes, "market_prob": py / total}, {"type": "btts", "pari": "Les deux équipes marquent — Non", "odds": no, "market_prob": pn / total}])
    clean = []
    for candidate in candidates:
        odds = float(candidate["odds"])
        if 1.35 <= odds <= 4.50:
            candidate["implied_prob_pct"] = round(100 / odds, 1); clean.append(candidate)
    return clean

def league_risk_penalty(match: Dict[str, Any]) -> int:
    comp = str(match.get("competition", "")).lower(); risky_keywords = ["korea", "japan", "greece", "argentina", "brazil", "chile", "colombia", "australia", "china", "friendly", "cup"]
    return 8 if any(k in comp for k in risky_keywords) else 0

def danger_score(match: Dict[str, Any], candidate: Dict[str, Any], ai_risk: int = 50) -> int:
    odds = float(candidate["odds"]); danger = 25
    if candidate["type"] in ("h2h", "draw"): danger += 8
    if odds >= 2.4: danger += 12
    elif odds >= 2.0: danger += 6
    danger += league_risk_penalty(match)
    if not match.get("real_odds"): danger += 30
    danger += int((ai_risk - 50) * 0.25)
    return int(clamp(danger, 10, 90))

def calculate_scores(match: Dict[str, Any], candidate: Dict[str, Any], llm_prob: float, ai_risk: int) -> Dict[str, Any]:
    odds = float(candidate["odds"]); p_market = float(candidate["market_prob"]); llm_prob = clamp(llm_prob, 0.40, 0.72); p_fused = (0.78 * p_market) + (0.22 * llm_prob)
    if candidate["type"] in ("total", "btts"): p_fused += 0.015
    if candidate["type"] == "draw": p_fused -= 0.025
    if candidate["type"] == "h2h": p_fused -= 0.015
    p_fused = clamp(p_fused, 0.38, 0.76); danger = danger_score(match, candidate, ai_risk); confidence = int(clamp(round(p_fused * 100 - danger * 0.12), 52, 82))
    if odds >= 2.4: confidence = min(confidence, 72)
    if league_risk_penalty(match): confidence = min(confidence, 76)
    ev = (p_fused * odds) - 1.0; value_score = round((ev * 100) - (danger * 0.25), 2)
    if value_score < -5: confidence = min(confidence, 62)
    stake_pct = 1
    if confidence >= 78 and value_score > 4 and danger < 45: stake_pct = 3
    elif confidence >= 70 and value_score > 0 and danger < 58: stake_pct = 2
    return {"p_market": round(p_market * 100, 1), "p_fused": round(p_fused * 100, 1), "confidence": confidence, "danger": danger, "value_score": value_score, "stake_pct": stake_pct}

async def agent_report(agent_id: str, match: Dict[str, Any], candidates: List[Dict[str, Any]]) -> str:
    return await groq_call(SYSTEM_PROMPTS[agent_id], f"Match: {match['home']} vs {match['away']}\nCompétition: {match['competition']} | Heure: {match['heure']}\nBookmaker: {match.get('bookmaker')}\nCandidats autorisés:\n{json.dumps(candidates, ensure_ascii=False, indent=2)}\nDonne une analyse courte, prudente, sans inventer d'info externe.", max_tokens=220, temperature=0.25)

async def judge_pick(match: Dict[str, Any], candidates: List[Dict[str, Any]], reports: Dict[str, str]) -> Dict[str, Any]:
    system = "Tu es le juge final d'un bot de value betting football. Tu dois choisir un seul pari parmi les candidats exacts. Tu dois éviter le biais victoire domicile. Tu dois préférer BTTS/Over/Under quand le marché est plus logique. Tu réponds uniquement en JSON."
    user = f"""
Match: {match['home']} vs {match['away']}
Compétition: {match['competition']}
Heure: {match['heure']}
Bookmaker: {match.get('bookmaker')}

Candidats autorisés:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Rapports agents:
{json.dumps(reports, ensure_ascii=False, indent=2)}

Réponds uniquement ce JSON:
{{"pari":"copie exacte d'un candidat","llm_prob":0.40,"ai_risk":55,"resume":"2 ou 3 phrases courtes","risque":"risque principal en une phrase"}}
Règles: ne donne jamais plus de 0.72; si seul argument=domicile, baisse fortement; ligue secondaire=prudence.
"""
    raw = await groq_call(system, user, max_tokens=500, temperature=0.18, json_mode=True)
    try: data = parse_json_object(raw)
    except Exception:
        log.warning("Judge JSON invalide: %s", raw[:300]); data = {"pari": candidates[0]["pari"], "llm_prob": 0.55, "ai_risk": 55, "resume": "JSON IA invalide, choix par défaut prudent.", "risque": "Analyse incomplète."}
    selected_name = str(data.get("pari", "")).strip(); selected = next((c for c in candidates if c["pari"].lower() == selected_name.lower()), None)
    if not selected:
        selected = sorted(candidates, key=lambda c: (c["type"] in ("total", "btts"), -abs(float(c["odds"]) - 1.85)), reverse=True)[0]
    scores = calculate_scores(match, selected, float(data.get("llm_prob", 0.55)), int(float(data.get("ai_risk", 55))))
    return {"pari": selected["pari"], "market_type": selected["type"], "odds": round(float(selected["odds"]), 2), "resume": str(data.get("resume", ""))[:800], "risque": str(data.get("risque", ""))[:300], **scores}

async def analyze_match(match: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    candidates = build_candidates(match)
    if not candidates: return None
    reports = {}
    for agent_id in ["market", "risk", "tempo"]:
        reports[agent_id] = await agent_report(agent_id, match, candidates)
    verdict = await judge_pick(match, candidates, reports)
    return {"match": match, "verdict": verdict, "reports": reports}

def bar(pct: int, size: int = 10) -> str:
    filled = int(round(size * pct / 100)); return "█" * filled + "░" * (size - filled)

def pick_text(rank: int, pick: Dict[str, Any]) -> str:
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]; medal = medals[rank - 1] if rank <= len(medals) else f"{rank}."
    stake = round(BANKROLL * pick["stake_pct"] / 100, 2); ret = round(stake * pick["odds"], 2); profit = round(ret - stake, 2); confidence = int(pick["confidence"]); danger = int(pick["danger"])
    label = "🔥 FORT" if confidence >= 78 else "✅ BON" if confidence >= 70 else "👍 PRUDENT" if confidence >= 62 else "⚠️ FAIBLE"
    return "\n".join([f"{medal} <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>", f"🏆 {esc(pick['competition'])} · ⏰ {esc(pick['heure'])}", "━━━━━━━━━━━━━━━━━━━━━", f"🎯 <b>PARI : {esc(pick['pari'])}</b>", f"🧩 Marché : <b>{esc(pick['market_type'])}</b>", f"📊 Confiance : <code>{bar(confidence)}</code> <b>{confidence}%</b> {label}", f"⚠️ Danger : <code>{bar(danger)}</code> <b>{danger}%</b>", f"💎 Value score : <b>{pick['value_score']}</b>", f"📈 Proba marché : <b>{pick['p_market']}%</b>", f"🧠 Proba fusion : <b>{pick['p_fused']}%</b>", f"⚡ Cote : <b>{pick['odds']}</b>", f"💰 Mise : <b>{stake}€</b> ({pick['stake_pct']}% de {BANKROLL}€)", f"🎁 Si gagne : <b>{ret}€</b> · profit <b>+{profit}€</b>", f"📡 Source: {esc(pick['source'])} · bookmaker: {esc(pick['bookmaker'])}", "", f"💡 <b>Pourquoi :</b>\n{esc(pick['resume'])}", "", f"⚠️ <b>Risque :</b> {esc(pick['risque'])}"])

async def run_scan(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    db = db_load(); t = target_day()
    if not force and db.get("scans", {}).get(t["key"], {}).get("picks"):
        await context.bot.send_message(CHAT_ID, f"💾 Scan déjà fait pour {esc(t['label'])}. Utilise /scan force pour refaire.", parse_mode=ParseMode.HTML); return
    msg = await context.bot.send_message(CHAT_ID, f"⚽ <b>ORACLE V4 — {esc(t['mode'])}</b>\n📅 {esc(t['label'])}\n\n🔍 Recherche de matchs avec vraies cotes...", parse_mode=ParseMode.HTML)
    data = await fetch_matches(t["iso_date"], t["label"]); pickable = data["pickable"]; info_only = data["info_only"]
    if not pickable:
        if info_only:
            examples = "\n".join(f"• {esc(m['heure'])} — {esc(m['home'])} vs {esc(m['away'])} ({esc(m['competition'])})" for m in info_only[:8])
            await msg.edit_text(f"⚠️ <b>Aucun match avec vraies cotes trouvé pour {esc(t['label'])}</b>\n\nFixtures sans cotes exploitables:\n{examples}\n\nLa V4 refuse les picks avec cotes inventées pour éviter les faux signaux.", parse_mode=ParseMode.HTML)
        else:
            await msg.edit_text(f"❌ Aucun match trouvé pour {esc(t['label'])}. Vérifie clés API, quotas et variables Railway.", parse_mode=ParseMode.HTML)
        return
    await msg.edit_text(f"✅ <b>{len(pickable)} matchs avec vraies cotes trouvés</b>\nSources: {esc(', '.join(data['sources']))}\n🔬 Analyse IA prudente en cours...", parse_mode=ParseMode.HTML)
    results = []
    for idx, match in enumerate(pickable[:MAX_ANALYZED]):
        progress = await context.bot.send_message(CHAT_ID, f"🔬 <b>Analyse {idx + 1}/{min(MAX_ANALYZED, len(pickable))}</b>\n⚽ {esc(match['home'])} vs {esc(match['away'])}\n🏆 {esc(match['competition'])} · ⏰ {esc(match['heure'])}\n<code>{bar(15)} 15%</code>", parse_mode=ParseMode.HTML)
        try:
            analyzed = await analyze_match(match)
            if analyzed:
                verdict = analyzed["verdict"]; results.append(analyzed)
                await progress.edit_text(f"✅ <b>{esc(match['home'])} vs {esc(match['away'])}</b>\n<code>{bar(100)} 100%</code>\n🎯 {esc(verdict['pari'])}\n📊 {verdict['confidence']}% · danger {verdict['danger']}% · value {verdict['value_score']}", parse_mode=ParseMode.HTML)
            else:
                await progress.edit_text(f"⚠️ {esc(match['home'])} vs {esc(match['away'])}: aucun marché exploitable.", parse_mode=ParseMode.HTML)
        except Exception as exc:
            log.exception("Analyse échouée"); await progress.edit_text(f"❌ Erreur analyse {esc(match['home'])} vs {esc(match['away'])}: {esc(exc)}", parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.5)
    if not results:
        await context.bot.send_message(CHAT_ID, "❌ Aucune analyse exploitable."); return
    picks = []
    for result in results:
        match = result["match"]; verdict = result["verdict"]
        if verdict["confidence"] < 60: continue
        picks.append({"home": match["home"], "away": match["away"], "competition": match["competition"], "heure": match["heure"], "source": match["source"], "bookmaker": match["bookmaker"], "result": None, **verdict})
    picks.sort(key=lambda p: (p["value_score"] - 0.35 * p["danger"], p["confidence"]), reverse=True); picks = picks[:5]
    if not picks:
        await context.bot.send_message(CHAT_ID, "⚠️ Matchs analysés, mais aucun pick assez propre selon les filtres V4."); return
    db.setdefault("scans", {})[t["key"]] = {"date_key": t["key"], "date_label": t["label"], "scanned_at": t["scanned_at"], "picks": picks}; db_save(db)
    await context.bot.send_message(CHAT_ID, f"🏆 <b>TOP {len(picks)} — {esc(t['label'])}</b>\nTri: value ajustée par danger.\nLa V4 est volontairement plus prudente que la V3.", parse_mode=ParseMode.HTML)
    for idx, pick in enumerate(picks):
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{t['key']}:{idx}:win"), InlineKeyboardButton("❌ LOSS", callback_data=f"res:{t['key']}:{idx}:loss"), InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{t['key']}:{idx}:cancel")]])
        await context.bot.send_message(CHAT_ID, pick_text(idx + 1, pick), parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await context.bot.send_message(CHAT_ID, "✅ Scan terminé. /resultats pour saisir WIN/LOSS.")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner maintenant", callback_data="launch_scan")]])
    await update.message.reply_text("⚽ <b>ORACLE FOOTBALL V4</b>\n━━━━━━━━━━━━━━━━━━━━━\nBot cloud Telegram + Railway.\nSources: The Odds API + API-Football + football-data.\n\nCommandes:\n/scan\n/scan force\n/resultats\n/stats", parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    await run_scan(context, force=bool(context.args and context.args[0].lower() == "force"))

async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); pending = []
    for date_key, scan in db.get("scans", {}).items():
        for idx, pick in enumerate(scan.get("picks", [])):
            if pick.get("result") is None: pending.append((date_key, scan.get("date_label", date_key), idx, pick))
    if not pending:
        await update.message.reply_text("✅ Aucun résultat en attente."); return
    await update.message.reply_text(f"⏳ {len(pending)} picks en attente.")
    for date_key, label, idx, pick in pending[:15]:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ WIN", callback_data=f"res:{date_key}:{idx}:win"), InlineKeyboardButton("❌ LOSS", callback_data=f"res:{date_key}:{idx}:loss"), InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{date_key}:{idx}:cancel")]])
        await update.message.reply_text(f"📅 {esc(label)}\n⚽ <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>\n🎯 {esc(pick['pari'])}\n📊 {pick['confidence']}% · danger {pick['danger']}%", parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID: return
    db = db_load(); picks = []
    for scan in db.get("scans", {}).values(): picks.extend(scan.get("picks", []))
    decided = [p for p in picks if p.get("result") in ("win", "loss")]; wins = [p for p in decided if p.get("result") == "win"]; winrate = round(len(wins) / len(decided) * 100, 1) if decided else 0.0
    by_market = {}
    for pick in decided:
        market = pick.get("market_type", "?"); by_market.setdefault(market, {"w": 0, "n": 0}); by_market[market]["n"] += 1
        if pick.get("result") == "win": by_market[market]["w"] += 1
    market_lines = []
    for market, values in by_market.items():
        wr = round(values["w"] / values["n"] * 100, 1) if values["n"] else 0; market_lines.append(f"• {market}: {values['w']}/{values['n']} = {wr}%")
    await update.message.reply_text("📊 <b>STATS ORACLE</b>\n" + f"Paris décidés: <b>{len(decided)}</b>\nWins: <b>{len(wins)}</b>\nWinrate: <b>{winrate}%</b>\n\n" + ("\n".join(market_lines) if market_lines else "Pas encore assez d'historique."), parse_mode=ParseMode.HTML)

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    if query.message.chat_id != CHAT_ID: return
    if query.data == "launch_scan": await run_scan(context, force=False); return
    if not query.data.startswith("res:"): return
    _, date_key, idx_s, result = query.data.split(":"); idx = int(idx_s); db = db_load(); scan = db.get("scans", {}).get(date_key)
    if not scan or idx >= len(scan.get("picks", [])):
        await query.edit_message_text("⚠️ Pick introuvable."); return
    pick = scan["picks"][idx]; pick["result"] = "cancelled" if result == "cancel" else result; db_save(db)
    suffix = "\n\n🚫 Pick annulé." if result == "cancel" else "\n\n✅ WIN enregistré." if result == "win" else "\n\n❌ LOSS enregistré."
    try: await query.edit_message_text(query.message.text_html + suffix, parse_mode=ParseMode.HTML)
    except Exception: await query.message.reply_text(suffix)

async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_scan(context, force=False)

def main() -> None:
    validate_env(); app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start)); app.add_handler(CommandHandler("scan", cmd_scan)); app.add_handler(CommandHandler("resultats", cmd_resultats)); app.add_handler(CommandHandler("stats", cmd_stats)); app.add_handler(CallbackQueryHandler(callback))
    app.job_queue.run_daily(daily_job, time=time(hour=SCAN_HOUR, minute=0, tzinfo=PARIS_TZ), days=(0, 1, 2, 3, 4, 5, 6), chat_id=CHAT_ID)
    log.info("Oracle Bot V4 démarré — scan auto à %sh Paris", SCAN_HOUR)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
