import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))

from segment_analysis import build_segment_report
from telegram_ui import segments_text


def pick(idx, market_type, odds, result):
    return {
        "match_id": f"m{idx}",
        "date_key": "2024-03-01",
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": "Premier League",
        "market_type": market_type,
        "pari": f"{market_type}-{idx}",
        "odds": odds,
        "result": result,
        "shadow": True,
    }


def main():
    candidates = [pick(i, "draw", 3.5, "win" if i < 50 else "loss") for i in range(320)]
    db = {"scans": {"2024-03-01": {"picks": [], "candidates": candidates}}}
    db["segment_report"] = build_segment_report(db)
    text = segments_text(db)
    assert "SEGMENTS HISTORIQUES" in text
    assert "Échantillons" in text
    assert "Aucun segment positif fiable détecté" in text
    assert "À éviter" in text
    print("test_segments_text ok")


if __name__ == "__main__":
    main()
