from datetime import datetime, timezone
from typing import Any, Dict, List


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


def _record_key(p: Dict[str, Any]) -> tuple:
    odds = round(_num(p.get("odds"), 0.0), 4)
    return (p.get("date_key"), p.get("home"), p.get("away"), p.get("market_type"), p.get("pari"), odds)


def settled_rows(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    seen = set()
    for scan in db.get("scans", {}).values():
        for p in (scan.get("picks", []) or []) + (scan.get("candidates", []) or []):
            if p.get("result") not in ("win", "loss"):
                continue
            key = _record_key(p)
            if key in seen:
                continue
            seen.add(key)
            rows.append(p)
    return rows


def _group(rows: List[Dict[str, Any]], key_fn):
    out: Dict[str, Dict[str, float]] = {}
    for p in rows:
        key = str(key_fn(p))
        out.setdefault(key, {"n": 0, "w": 0, "profit": 0.0})
        out[key]["n"] += 1
        out[key]["w"] += 1 if p.get("result") == "win" else 0
        out[key]["profit"] += _unit_profit(p)
    for stat in out.values():
        n = stat["n"]
        stat["wr"] = round(stat["w"] / n * 100, 1) if n else 0
        stat["roi"] = round(stat["profit"] / n * 100, 1) if n else 0
        stat["profit"] = round(stat["profit"], 2)
    return out


def _maturity(samples: int) -> str:
    if samples < 30:
        return "mémoire jeune"
    if samples <= 100:
        return "calibration en cours"
    return "calibration active"


def _base_thresholds(samples: int) -> Dict[str, Any]:
    if samples < 30:
        return {
            "min_ev_for_top": 2.0,
            "min_council_score_for_top": 7.2,
            "max_danger_for_top": 50,
            "max_h2h_odds_for_top": 2.50,
            "max_draw_odds_for_top": 0,
            "max_observation_negative_score": -3.0,
        }
    if samples <= 100:
        return {
            "min_ev_for_top": 1.5,
            "min_council_score_for_top": 6.8,
            "max_danger_for_top": 54,
            "max_h2h_odds_for_top": 2.80,
            "max_draw_odds_for_top": 3.20,
            "max_observation_negative_score": -4.0,
        }
    return {
        "min_ev_for_top": 1.2,
        "min_council_score_for_top": 6.5,
        "max_danger_for_top": 56,
        "max_h2h_odds_for_top": 3.20,
        "max_draw_odds_for_top": 3.20,
        "max_observation_negative_score": -5.0,
    }


def _risk_entry(stat: Dict[str, Any], strong_roi: float, block_roi: float, strong_n: int, block_n: int) -> Dict[str, Any]:
    n = int(stat.get("n", 0) or 0)
    roi = _num(stat.get("roi"))
    if n >= block_n and roi < block_roi:
        return {"n": n, "roi": roi, "penalty": "blocage_top", "block_top": True}
    if n >= strong_n and roi < strong_roi:
        return {"n": n, "roi": roi, "penalty": "forte", "block_top": False}
    return {}


def build_calibration(db: Dict[str, Any], learning: Dict[str, Any] = None) -> Dict[str, Any]:
    rows = settled_rows(db)
    learning = learning or {}
    samples = int(learning.get("samples", len(rows)) or 0)
    by_market = learning.get("by_market") or _group(rows, lambda p: p.get("market_type", "?"))
    by_odds = learning.get("by_odds") or _group(rows, lambda p: odds_bucket(_num(p.get("odds"), 2.0)))
    by_league = learning.get("by_league") or _group(rows, lambda p: league_bucket(p.get("competition", "")))

    calibration = _base_thresholds(samples)
    calibration.update({
        "maturity_level": _maturity(samples),
        "samples": samples,
        "banned_or_penalized_markets": {},
        "banned_or_penalized_odds_buckets": {},
        "confidence_cap_by_bucket": {"low": 72, "mid": 68, "high": 60, "very_high": 54},
        "positive_buckets": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    for market, stat in by_market.items():
        entry = _risk_entry(stat, strong_roi=-8, block_roi=-12, strong_n=100, block_n=300)
        if entry:
            calibration["banned_or_penalized_markets"][market] = entry
            calibration["min_council_score_for_top"] = max(calibration["min_council_score_for_top"], 7.2)
            calibration["min_ev_for_top"] = max(calibration["min_ev_for_top"], 1.8)
            if market == "h2h":
                calibration["max_h2h_odds_for_top"] = min(calibration["max_h2h_odds_for_top"], 2.60)
            if market == "draw":
                calibration["max_draw_odds_for_top"] = 0

    for bucket, stat in by_odds.items():
        entry = _risk_entry(stat, strong_roi=-10, block_roi=-12, strong_n=100, block_n=300)
        if entry:
            calibration["banned_or_penalized_odds_buckets"][bucket] = entry
            calibration["min_council_score_for_top"] = max(calibration["min_council_score_for_top"], 7.0)
            if bucket in ("high", "very_high"):
                calibration["max_h2h_odds_for_top"] = min(calibration["max_h2h_odds_for_top"], 2.60)
            if bucket == "very_high":
                entry["block_top"] = True
                calibration["confidence_cap_by_bucket"]["very_high"] = 52
        n = int(stat.get("n", 0) or 0)
        roi = _num(stat.get("roi"))
        if bucket == "low" and n >= 100 and roi > 0:
            calibration["positive_buckets"].append("low")
            calibration["confidence_cap_by_bucket"]["low"] = 74

    calibration["by_market"] = by_market
    calibration["by_odds"] = by_odds
    calibration["by_league"] = by_league
    return calibration
