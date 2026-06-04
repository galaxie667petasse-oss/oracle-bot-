import json
import tempfile
from pathlib import Path

import api_football_same_day_runner as runner


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def fixtures_payload():
    return {
        "response": [
            {
                "fixture": {"id": 7001, "date": "2026-06-04T18:00:00+00:00", "status": {"short": "NS"}},
                "league": {"name": "Serie A", "country": "Italy"},
                "teams": {"home": {"name": "Parma Calcio 1913"}, "away": {"name": "Napoli"}},
            }
        ]
    }


def odds_payload():
    return {
        "response": [
            {
                "fixture": {"id": 7001, "date": "2026-06-04T18:00:00+00:00"},
                "league": {"name": "Serie A"},
                "bookmakers": [
                    {
                        "name": "Book Test",
                        "bets": [
                            {
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "2.15"},
                                    {"value": "Away", "odd": "3.10"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixtures = root / "fixtures.json"
        odds = root / "odds.json"
        out_dir = root / "reports" / "same_day"
        ledger = root / "reports" / "shadow_ledger.csv"
        write_json(fixtures, fixtures_payload())
        write_json(odds, odds_payload())

        report = runner.run_same_day(
            "2026-06-04",
            output_dir=str(out_dir),
            ledger=str(ledger),
            fixtures_json=str(fixtures),
            odds_json=str(odds),
            allow_network=False,
            apply=False,
            max_events=1,
            prefer_side="home",
        )
        assert report["allow_network"] is False
        assert report["applied"] is False
        assert report["fixtures"] == 1
        assert report["odds_valid"] == 2
        assert report["selection_rows"] == 1
        assert report["would_add_or_added"] == 1
        assert not ledger.exists()
        assert (out_dir / "summary.json").exists()
        assert (out_dir / "selection.csv").exists()

        report_empty = runner.run_same_day("2026-06-04", output_dir=str(root / "reports" / "empty"), ledger=str(ledger), allow_network=False)
        assert report_empty["fixtures"] == 0
        assert report_empty["odds_valid"] == 0

        assert runner.main(["--date", "2026-06-04", "--dry-run", "--apply", "--fixtures-json", str(fixtures), "--odds-json", str(odds), "--ledger", str(ledger), "--output-dir", str(root / "reports" / "cli")]) == 0
        assert not ledger.exists()

    print("test_api_football_same_day_runner ok")


if __name__ == "__main__":
    main()
