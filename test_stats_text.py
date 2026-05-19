import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))

from agents import agent_weights
from store import build_learning
from telegram_ui import stats_text


def pick(idx, market_type, odds, result):
    return {
        "match_id": f"s{idx}",
        "date_key": "2026-01-01",
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": "Other League",
        "market_type": market_type,
        "pari": f"{market_type}-{idx}",
        "odds": odds,
        "result": result,
        "decision": "REFUSE",
        "shadow": True,
    }


def main():
    candidates = []
    for i in range(140):
        candidates.append(pick(f"h{i}", "h2h", 3.4, "win" if i < 35 else "loss"))
    for i in range(140):
        candidates.append(pick(f"d{i}", "draw", 3.3, "win" if i < 30 else "loss"))
    for i in range(140):
        candidates.append(pick(f"v{i}", "h2h", 3.8, "win" if i < 25 else "loss"))
    db = {"scans": {"2026-01-01": {"picks": [], "candidates": candidates}}}
    db["learning"] = build_learning(db)
    agent_weights(db)
    text = stats_text(db)
    assert "Calibration active" in text
    assert "Marchés pénalisés" in text
    assert "Historique défavorable" in text
    print("test_stats_text ok")


if __name__ == "__main__":
    main()
