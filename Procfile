import os
import re
import json
import html
import asyncio
import logging
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
log = logging.getLogger("oracle_bot_v41")

PARIS_TZ = pytz.timezone("Europe/Paris")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

GROQ_KEYS = [k.strip() for k in os.getenv("GROQ_KEYS", "").replace("\n", ",").split(",") if k.strip()]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

ODDS_KEY = (
    os.getenv("ODDSPAPI_KEY", "")
    or os.getenv("ODDS_API_KEY", "")
    or os.getenv("THE_ODDS_API_KEY", "")
).strip()

FOOTBALL_KEY = (
    os.getenv("FOOTBALL_KEY", "")
    or os.getenv("API_FOOTBALL_KEY", "")
    or os.getenv("APISPORTS_KEY", "")
).strip()

FOOTBALL_DATA_KEY = (
    os.getenv("FOOTBALL_DATA_KEY", "")
    or os.getenv("FOOTBALLDATA_KEY", "")
).strip()

BANKROLL = float(os.getenv("BANKROLL", "100"))
SCAN_HOUR = int(os.getenv("SCAN_HOUR", "9"))
MAX_MATCHES = int(os.getenv("MAX_MATCHES", "60"))
MAX_ANALYZED = int(os.getenv("MAX_ANALYZED", "20"))
TOP_PICKS = int(os.getenv("TOP_PICKS", "5"))
ORACLE_MODE = os.getenv("ORACLE_MODE", "balanced").strip().lower()

MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "58"))
MIN_VALUE_SCORE = float(os.getenv("MIN_VALUE_SCORE", "-8"))
MAX_H2H_TOP = int(os.getenv("MAX_H2H_TOP", "2"))

ODDS_REGIONS = os.getenv("ODDS_REGIONS", "eu")
ODDS_MARKETS = os.getenv("ODDS_MARKETS", "h2h,totals,btts")
DB_FILE = Path(os.getenv("DB_FILE", "oracle_db.json"))

FOOTBALL_DATA_COMPS = ["PL", "FL1", "BL1", "SA", "PD", "CL", "ELC"]

GROQ_INDEX = 0

MODE_CONFIG = {
    "safe": {
        "min_confidence": max(MIN_CONFIDENCE, 64),
        "min_value": max(MIN_VALUE_SCORE, -2),
        "danger_mult": 0.22,
        "llm_weight": 0.20,
        "max_conf": 78,
    },
    "balanced": {
        "min_confidence": MIN_CONFIDENCE,
        "min_value": MIN_VALUE_SCORE,
        "danger_mult": 0.14,
        "llm_weight": 0.34,
        "max_conf": 80,
    },
    "aggressive": {
        "min_confidence": min(MIN_CONFIDENCE, 56),
        "min_value": min(MIN_VALUE_SCORE, -14),
        "danger_mult": 0.09,
        "llm_weight": 0.42,
        "max_conf": 82,
    },
}

CFG = MODE_CONFIG.get(ORACLE_MODE, MODE_CONFIG["balanced"])

SYSTEM_PROMPTS = {
    "market": (
        "Tu es analyste value betting football. Compare la cote, la proba implicite, "
        "les marchés alternatifs et les pièges de marché. Pas d'invention. 80 mots max."
    ),
    "risk": (
        "Tu es red-team. Ton rôle est de dire pourquoi CE pari peut perdre. "
        "Mentionne variance, nul, motivation, ligue secondaire, cote suspecte. 80 mots max."
    ),
    "tempo": (
        "Tu es expert buts/BTTS/rythme. Dis si le marché buts ou BTTS semble meilleur "
        "que la victoire simple. 80 mots max."
    ),
}


def esc(x: Any) -> str:
    return html.escape(str(x), quote=False)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def now_paris() -> datetime:
    return datetime.now(PARIS_TZ)


def validate_env() -> None:
    missing = []
    if not TELEGRAM_TOKEN:
        missing.append("TELEGRAM_TOKEN")
    if not CHAT_ID:
        missing.append("CHAT_ID")
    if not GROQ_KEYS:
        missing.append("GROQ_KEYS")
    if not any([ODDS_KEY, FOOTBALL_KEY, FOOTBALL_DATA_KEY]):
        missing.append("ODDSPAPI_KEY ou FOOTBALL_KEY ou FOOTBALL_DATA_KEY")
    if missing:
        raise RuntimeError("Variables Railway manquantes: " + ", ".join(missing))


def db_load() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            log.exception("DB JSON illisible")
    return {"scans": {}, "lessons": []}


def db_save(db: Dict[str, Any]) -> None:
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def target_day(force_tomorrow: bool = False) -> Dict[str, str]:
    n = now_paris()
    target = n + timedelta(days=1) if force_tomorrow or n.hour >= 21 else n
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    return {
        "mode": "DEMAIN" if target.date() != n.date() else "AUJOURD'HUI",
        "iso_date": target.strftime("%Y-%m-%d"),
        "key": target.strftime("%Y-%m-%d"),
        "label": f"{jours[target.weekday()]} {target.day} {mois[target.month - 1]} {target.year}",
        "scanned_at": n.strftime("%Y-%m-%d %H:%M:%S"),
    }


def next_groq_key() -> str:
    global GROQ_INDEX
    key = GROQ_KEYS[GROQ_INDEX % len(GROQ_KEYS)]
    GROQ_INDEX += 1
    return key


async def groq_call(system: str, user: str, max_tokens: int = 450, temperature: float = 0.25, json_mode: bool = False) -> str:
    payload: Dict[str, Any] = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error = ""
    for attempt in range(5):
        headers = {"Authorization": f"Bearer {next_groq_key()}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=45,
                ) as response:
                    raw = await response.text()
                    if response.status == 429:
                        await asyncio.sleep(4 + attempt * 5)
                        continue
                    if response.status >= 400:
                        last_error = raw[:300]
                        await asyncio.sleep(2)
                        continue
                    data = json.loads(raw)
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last_error = str(exc)
            await asyncio.sleep(2)
    raise RuntimeError(f"Groq indisponible: {last_error[:180]}")


def parse_json_object(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("JSON absent")
    return json.loads(match.group(0))


async def fetch_json(session: aiohttp.ClientSession, url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 20) -> Tuple[int, Any, str]:
    try:
        async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
            text = await response.text()
            try:
                return response.status, json.loads(text), text[:500]
            except Exception:
                return response.status, None, text[:500]
    except Exception as exc:
        return 0, None, str(exc)


async def odds_active_sports(session: aiohttp.ClientSession) -> List[str]:
    if not ODDS_KEY:
        return []
    status, data, body = await fetch_json(session, "https://api.the-odds-api.com/v4/sports", params={"apiKey": ODDS_KEY})
    if status != 200 or not isinstance(data, list):
        log.warning("Odds sports list status=%s body=%s", status, body)
        return []
    return [str(s.get("key")) for s in data if str(s.get("key", "")).startswith("soccer") and s.get("active", True)]


def outcome_price(outcomes: List[Dict[str, Any]], *names: str) -> Optional[float]:
    wanted = {n.lower() for n in names if n}
    for outcome in outcomes:
        if str(outcome.get("name", "")).lower() in wanted:
            try:
                return float(outcome.get("price"))
            except Exception:
                return None
    return None


def extract_markets(event: Dict[str, Any], home: str, away: str) -> Dict[str, Any]:
    result = {
        "h2h_home": None,
        "h2h_draw": None,
        "h2h_away": None,
        "over25": None,
        "under25": None,
        "btts_yes": None,
        "btts_no": None,
        "bookmaker": "",
        "real_odds": False,
    }
    bookmakers = event.get("bookmakers", []) or []
    preferred = ["pinnacle", "bet365", "unibet", "williamhill", "bwin"]
    bookmakers.sort(key=lambda b: preferred.index(b.get("key")) if b.get("key") in preferred else 99)

    for bookmaker in bookmakers:
        local = dict(result)
        for market in bookmaker.get("markets", []) or []:
            key = market.get("key")
            outcomes = market.get("outcomes", []) or []
            if key == "h2h":
                local["h2h_home"] = outcome_price(outcomes, home, "Home")
                local["h2h_draw"] = outcome_price(outcomes, "Draw", "Nul")
                local["h2h_away"] = outcome_price(outcomes, away, "Away")
            elif key == "totals":
                for outcome in outcomes:
                    try:
                        point = float(outcome.get("point"))
                        price = float(outcome.get("price"))
                    except Exception:
                        continue
                    name = str(outcome.get("name", "")).lower()
                    if abs(point - 2.5) < 0.01 and name == "over":
                        local["over25"] = price
                    if abs(point - 2.5) < 0.01 and name == "under":
                        local["under25"] = price
            elif key == "btts":
                local["btts_yes"] = outcome_price(outcomes, "Yes", "Oui")
                local["btts_no"] = outcome_price(outcomes, "No", "Non")

        if any(local.get(k) for k in ["h2h_home", "h2h_draw", "h2h_away", "over25", "under25", "btts_yes", "btts_no"]):
            local["bookmaker"] = bookmaker.get("title") or bookmaker.get("key") or "Odds API"
            local["real_odds"] = True
            return local

    return result


async def fetch_odds_matches(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not ODDS_KEY:
        return []

    start = f"{iso_date}T00:00:00Z"
    end = f"{iso_date}T23:59:59Z"
    matches: List[Dict[str, Any]] = []
    seen = set()

    async with aiohttp.ClientSession() as session:
        sports = await odds_active_sports(session)
        log.info("The Odds API active soccer sports=%s", len(sports))
        for sport in sports[:50]:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {
                "apiKey": ODDS_KEY,
                "regions": ODDS_REGIONS,
                "markets": ODDS_MARKETS,
                "oddsFormat": "decimal",
                "dateFormat": "iso",
                "commenceTimeFrom": start,
                "commenceTimeTo": end,
            }
            status, data, body = await fetch_json(session, url, params=params)

            if status == 422:
                params["markets"] = "h2h"
                status, data, body = await fetch_json(session, url, params=params)

            if status != 200 or not isinstance(data, list):
                log.warning("Odds API sport=%s status=%s body=%s", sport, status, body)
                continue

            for event in data:
                home = event.get("home_team") or "?"
                away = event.get("away_team") or "?"
                event_id = event.get("id") or f"{home}-{away}-{event.get('commence_time')}"
                if event_id in seen:
                    continue
                seen.add(event_id)
                try:
                    dt = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception:
                    continue
                if dt.strftime("%Y-%m-%d") != iso_date:
                    continue

                markets = extract_markets(event, home, away)
                if not markets["real_odds"]:
                    continue

                matches.append({
                    "id": event_id,
                    "source": "the_odds_api",
                    "home": home,
                    "away": away,
                    "competition": sport.replace("soccer_", "").replace("_", " ").title(),
                    "date": label,
                    "heure": dt.strftime("%H:%M"),
                    **markets,
                })

    matches.sort(key=lambda m: (m.get("heure", "99:99"), m.get("competition", "")))
    return matches[:MAX_MATCHES]


async def fetch_api_football_fixtures(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_KEY:
        return []
    headers = {"x-apisports-key": FOOTBALL_KEY}
    async with aiohttp.ClientSession(headers=headers) as session:
        status, data, body = await fetch_json(session, "https://v3.football.api-sports.io/fixtures", params={"date": iso_date})
    if status != 200 or not isinstance(data, dict):
        log.warning("API-Football fixtures status=%s body=%s", status, body)
        return []

    out = []
    for item in data.get("response", [])[:MAX_MATCHES]:
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        league = item.get("league", {})
        try:
            dt = datetime.fromisoformat(fixture.get("date", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
        except Exception:
            continue
        if dt.strftime("%Y-%m-%d") != iso_date:
            continue
        out.append({
            "id": str(fixture.get("id")),
            "source": "api_football_fixture_only",
            "home": teams.get("home", {}).get("name", "?"),
            "away": teams.get("away", {}).get("name", "?"),
            "competition": league.get("name", "Football"),
            "date": label,
            "heure": dt.strftime("%H:%M"),
            "bookmaker": "no_real_odds",
            "real_odds": False,
        })
    return out


async def fetch_football_data_fixtures(iso_date: str, label: str) -> List[Dict[str, Any]]:
    if not FOOTBALL_DATA_KEY:
        return []
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    out = []
    async with aiohttp.ClientSession(headers=headers) as session:
        for comp in FOOTBALL_DATA_COMPS:
            status, data, body = await fetch_json(
                session,
                f"https://api.football-data.org/v4/competitions/{comp}/matches",
                params={"dateFrom": iso_date, "dateTo": iso_date},
            )
            if status != 200 or not isinstance(data, dict):
                log.warning("football-data comp=%s status=%s body=%s", comp, status, body)
                continue
            for item in data.get("matches", []):
                try:
                    dt = datetime.fromisoformat(item.get("utcDate", "").replace("Z", "+00:00")).astimezone(PARIS_TZ)
                except Exception:
                    continue
                out.append({
                    "id": str(item.get("id")),
                    "source": "football_data_fixture_only",
                    "home": item.get("homeTeam", {}).get("name", "?"),
                    "away": item.get("awayTeam", {}).get("name", "?"),
                    "competition": item.get("competition", {}).get("name", comp),
                    "date": label,
                    "heure": dt.strftime("%H:%M"),
                    "bookmaker": "no_real_odds",
                    "real_odds": False,
                })
    return out[:MAX_MATCHES]


async def fetch_matches(iso_date: str, label: str) -> Dict[str, List[Dict[str, Any]]]:
    pickable = await fetch_odds_matches(iso_date, label)
    if pickable:
        return {"pickable": pickable, "info_only": [], "sources": ["the_odds_api"]}

    info = []
    info.extend(await fetch_api_football_fixtures(iso_date, label))
    info.extend(await fetch_football_data_fixtures(iso_date, label))
    return {"pickable": [], "info_only": info[:MAX_MATCHES], "sources": sorted({m["source"] for m in info})}


def implied_prob(odds: float) -> float:
    return 1.0 / odds


def normalize_two_way(a: float, b: float) -> Tuple[float, float]:
    pa, pb = implied_prob(a), implied_prob(b)
    s = pa + pb
    return (pa / s, pb / s) if s else (pa, pb)


def normalize_three_way(a: float, b: float, c: float) -> Tuple[float, float, float]:
    pa, pb, pc = implied_prob(a), implied_prob(b), implied_prob(c)
    s = pa + pb + pc
    return (pa / s, pb / s, pc / s) if s else (pa, pb, pc)


def league_penalty(match: Dict[str, Any]) -> int:
    comp = str(match.get("competition", "")).lower()
    risky = ["korea", "japan", "greece", "argentina", "brazil", "chile", "colombia", "australia", "china", "friendly", "cup"]
    major = ["epl", "premier", "la liga", "serie a", "bundesliga", "ligue 1", "champions", "europa"]
    if any(k in comp for k in major):
        return 0
    if any(k in comp for k in risky):
        return 7
    return 4


def build_candidates_for_match(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not match.get("real_odds"):
        return []

    home, away = match["home"], match["away"]
    cands = []

    if match.get("h2h_home") and match.get("h2h_draw") and match.get("h2h_away"):
        ph, pd, pa = normalize_three_way(float(match["h2h_home"]), float(match["h2h_draw"]), float(match["h2h_away"]))
        cands.extend([
            {"type": "h2h", "pari": f"Victoire {home}", "odds": float(match["h2h_home"]), "market_prob": ph},
            {"type": "draw", "pari": "Match nul", "odds": float(match["h2h_draw"]), "market_prob": pd},
            {"type": "h2h", "pari": f"Victoire {away}", "odds": float(match["h2h_away"]), "market_prob": pa},
        ])

    if match.get("over25") and match.get("under25"):
        po, pu = normalize_two_way(float(match["over25"]), float(match["under25"]))
        cands.extend([
            {"type": "total", "pari": "Plus de 2.5 buts", "odds": float(match["over25"]), "market_prob": po},
            {"type": "total", "pari": "Moins de 2.5 buts", "odds": float(match["under25"]), "market_prob": pu},
        ])

    if match.get("btts_yes") and match.get("btts_no"):
        py, pn = normalize_two_way(float(match["btts_yes"]), float(match["btts_no"]))
        cands.extend([
            {"type": "btts", "pari": "Les deux équipes marquent — Oui", "odds": float(match["btts_yes"]), "market_prob": py},
            {"type": "btts", "pari": "Les deux équipes marquent — Non", "odds": float(match["btts_no"]), "market_prob": pn},
        ])

    clean = []
    for c in cands:
        odds = float(c["odds"])
        if 1.35 <= odds <= 4.80:
            c["implied_prob_pct"] = round(100 / odds, 1)
            c["match_id"] = match["id"]
            clean.append(c)
    return clean


def candidate_prefilter_score(match: Dict[str, Any], candidate: Dict[str, Any]) -> float:
    odds = float(candidate["odds"])
    p_market = float(candidate["market_prob"])
    typ = candidate["type"]

    score = 0.0
    score += 100 * p_market
    score += max(0.0, odds - 1.55) * 9

    if typ in ("total", "btts"):
        score += 8
    elif typ == "draw":
        score -= 4
    elif typ == "h2h":
        score -= 3

    if 1.60 <= odds <= 2.35:
        score += 7
    elif odds > 3.20:
        score -= 5
    elif odds < 1.50:
        score -= 8

    score -= league_penalty(match) * 0.8
    return round(score, 2)


def build_market_pool(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pool = []
    for match in matches:
        for cand in build_candidates_for_match(match):
            pool.append({
                "match": match,
                "candidate": cand,
                "prefilter_score": candidate_prefilter_score(match, cand),
            })
    pool.sort(key=lambda x: x["prefilter_score"], reverse=True)
    return pool


def danger_score(match: Dict[str, Any], candidate: Dict[str, Any], ai_risk: int) -> int:
    odds = float(candidate["odds"])
    typ = candidate["type"]
    danger = 24

    if typ == "draw":
        danger += 12
    elif typ == "h2h":
        danger += 7
    elif typ in ("total", "btts"):
        danger += 2

    if odds >= 2.80:
        danger += 12
    elif odds >= 2.25:
        danger += 7
    elif odds < 1.50:
        danger += 6

    danger += league_penalty(match)
    danger += int((ai_risk - 50) * 0.25)
    return int(clamp(danger, 10, 88))


def calculate_scores(match: Dict[str, Any], candidate: Dict[str, Any], llm_prob: float, ai_risk: int, prefilter_score: float) -> Dict[str, Any]:
    odds = float(candidate["odds"])
    p_market = float(candidate["market_prob"])
    typ = candidate["type"]

    llm_prob = clamp(llm_prob, 0.38, 0.74)
    w = CFG["llm_weight"]
    p_fused = (1 - w) * p_market + w * llm_prob

    if typ in ("total", "btts"):
        p_fused += 0.025
    elif typ == "draw":
        p_fused -= 0.015
    elif typ == "h2h":
        p_fused -= 0.005

    p_fused = clamp(p_fused, 0.34, 0.77)
    edge = p_fused - p_market
    danger = danger_score(match, candidate, ai_risk)

    confidence = int(round(48 + p_fused * 42 + edge * 45 - danger * 0.10))
    confidence = int(clamp(confidence, 52, CFG["max_conf"]))

    if odds >= 2.70:
        confidence = min(confidence, 73)
    if league_penalty(match) >= 7:
        confidence = min(confidence, 76)

    # V4.1: score exploitable, moins punitif que V4.
    ev = (p_fused * odds) - 1.0
    value_score = (
        ev * 100
        + edge * 70
        + (6 if typ in ("total", "btts") else 0)
        + max(0, odds - 1.65) * 3
        + prefilter_score * 0.08
        - danger * CFG["danger_mult"]
    )

    stake_pct = 1
    if confidence >= 74 and value_score >= 0 and danger < 54:
        stake_pct = 3
    elif confidence >= 64 and value_score >= CFG["min_value"] and danger < 66:
        stake_pct = 2

    return {
        "p_market": round(p_market * 100, 1),
        "p_fused": round(p_fused * 100, 1),
        "edge_pct": round(edge * 100, 1),
        "confidence": confidence,
        "danger": danger,
        "value_score": round(value_score, 2),
        "stake_pct": stake_pct,
        "ev_pct": round(ev * 100, 1),
    }


async def agent_report(agent_id: str, match: Dict[str, Any], candidate: Dict[str, Any], alternatives: List[Dict[str, Any]]) -> str:
    return await groq_call(
        SYSTEM_PROMPTS[agent_id],
        (
            f"Match: {match['home']} vs {match['away']}\n"
            f"Compétition: {match['competition']} | Heure: {match['heure']}\n"
            f"Bookmaker: {match.get('bookmaker')}\n"
            f"Pari étudié: {json.dumps(candidate, ensure_ascii=False)}\n"
            f"Alternatives du même match: {json.dumps(alternatives, ensure_ascii=False)}\n"
            "Analyse courte, prudente, sans inventer d'information externe."
        ),
        max_tokens=220,
        temperature=0.25,
    )


async def judge_candidate(match: Dict[str, Any], candidate: Dict[str, Any], alternatives: List[Dict[str, Any]], reports: Dict[str, str], prefilter_score: float) -> Dict[str, Any]:
    system = (
        "Tu es juge final value betting football. Tu évalues UN pari précis. "
        "Tu dois éviter le biais victoire simple. Tu ne dois pas inventer d'information. "
        "Tu réponds uniquement en JSON."
    )
    user = f"""
Match: {match['home']} vs {match['away']}
Compétition: {match['competition']}
Heure: {match['heure']}
Bookmaker: {match.get('bookmaker')}

Pari étudié:
{json.dumps(candidate, ensure_ascii=False, indent=2)}

Alternatives du même match:
{json.dumps(alternatives, ensure_ascii=False, indent=2)}

Rapports:
{json.dumps(reports, ensure_ascii=False, indent=2)}

Réponds seulement:
{{
  "llm_prob": 0.38 à 0.74,
  "ai_risk": 10 à 90,
  "resume": "2 ou 3 phrases courtes: pourquoi ce pari peut être jouable",
  "risque": "risque principal"
}}

Règles:
- Si le pari est juste une victoire simple sans autre avantage, llm_prob <= 0.56.
- Si le marché buts/BTTS semble meilleur que H2H, dis-le dans le résumé.
- Ligue secondaire = prudence.
- Ne dépasse 0.68 que si le marché est vraiment cohérent.
"""
    raw = await groq_call(system, user, max_tokens=430, temperature=0.18, json_mode=True)
    try:
        data = parse_json_object(raw)
    except Exception:
        log.warning("Judge JSON invalide: %s", raw[:300])
        data = {"llm_prob": 0.54, "ai_risk": 58, "resume": "Analyse IA incomplète, score prudent.", "risque": "Parsing incomplet."}

    scores = calculate_scores(
        match,
        candidate,
        float(data.get("llm_prob", 0.54)),
        int(float(data.get("ai_risk", 58))),
        prefilter_score,
    )

    return {
        "pari": candidate["pari"],
        "market_type": candidate["type"],
        "odds": round(float(candidate["odds"]), 2),
        "resume": str(data.get("resume", ""))[:800],
        "risque": str(data.get("risque", ""))[:300],
        **scores,
    }


async def analyze_market_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    match = item["match"]
    candidate = item["candidate"]
    all_cands = build_candidates_for_match(match)
    alternatives = [c for c in all_cands if c["pari"] != candidate["pari"]]

    reports = {}
    for agent_id in ["market", "risk", "tempo"]:
        reports[agent_id] = await agent_report(agent_id, match, candidate, alternatives)

    verdict = await judge_candidate(match, candidate, alternatives, reports, item["prefilter_score"])
    return {"match": match, "candidate": candidate, "verdict": verdict, "reports": reports, "prefilter_score": item["prefilter_score"]}


def diversify_picks(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected = []
    seen_matches = set()
    h2h_count = 0

    # 1) pick best totals/btts first when viable
    non_h2h = [p for p in candidates if p["market_type"] in ("total", "btts")]
    h2h = [p for p in candidates if p["market_type"] in ("h2h", "draw")]

    ordered = non_h2h + h2h

    for pick in ordered:
        if pick["match_id"] in seen_matches:
            continue
        if pick["market_type"] == "h2h" and h2h_count >= MAX_H2H_TOP:
            continue
        if pick["confidence"] < CFG["min_confidence"] and len(selected) >= 3:
            continue
        if pick["value_score"] < CFG["min_value"] and len(selected) >= 3:
            continue

        selected.append(pick)
        seen_matches.add(pick["match_id"])
        if pick["market_type"] == "h2h":
            h2h_count += 1
        if len(selected) >= TOP_PICKS:
            break

    # 2) ensure at least 3 picks if possible in balanced/aggressive
    if len(selected) < min(3, TOP_PICKS) and ORACLE_MODE in ("balanced", "aggressive"):
        for pick in candidates:
            if pick["match_id"] in seen_matches:
                continue
            if pick["confidence"] >= 54 and pick["value_score"] >= (CFG["min_value"] - 8):
                selected.append(pick)
                seen_matches.add(pick["match_id"])
            if len(selected) >= min(3, TOP_PICKS):
                break

    return selected[:TOP_PICKS]


def bar(pct: int, size: int = 10) -> str:
    filled = int(round(size * pct / 100))
    return "█" * filled + "░" * (size - filled)


def pick_text(rank: int, pick: Dict[str, Any]) -> str:
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    medal = medals[rank - 1] if rank <= len(medals) else f"{rank}."
    stake = round(BANKROLL * pick["stake_pct"] / 100, 2)
    ret = round(stake * pick["odds"], 2)
    profit = round(ret - stake, 2)
    confidence = int(pick["confidence"])
    danger = int(pick["danger"])

    if confidence >= 76:
        label = "🔥 FORT"
    elif confidence >= 66:
        label = "✅ BON"
    elif confidence >= 58:
        label = "👍 JOUABLE"
    else:
        label = "⚠️ SPÉCULATIF"

    return "\n".join([
        f"{medal} <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>",
        f"🏆 {esc(pick['competition'])} · ⏰ {esc(pick['heure'])}",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>PARI : {esc(pick['pari'])}</b>",
        f"🧩 Marché : <b>{esc(pick['market_type'])}</b>",
        f"📊 Confiance : <code>{bar(confidence)}</code> <b>{confidence}%</b> {label}",
        f"⚠️ Danger : <code>{bar(danger)}</code> <b>{danger}%</b>",
        f"💎 Value score : <b>{pick['value_score']}</b> · EV {pick['ev_pct']}%",
        f"📈 Marché : <b>{pick['p_market']}%</b> · Fusion IA : <b>{pick['p_fused']}%</b> · Edge {pick['edge_pct']}%",
        f"⚡ Cote : <b>{pick['odds']}</b>",
        f"💰 Mise : <b>{stake}€</b> ({pick['stake_pct']}% de {BANKROLL}€)",
        f"🎁 Si gagne : <b>{ret}€</b> · profit <b>+{profit}€</b>",
        f"📡 Source: {esc(pick['source'])} · bookmaker: {esc(pick['bookmaker'])}",
        "",
        f"💡 <b>Pourquoi :</b>\n{esc(pick['resume'])}",
        "",
        f"⚠️ <b>Risque :</b> {esc(pick['risque'])}",
    ])


async def run_scan(context: ContextTypes.DEFAULT_TYPE, force: bool = False) -> None:
    db = db_load()
    t = target_day()

    if not force and db.get("scans", {}).get(t["key"], {}).get("picks"):
        await context.bot.send_message(CHAT_ID, f"💾 Scan déjà fait pour {esc(t['label'])}. Utilise /scan force.", parse_mode=ParseMode.HTML)
        return

    msg = await context.bot.send_message(
        CHAT_ID,
        f"⚽ <b>ORACLE V4.1 — {esc(t['mode'])}</b>\n📅 {esc(t['label'])}\nMode: <b>{esc(ORACLE_MODE)}</b>\n\n🔍 Recherche large de matchs + marchés...",
        parse_mode=ParseMode.HTML,
    )

    data = await fetch_matches(t["iso_date"], t["label"])
    matches = data["pickable"]

    if not matches:
        info_only = data["info_only"]
        if info_only:
            examples = "\n".join(f"• {esc(m['heure'])} — {esc(m['home'])} vs {esc(m['away'])} ({esc(m['competition'])})" for m in info_only[:8])
            await msg.edit_text(
                f"⚠️ <b>Fixtures trouvées mais pas de vraies cotes.</b>\n\n{examples}\n\nLa V4.1 refuse les cotes inventées.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await msg.edit_text(f"❌ Aucun match trouvé pour {esc(t['label'])}. Vérifie clés API/quota.", parse_mode=ParseMode.HTML)
        return

    pool = build_market_pool(matches)
    if not pool:
        await msg.edit_text("❌ Matchs trouvés, mais aucun marché exploitable.", parse_mode=ParseMode.HTML)
        return

    pool = pool[:MAX_ANALYZED]
    await msg.edit_text(
        f"✅ <b>{len(matches)} matchs avec cotes</b>\n"
        f"🧪 <b>{len(pool)} meilleurs marchés préfiltrés</b> sur {sum(len(build_candidates_for_match(m)) for m in matches)} marchés\n"
        f"Sources: {esc(', '.join(data['sources']))}\n"
        "🔬 Analyse IA des marchés en cours...",
        parse_mode=ParseMode.HTML,
    )

    analyzed = []
    for idx, item in enumerate(pool):
        m = item["match"]
        c = item["candidate"]
        pmsg = await context.bot.send_message(
            CHAT_ID,
            f"🔬 <b>Marché {idx + 1}/{len(pool)}</b>\n⚽ {esc(m['home'])} vs {esc(m['away'])}\n🎯 {esc(c['pari'])} @ {c['odds']}\n<code>{bar(15)} 15%</code>",
            parse_mode=ParseMode.HTML,
        )

        try:
            res = await analyze_market_item(item)
            if res:
                v = res["verdict"]
                analyzed.append(res)
                await pmsg.edit_text(
                    f"✅ <b>{esc(m['home'])} vs {esc(m['away'])}</b>\n<code>{bar(100)} 100%</code>\n🎯 {esc(v['pari'])}\n📊 {v['confidence']}% · danger {v['danger']}% · value {v['value_score']}",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as exc:
            log.exception("Analyse marché échouée")
            await pmsg.edit_text(f"❌ Erreur analyse: {esc(exc)}", parse_mode=ParseMode.HTML)

        await asyncio.sleep(0.35)

    raw_picks = []
    for res in analyzed:
        m, v = res["match"], res["verdict"]
        raw_picks.append({
            "match_id": m["id"],
            "home": m["home"],
            "away": m["away"],
            "competition": m["competition"],
            "heure": m["heure"],
            "source": m["source"],
            "bookmaker": m["bookmaker"],
            "prefilter_score": res["prefilter_score"],
            "result": None,
            **v,
        })

    raw_picks.sort(key=lambda p: (p["value_score"] - 0.25 * p["danger"], p["confidence"], p["prefilter_score"]), reverse=True)
    picks = diversify_picks(raw_picks)

    if not picks:
        await context.bot.send_message(CHAT_ID, "⚠️ Analyse terminée, mais aucun pick ne passe les filtres. Essaie ORACLE_MODE=aggressive ou augmente MAX_MATCHES.")
        return

    db.setdefault("scans", {})[t["key"]] = {
        "date_key": t["key"],
        "date_label": t["label"],
        "scanned_at": t["scanned_at"],
        "mode": ORACLE_MODE,
        "picks": picks,
    }
    db_save(db)

    await context.bot.send_message(
        CHAT_ID,
        f"🏆 <b>TOP {len(picks)} — {esc(t['label'])}</b>\n"
        f"Mode: <b>{esc(ORACLE_MODE)}</b>\n"
        "Tri: marché + edge IA + value - danger. Max victoires simples limité.",
        parse_mode=ParseMode.HTML,
    )

    for idx, pick in enumerate(picks):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"res:{t['key']}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{t['key']}:{idx}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{t['key']}:{idx}:cancel"),
        ]])
        await context.bot.send_message(CHAT_ID, pick_text(idx + 1, pick), parse_mode=ParseMode.HTML, reply_markup=keyboard)

    await context.bot.send_message(CHAT_ID, "✅ Scan terminé. /resultats pour saisir WIN/LOSS.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⚽ Scanner maintenant", callback_data="launch_scan")]])
    await update.message.reply_text(
        "⚽ <b>ORACLE FOOTBALL V4.1</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Scan large\n"
        "✅ Préfiltre marchés sans IA\n"
        "✅ Analyse marchés, pas seulement matchs\n"
        "✅ Score balanced/safe/aggressive\n"
        "✅ Max H2H dans le Top\n\n"
        "/scan\n/scan force\n/resultats\n/stats",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return
    await run_scan(context, force=bool(context.args and context.args[0].lower() == "force"))


async def cmd_resultats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return

    db = db_load()
    pending = []
    for date_key, scan in db.get("scans", {}).items():
        for idx, pick in enumerate(scan.get("picks", [])):
            if pick.get("result") is None:
                pending.append((date_key, scan.get("date_label", date_key), idx, pick))

    if not pending:
        await update.message.reply_text("✅ Aucun résultat en attente.")
        return

    await update.message.reply_text(f"⏳ {len(pending)} picks en attente.")
    for date_key, label, idx, pick in pending[:15]:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ WIN", callback_data=f"res:{date_key}:{idx}:win"),
            InlineKeyboardButton("❌ LOSS", callback_data=f"res:{date_key}:{idx}:loss"),
            InlineKeyboardButton("🚫 ANNULER", callback_data=f"res:{date_key}:{idx}:cancel"),
        ]])
        await update.message.reply_text(
            f"📅 {esc(label)}\n⚽ <b>{esc(pick['home'])} vs {esc(pick['away'])}</b>\n🎯 {esc(pick['pari'])}\n📊 {pick['confidence']}% · value {pick['value_score']}",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != CHAT_ID:
        return

    db = db_load()
    picks = [p for scan in db.get("scans", {}).values() for p in scan.get("picks", [])]
    decided = [p for p in picks if p.get("result") in ("win", "loss")]
    wins = [p for p in decided if p.get("result") == "win"]
    winrate = round(len(wins) / len(decided) * 100, 1) if decided else 0.0

    by_market = {}
    for p in decided:
        market = p.get("market_type", "?")
        by_market.setdefault(market, {"w": 0, "n": 0})
        by_market[market]["n"] += 1
        if p.get("result") == "win":
            by_market[market]["w"] += 1

    lines = []
    for market, values in by_market.items():
        wr = round(values["w"] / values["n"] * 100, 1)
        lines.append(f"• {market}: {values['w']}/{values['n']} = {wr}%")

    await update.message.reply_text(
        "📊 <b>STATS ORACLE</b>\n"
        f"Mode: <b>{esc(ORACLE_MODE)}</b>\n"
        f"Paris décidés: <b>{len(decided)}</b>\n"
        f"Wins: <b>{len(wins)}</b>\n"
        f"Winrate: <b>{winrate}%</b>\n\n"
        + ("\n".join(lines) if lines else "Pas assez d'historique."),
        parse_mode=ParseMode.HTML,
    )


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.message.chat_id != CHAT_ID:
        return

    if query.data == "launch_scan":
        await run_scan(context, force=False)
        return

    if not query.data.startswith("res:"):
        return

    _, date_key, idx_s, result = query.data.split(":")
    idx = int(idx_s)

    db = db_load()
    scan = db.get("scans", {}).get(date_key)
    if not scan or idx >= len(scan.get("picks", [])):
        await query.edit_message_text("⚠️ Pick introuvable.")
        return

    pick = scan["picks"][idx]
    pick["result"] = "cancelled" if result == "cancel" else result
    db_save(db)

    suffix = "\n\n🚫 Pick annulé." if result == "cancel" else f"\n\n{'✅' if result == 'win' else '❌'} {result.upper()} enregistré."
    try:
        await query.edit_message_text(query.message.text_html + suffix, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.reply_text(suffix)


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_scan(context, force=False)


def main() -> None:
    validate_env()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("scan", cmd_scan))
    app.add_handler(CommandHandler("resultats", cmd_resultats))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(callback))

    app.job_queue.run_daily(
        daily_job,
        time=time(hour=SCAN_HOUR, minute=0, tzinfo=PARIS_TZ),
        days=(0, 1, 2, 3, 4, 5, 6),
        chat_id=CHAT_ID,
    )

    log.info(
        "Oracle Bot V4.1 démarré — mode=%s scan=%sh Paris max_matches=%s max_analyzed=%s",
        ORACLE_MODE,
        SCAN_HOUR,
        MAX_MATCHES,
        MAX_ANALYZED,
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
