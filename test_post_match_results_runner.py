import json
import tempfile
from pathlib import Path

from post_match_results_runner import run_post_match_results
from shadow_ledger import add_shadow_entry, read_ledger


def results_payload(date: str, fixture_id: int):
    return {
        "response": [{
            "fixture": {"id": fixture_id, "date": f"{date}T20:00:00+00:00", "status": {"short": "FT"}},
            "league": {"id": 1, "name": "J League", "country": "Japan"},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            "goals": {"home": 2, "away": 1},
        }]
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        fixtures = root / "results"
        fixtures.mkdir(parents=True)
        (fixtures / "2026-06-05.json").write_text(json.dumps(results_payload("2026-06-05", 99)), encoding="utf-8")
        add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="J League",
            home_team="A",
            away_team="B",
            market_type="h2h",
            side="home",
            taken_odds="2.10",
            notes="source_event_id=99",
        )
        dry = run_post_match_results(
            str(ledger),
            output_dir=str(root / "reports" / "post"),
            dry_run=True,
            apply=False,
            dates_from_ledger=True,
            results_json_dir=str(fixtures),
        )
        assert dry["matched"] == 1
        assert dry["updated"] == 0
        assert read_ledger(str(ledger))[0]["result"] == "unknown"

        applied = run_post_match_results(
            str(ledger),
            output_dir=str(root / "reports" / "post_apply"),
            dry_run=False,
            apply=True,
            dates_from_ledger=True,
            results_json_dir=str(fixtures),
        )
        assert applied["updated"] == 1
        assert read_ledger(str(ledger))[0]["result"] == "win"

    print("test_post_match_results_runner ok")


if __name__ == "__main__":
    main()
