import json
from datetime import datetime
from typing import Any, Dict, List
from config import settings


def load_db() -> Dict[str, Any]:
    if settings.db_file.exists():
        try:
            db = json.loads(settings.db_file.read_text(encoding="utf-8"))
        except Exception:
            db = {}
    else:
        db = {}
    db.setdefault("scans", {})
    db.setdefault("learning", {})
    db.setdefault("agent_weights", {})
    return db


def save_db(db: Dict[str, Any]) -> None:
    settings.db_file.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def settled_picks(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        pick
        for scan in db.get("scans", {}).values()
        for pick in scan.get("picks", [])
        if pick.get("result") in ("win", "loss")
    ]


def unit_profit(pick: Dict[str, Any]) -> float:
    odds = float(pick.get("odds", 1.0) or 1.0)
    return odds - 1.0 if pick.get("result") == "win" else -1.0


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


def _group(rows: List[Dict[str, Any]], fn):
    out = {}
    for p in rows:
        key = fn(p)
        out.setdefault(key, {"n": 0, "w": 0, "profit": 0.0})
        out[key]["n"] += 1
        out[key]["w"] += 1 if p.get("result") == "win" else 0
        out[key]["profit"] += unit_profit(p)
    for v in out.values():
        v["wr"] = round(v["w"] / v["n"] * 100, 1) if v["n"] else 0
        v["roi"] = round(v["profit"] / v["n"] * 100, 1) if v["n"] else 0
    return out


def build_learning(db: Dict[str, Any]) -> Dict[str, Any]:
    rows = settled_picks(db)
    return {
        "samples": len(rows),
        "by_market": _group(rows, lambda p: p.get("market_type", "?")),
        "by_odds": _group(rows, lambda p: odds_bucket(float(p.get("odds", 2.0) or 2.0))),
        "by_league": _group(rows, lambda p: league_bucket(p.get("competition", ""))),
        "updated_at": datetime.utcnow().isoformat(),
    }


def pending_picks(db: Dict[str, Any]):
    for date_key, scan in db.get("scans", {}).items():
        for idx, pick in enumerate(scan.get("picks", [])):
            if pick.get("result") is None:
                yield date_key, idx, pick
