import json
import tempfile
from pathlib import Path

from api_football_next_days_runner import run_next_days
from shadow_ledger import read_ledger


def fixtures_payload(date: str, fixture_id: int, status: str = "NS"):
    return {
        "response": [{
            "fixture": {"id": fixture_id, "date": f"{date}T20:00:00+00:00", "status": {"short": status}},
            "league": {"id": 1, "name": "J League", "country": "Japan"},
            "teams": {"home": {"name": f"Home {fixture_id}"}, "away": {"name": f"Away {fixture_id}"}},
        }]
    }


def odds_payload(fixture_id: int):
    return {
        "response": [{
            "fixture": {"id": fixture_id},
            "bookmakers": [{
                "name": "Book",
                "bets": [{
                    "name": "Match Winner",
                    "values": [
                        {"value": f"Home {fixture_id}", "odd": "2.10"},
                        {"value": "Draw", "odd": "3.20"},
                        {"value": f"Away {fixture_id}", "odd": "3.40"},
                    ],
                }],
            }],
        }]
    }


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixtures_dir = root / "fixtures"
        odds_dir = root / "odds"
        ledger = root / "reports" / "shadow_ledger.csv"
        write_json(fixtures_dir / "2026-06-05.json", fixtures_payload("2026-06-05", 1001))
        write_json(odds_dir / "2026-06-05.json", odds_payload(1001))
        write_json(fixtures_dir / "2026-06-06.json", fixtures_payload("2026-06-06", 1002, status="FT"))
        write_json(odds_dir / "2026-06-06.json", odds_payload(1002))

        dry = run_next_days(
            "2026-06-05",
            days=2,
            output_dir=str(root / "reports" / "next_days"),
            ledger=str(ledger),
            dry_run=True,
            apply=False,
            fixtures_json_dir=str(fixtures_dir),
            odds_json_dir=str(odds_dir),
        )
        assert dry["selected_total"] == 1
        assert dry["would_add_or_added_total"] == 1
        assert read_ledger(str(ledger)) == []

        applied = run_next_days(
            "2026-06-05",
            days=1,
            output_dir=str(root / "reports" / "next_days_apply"),
            ledger=str(ledger),
            dry_run=False,
            apply=True,
            fixtures_json_dir=str(fixtures_dir),
            odds_json_dir=str(odds_dir),
        )
        assert applied["applied"] is True
        assert applied["would_add_or_added_total"] == 1
        rows = read_ledger(str(ledger))
        assert len(rows) == 1
        assert rows[0]["market_type"] == "h2h"
        assert (root / "reports" / "next_days_apply" / "summary.json").exists()

    print("test_api_football_next_days_runner ok")


if __name__ == "__main__":
    main()
