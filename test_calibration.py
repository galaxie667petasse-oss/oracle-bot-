import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))

from calibration import build_calibration
from store import build_learning


def pick(idx, market_type, odds, result, date_key="2026-01-01"):
    return {
        "match_id": f"m{idx}",
        "date_key": date_key,
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

    mixed = []
    for i in range(400):
        mixed.append(pick(f"old{i}", "total", 1.5, "win" if i < 340 else "loss", "2008-01-01"))
    for i in range(400):
        mixed.append(pick(f"new{i}", "total", 1.5, "win" if i < 160 else "loss", "2021-01-01"))
    db2 = {"scans": {"mixed": {"picks": [], "candidates": mixed}}}
    db2["learning"] = build_learning(db2)
    calibration2 = build_calibration(db2, db2["learning"])
    assert "weighted_by_market" in calibration2
    assert "weighted_by_period" in calibration2
    assert db2["learning"]["weighted_by_period"]["archive_pre2012"]["weighted_n"] < db2["learning"]["by_period"]["archive_pre2012"]["n"]
    assert calibration2["weighted_by_market"]["total"]["weighted_roi"] < 0
    assert calibration2["positive_segments_count"] == 0
    print("test_calibration ok")


if __name__ == "__main__":
    main()
