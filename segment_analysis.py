from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def odds_bucket(odds: float) -> str:
    if odds < 1.65:
        return "low"
    if odds < 2.30:
        return "mid"
    if odds < 3.20:
        return "high"
    return "very_high"


def league_bucket(comp: str) -> str:
    c = str(comp).lower()
    if any(x in c for x in ["la liga", "epl", "premier", "serie a", "bundesliga", "ligue 1", "champions", "europa"]):
        return "major"
    if any(x in c for x in ["argentina", "sweden", "poland", "korea", "japan", "greece", "cup", "friendly", "mls"]):
        return "volatile"
    return "other"


def _unit_profit(pick: Dict[str, Any]) -> float:
    odds = _num(pick.get("odds"), 1.0)
    return odds - 1.0 if pick.get("result") == "win" else -1.0


def _record_key(pick: Dict[str, Any]) -> Tuple[Any, ...]:
    odds = round(_num(pick.get("odds"), 0.0), 4)
    return (pick.get("date_key"), pick.get("home"), pick.get("away"), pick.get("market_type"), pick.get("pari"), odds)


def settled_rows(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for scan in db.get("scans", {}).values():
        for pick in (scan.get("picks", []) or []) + (scan.get("candidates", []) or []):
            if pick.get("result") not in ("win", "loss"):
                continue
            key = _record_key(pick)
            if key in seen:
                continue
            seen.add(key)
            rows.append(pick)
    return sorted(rows, key=lambda p: str(p.get("date_key", "")))


def h2h_side(pick: Dict[str, Any]) -> Optional[str]:
    if pick.get("market_type") != "h2h":
        return None
    family = str(pick.get("import_family", "")).lower()
    if family in ("home", "away"):
        return family
    pari = str(pick.get("pari", "")).lower()
    home = str(pick.get("home", "")).lower()
    away = str(pick.get("away", "")).lower()
    if home and home in pari:
        return "home"
    if away and away in pari:
        return "away"
    return None


def price_profile(odds: float) -> str:
    if odds < 2.0:
        return "favorite"
    if odds >= 3.0:
        return "outsider"
    return "middle"


def elo_profile(pick: Dict[str, Any]) -> Optional[str]:
    if pick.get("elo_diff") in (None, ""):
        return None
    diff = _num(pick.get("elo_diff"))
    if diff >= 75:
        return "elo_home_strong"
    if diff <= -75:
        return "elo_away_strong"
    return "elo_balanced"


def era_profile(pick: Dict[str, Any]) -> Optional[str]:
    date_key = str(pick.get("date_key") or "")
    if len(date_key) < 4:
        return None
    try:
        year = int(date_key[:4])
    except ValueError:
        return None
    return "recent_2023_plus" if year >= 2023 else "ancien_avant_2023"


def candidate_segment_keys(pick: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    market = str(pick.get("market_type") or "?")
    odds = _num(pick.get("odds"), 2.0)
    bucket = odds_bucket(odds)
    league = league_bucket(pick.get("competition", ""))
    keys = [
        (f"market_odds_league:{market}|{bucket}|{league}", f"{market} + {bucket} + {league}", "market_odds_league"),
        (f"market_odds:{market}|{bucket}", f"{market} + {bucket}", "market_odds"),
        (f"market_league:{market}|{league}", f"{market} + {league}", "market_league"),
        (f"market:{market}", market, "market"),
        (f"odds:{bucket}", bucket, "odds"),
        (f"price_profile:{price_profile(odds)}", price_profile(odds), "price_profile"),
    ]
    side = h2h_side(pick)
    if side:
        label = "h2h domicile" if side == "home" else "h2h extérieur"
        keys.insert(3, (f"h2h_side:{side}", label, "h2h_side"))
    elo = elo_profile(pick)
    if elo:
        keys.append((f"elo_profile:{elo}", elo, "elo_profile"))
    era = era_profile(pick)
    if era:
        keys.append((f"era:{era}", era, "era"))
    return keys


def _classify(n: int, roi: float) -> str:
    if n < 100:
        return "volume_insuffisant"
    if n < 300:
        return "signal_faible"
    if roi < -12:
        return "a_bloquer"
    if roi < -8:
        return "negatif_fort"
    if roi > 5:
        return "positif_fort"
    if roi > 2:
        return "positif"
    return "exploitable_neutre"


def _max_drawdown(sequence: List[Tuple[str, float]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for _, profit in sorted(sequence, key=lambda item: item[0]):
        cumulative += profit
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return round(drawdown, 2)


def _finalize(key: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    n = raw["n"]
    wins = raw["wins"]
    profit = round(raw["profit"], 2)
    roi = round(profit / n * 100, 1) if n else 0.0
    winrate = round(wins / n * 100, 1) if n else 0.0
    avg_odds = round(raw["odds_sum"] / n, 2) if n else 0.0
    max_dd = _max_drawdown(raw["sequence"])
    status = _classify(n, roi)
    volume_factor = min(1.0, n / 300)
    drawdown_penalty = min(8.0, (max_dd / max(n, 1)) * 8)
    reliability = round((roi * volume_factor) - drawdown_penalty, 2)
    return {
        "key": key,
        "label": raw["label"],
        "kind": raw["kind"],
        "n": n,
        "wins": wins,
        "winrate": winrate,
        "wr": winrate,
        "profit": profit,
        "roi": roi,
        "average_odds": avg_odds,
        "max_drawdown": max_dd,
        "reliability_score": reliability,
        "status": status,
        "decision_eligible": n >= 100,
        "positive_reliable": n >= 300 and roi > 2,
        "strong_positive": n >= 300 and roi > 5,
        "negative_strong": n >= 300 and roi < -8,
        "block_top": n >= 300 and roi < -12,
    }


def build_segment_report(db: Dict[str, Any]) -> Dict[str, Any]:
    rows = settled_rows(db)
    raw_segments: Dict[str, Dict[str, Any]] = {}
    for pick in rows:
        profit = _unit_profit(pick)
        odds = _num(pick.get("odds"), 0.0)
        date_key = str(pick.get("date_key") or "")
        for key, label, kind in candidate_segment_keys(pick):
            raw = raw_segments.setdefault(key, {
                "label": label,
                "kind": kind,
                "n": 0,
                "wins": 0,
                "profit": 0.0,
                "odds_sum": 0.0,
                "sequence": [],
            })
            raw["n"] += 1
            raw["wins"] += 1 if pick.get("result") == "win" else 0
            raw["profit"] += profit
            raw["odds_sum"] += odds
            raw["sequence"].append((date_key, profit))

    segments = {key: _finalize(key, raw) for key, raw in raw_segments.items()}
    decision_segments = [seg for seg in segments.values() if seg["decision_eligible"]]
    best = sorted(decision_segments, key=lambda seg: (seg["roi"], seg["n"], seg["reliability_score"]), reverse=True)
    worst = sorted([seg for seg in segments.values() if seg["n"] >= 300], key=lambda seg: (seg["roi"], -seg["n"]))
    positive = [seg for seg in best if seg["positive_reliable"]]
    blocked = [seg for seg in worst if seg["block_top"]]
    return {
        "samples": len(rows),
        "segments_count": len(segments),
        "segments": segments,
        "best_segments": best[:10],
        "positive_segments": positive[:10],
        "worst_segments": worst[:10],
        "blocked_segments": blocked[:10],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
