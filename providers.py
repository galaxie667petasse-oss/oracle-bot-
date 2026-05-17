import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import aiohttp

from config import settings


async def fetch_json(session, url: str, params=None, headers=None) -> Tuple[int, Any, str]:
    try:
        async with session.get(url, params=params, headers=headers, timeout=25) as r:
            txt = await r.text()
            try:
                return r.status, json.loads(txt), txt[:400]
            except Exception:
                return r.status, None, txt[:400]
    except Exception as exc:
        return 0, None, str(exc)


def _price(outcomes, *names) -> Optional[float]:
    wanted = {str(n).lower() for n in names}
    for o in outcomes or []:
        if str(o.get("name", "")).lower() in wanted:
            try:
                return float(o.get("price"))
            except Exception:
                return None
    return None


async def active_sports(session) -> List[str]:
    status, data, _ = await fetch_json(session, "https://api.the-odds-api.com/v4/sports", {"apiKey": settings.odds_key})
    if status != 200 or not isinstance(data, list):
        return []
    return [
        s["key"] for s in data
        if str(s.get("key", "")).startswith("soccer")
        and s.get("active", True)
        and "winner" not in str(s.get("key", "")).lower()
    ]


def extract_markets(event, home: str, away: str) -> Dict[str, Any]:
    base = {"h2h_home": None, "h2h_draw": None, "h2h_away": None, "over25": None, "under25": None, "btts_yes": None, "btts_no": None, "bookmaker": "", "real_odds": False}
    books = event.get("bookmakers", []) or []
    books.sort(key=lambda b: 0 if b.get("key") == "pinnacle" else 1)
    for b in books:
        d = dict(base)
        for m in b.get("markets", []) or []:
            key = m.get("key")
            outs = m.get("outcomes", []) or []
            if key == "h2h":
                d["h2h_home"] = _price(outs, home, "Home")
                d["h2h_draw"] = _price(outs, "Draw", "Nul")
                d["h2h_away"] = _price(outs, away, "Away")
            elif key == "totals":
                for o in outs:
                    try:
                        point, price = float(o.get("point")), float(o.get("price"))
                    except Exception:
                        continue
                    nm = str(o.get("name", "")).lower()
                    if abs(point - 2.5) < 0.01 and nm == "over":
                        d["over25"] = price
                    if abs(point - 2.5) < 0.01 and nm == "under":
                        d["under25"] = price
            elif key == "btts":
                d["btts_yes"] = _price(outs, "Yes", "Oui")
                d["btts_no"] = _price(outs, "No", "Non")
        if any(d.get(x) for x in ["h2h_home", "h2h_draw", "h2h_away", "over25", "under25", "btts_yes", "btts_no"]):
            d["bookmaker"] = b.get("title") or b.get("key") or "bookmaker"
            d["real_odds"] = True
            return d
    return base


async def odds_matches(day_key: str) -> List[Dict[str, Any]]:
    rows, seen = [], set()
    start, end = f"{day_key}T00:00:00Z", f"{day_key}T23:59:59Z"
    async with aiohttp.ClientSession() as session:
        for sport in (await active_sports(session))[:60]:
            url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
            params = {"apiKey": settings.odds_key, "regions": settings.odds_regions, "markets": settings.odds_markets, "oddsFormat": "decimal", "dateFormat": "iso", "commenceTimeFrom": start, "commenceTimeTo": end}
            status, data, _ = await fetch_json(session, url, params)
            if status == 422:
                params["markets"] = "h2h"
                status, data, _ = await fetch_json(session, url, params)
            if status != 200 or not isinstance(data, list):
                continue
            for ev in data:
                home, away = ev.get("home_team") or "?", ev.get("away_team") or "?"
                eid = ev.get("id") or f"{home}-{away}-{ev.get('commence_time')}"
                if eid in seen:
                    continue
                seen.add(eid)
                try:
                    dt = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(settings.tz)
                except Exception:
                    continue
                if dt.strftime("%Y-%m-%d") != day_key:
                    continue
                markets = extract_markets(ev, home, away)
                if not markets["real_odds"]:
                    continue
                rows.append({"id": eid, "date_key": day_key, "home": home, "away": away, "competition": sport.replace("soccer_", "").replace("_", " ").title(), "heure": dt.strftime("%H:%M"), "source": "the_odds_api", **markets})
    return sorted(rows, key=lambda r: (r["heure"], r["competition"]))[:settings.max_matches]


async def result_fixtures(day_key: str) -> List[Dict[str, Any]]:
    out = []
    if settings.football_key:
        async with aiohttp.ClientSession(headers={"x-apisports-key": settings.football_key}) as session:
            status, data, _ = await fetch_json(session, "https://v3.football.api-sports.io/fixtures", {"date": day_key})
        if status == 200 and isinstance(data, dict):
            for it in data.get("response", []):
                fx, tm, g = it.get("fixture", {}), it.get("teams", {}), it.get("goals", {})
                out.append({"home": tm.get("home", {}).get("name", "?"), "away": tm.get("away", {}).get("name", "?"), "status": fx.get("status", {}).get("short", ""), "hg": g.get("home"), "ag": g.get("away"), "src": "api_football"})
    if not out and settings.football_data_key:
        async with aiohttp.ClientSession(headers={"X-Auth-Token": settings.football_data_key}) as session:
            for comp in settings.football_data_comps:
                status, data, _ = await fetch_json(session, f"https://api.football-data.org/v4/competitions/{comp}/matches", {"dateFrom": day_key, "dateTo": day_key})
                if status == 200 and isinstance(data, dict):
                    for it in data.get("matches", []):
                        score = it.get("score", {}).get("fullTime", {})
                        out.append({"home": it.get("homeTeam", {}).get("name", "?"), "away": it.get("awayTeam", {}).get("name", "?"), "status": it.get("status", ""), "hg": score.get("home"), "ag": score.get("away"), "src": "football_data"})
    return out
