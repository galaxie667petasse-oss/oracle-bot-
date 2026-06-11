import json
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

import api_football_next_days_runner as runner
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

        calls = []
        original_same_day = runner.run_same_day

        def fake_same_day(date, **kwargs):
            calls.append({"date": date, **kwargs})
            return {
                "date": date,
                "allow_network": kwargs.get("allow_network"),
                "fixtures": 0,
                "odds_valid": 0,
                "valid_h2h_not_finished_rows": 0,
                "selection_rows": 0,
                "would_add_or_added": 0,
                "lab_only": True,
                "can_influence_picks": False,
            }

        runner.run_same_day = fake_same_day
        try:
            no_network = runner.run_next_days(
                "2026-06-07",
                days=1,
                output_dir=str(root / "reports" / "mock_no_network"),
                ledger=str(root / "reports" / "mock_ledger.csv"),
                allow_network=False,
                dry_run=True,
                apply=False,
                debug_network=True,
            )
            assert calls[-1]["allow_network"] is False
            assert no_network["allow_network"] is False

            network = runner.run_next_days(
                "2026-06-08",
                days=1,
                output_dir=str(root / "reports" / "mock_network"),
                ledger=str(root / "reports" / "mock_ledger.csv"),
                allow_network=True,
                dry_run=True,
                apply=False,
                debug_network=True,
            )
            assert calls[-1]["allow_network"] is True
            assert network["allow_network"] is True
            assert network["network_debug"][0]["allow_network_propagated"] is True

            out = StringIO()
            with redirect_stdout(out):
                runner.print_report(network)
            printed = out.getvalue()
            assert "allow_network=True" in printed
            assert "API_FOOTBALL_KEY" not in printed
            assert "SECRET" not in printed
        finally:
            runner.run_same_day = original_same_day

        def fake_broken_same_day(date, **kwargs):
            return {
                "date": date,
                "allow_network": False,
                "fixtures": 0,
                "odds_valid": 0,
                "valid_h2h_not_finished_rows": 0,
                "selection_rows": 0,
                "would_add_or_added": 0,
            }

        runner.run_same_day = fake_broken_same_day
        try:
            try:
                runner.run_next_days(
                    "2026-06-09",
                    days=1,
                    output_dir=str(root / "reports" / "broken_network"),
                    ledger=str(root / "reports" / "mock_ledger.csv"),
                    allow_network=True,
                    dry_run=True,
                    apply=False,
                )
                raise AssertionError("propagation reseau cassee non detectee")
            except RuntimeError as exc:
                assert "--allow-network demande mais non propage" in str(exc)
        finally:
            runner.run_same_day = original_same_day

    print("test_api_football_next_days_runner ok")


if __name__ == "__main__":
    main()
