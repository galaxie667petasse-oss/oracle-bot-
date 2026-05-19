import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))

from calibration import build_calibration
from store import build_learning


def pick(idx, market_type, odds, result):
    return {
        "match_id": f"m{idx}",
        "date_key": "2026-01-01",
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": "Unknown League",
        "market_type": market_type,
        "pari": f"{market_type}-{idx}",
        "odds": odds,
        "result": result,
        "shadow": True,
    }


def main():
    candidates = []
    for i in range(320):
        candidates.append(pick(f"h{i}", "h2h", 3.4, "win" if i < 80 else "loss"))
    for i in range(320):
        candidates.append(pick(f"d{i}", "draw", 3.6, "win" if i < 70 else "loss"))
    for i in range(140):
        candidates.append(pick(f"v{i}", "h2h", 3.8, "win" if i < 20 else "loss"))
    for i in range(140):
        candidates.append(pick(f"l{i}", "total", 1.5, "win" if i < 105 else "loss"))
    db = {"scans": {"2026-01-01": {"picks": [], "candidates": candidates}}}
    db["learning"] = build_learning(db)
    calibration = build_calibration(db, db["learning"])

    assert calibration["maturity_level"] == "calibration active"
    assert "h2h" in calibration["banned_or_penalized_markets"]
    assert "draw" in calibration["banned_or_penalized_markets"]
    assert "very_high" in calibration["banned_or_penalized_odds_buckets"]
    assert calibration["banned_or_penalized_odds_buckets"]["very_high"]["block_top"] is True
    assert "low" in calibration["positive_buckets"]
    print("test_calibration ok")


if __name__ == "__main__":
    main()
