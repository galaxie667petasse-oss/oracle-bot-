import csv
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_result_matcher
from api_football_results_adapter import RESULT_COLUMNS


def write_results(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()
        for row in rows:
            base = {column: "" for column in RESULT_COLUMNS}
            base.update(row)
            writer.writerow(base)


def read_row(ledger: Path, shadow_id: str):
    for row in shadow_ledger.read_ledger(str(ledger)):
        if row["shadow_id"] == shadow_id:
            return row
    raise AssertionError(f"shadow_id introuvable: {shadow_id}")


def add_entry(ledger: Path, **kwargs):
    defaults = {
        "match_date": "2026-06-17",
        "league": "World Cup",
        "market": "h2h",
        "taken_odds": "2.26",
        "bookmaker": "10Bet",
    }
    defaults.update(kwargs)
    return shadow_ledger.add_shadow_entry(str(ledger), **defaults)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        ghana = add_entry(
            ledger,
            home="Ghana",
            away="Panama",
            side="home",
            notes="source=api_football; source_event_id=1489385",
            closing_odds="2.26",
        )
        away_loss = add_entry(ledger, match_date="2026-06-18", league="EPL", home="A", away="B", side="away", taken_odds="3.00")
        away_win = add_entry(ledger, match_date="2026-06-19", league="EPL", home="C", away="D", side="away", taken_odds="2.50")
        draw_win = add_entry(ledger, match_date="2026-06-20", league="EPL", home="E", away="F", side="draw", taken_odds="3.20")
        draw_loss = add_entry(ledger, match_date="2026-06-21", league="EPL", home="G", away="H", side="draw", taken_odds="3.30")
        target = add_entry(ledger, match_date="2026-06-22", league="EPL", home="I", away="J", side="home", taken_odds="2.00")
        untouched = add_entry(ledger, match_date="2026-06-23", league="EPL", home="K", away="L", side="home", taken_odds="2.00")

        results = root / "reports" / "results.csv"
        write_results(results, [
            {"fixture_id": "1489385", "date": "2026-06-17", "league": "World Cup", "home_team": "Ghana", "away_team": "Panama", "home_goals": "1", "away_goals": "0", "status": "FT", "is_finished": "True"},
            {"fixture_id": "2", "date": "2026-06-18", "league": "EPL", "home_team": "A", "away_team": "B", "home_goals": "2", "away_goals": "1", "status": "FT", "is_finished": "True"},
            {"fixture_id": "3", "date": "2026-06-19", "league": "EPL", "home_team": "C", "away_team": "D", "home_goals": "0", "away_goals": "2", "status": "FT", "is_finished": "True"},
            {"fixture_id": "4", "date": "2026-06-20", "league": "EPL", "home_team": "E", "away_team": "F", "home_goals": "1", "away_goals": "1", "status": "FT", "is_finished": "True"},
            {"fixture_id": "5", "date": "2026-06-21", "league": "EPL", "home_team": "G", "away_team": "H", "home_goals": "2", "away_goals": "1", "status": "FT", "is_finished": "True"},
            {"fixture_id": "6", "date": "2026-06-22", "league": "EPL", "home_team": "I", "away_team": "J", "home_goals": "1", "away_goals": "0", "status": "FT", "is_finished": "True"},
            {"fixture_id": "7", "date": "2026-06-23", "league": "EPL", "home_team": "K", "away_team": "L", "home_goals": "1", "away_goals": "0", "status": "NS", "is_finished": "False"},
        ])

        before = ledger.read_text(encoding="utf-8")
        dry = shadow_result_matcher.match_results(str(ledger), str(results), dry_run=True, apply=False)
        assert dry["matches_found"] == 7
        assert dry["updated"] == 0
        assert dry["skipped_not_finished"] == 1
        assert ledger.read_text(encoding="utf-8") == before

        applied_target = shadow_result_matcher.match_results(
            str(ledger),
            str(results),
            dry_run=False,
            apply=True,
            target_shadow_id=target["shadow_id"],
        )
        assert applied_target["updated"] == 1
        assert read_row(ledger, target["shadow_id"])["result_status"] == "win"
        assert read_row(ledger, untouched["shadow_id"])["result_status"] == "unknown"

        applied = shadow_result_matcher.match_results(str(ledger), str(results), dry_run=False, apply=True)
        assert applied["updated"] == 5
        ghana_row = read_row(ledger, ghana["shadow_id"])
        assert ghana_row["result_fixture_id"] == "1489385"
        assert ghana_row["result_status"] == "win"
        assert ghana_row["profit_units"] == "1.26"
        assert ghana_row["roi_percent"] == "126.0"
        assert ghana_row["settlement_status"] == "settled"
        assert read_row(ledger, away_loss["shadow_id"])["result_status"] == "loss"
        assert read_row(ledger, away_win["shadow_id"])["result_status"] == "win"
        assert read_row(ledger, draw_win["shadow_id"])["result_status"] == "win"
        assert read_row(ledger, draw_loss["shadow_id"])["result_status"] == "loss"
        assert read_row(ledger, untouched["shadow_id"])["result_status"] == "unknown"

        no_overwrite = shadow_result_matcher.match_results(str(ledger), str(results), dry_run=False, apply=True)
        assert no_overwrite["already_settled"] == 6
        assert no_overwrite["updated"] == 0

        overwrite_results = root / "reports" / "overwrite.csv"
        write_results(overwrite_results, [
            {"fixture_id": "1489385", "date": "2026-06-17", "league": "World Cup", "home_team": "Ghana", "away_team": "Panama", "home_goals": "0", "away_goals": "1", "status": "FT", "is_finished": "True"},
        ])
        overwrite = shadow_result_matcher.match_results(
            str(ledger),
            str(overwrite_results),
            overwrite=True,
            dry_run=False,
            apply=True,
            target_shadow_id=ghana["shadow_id"],
        )
        assert overwrite["updated"] == 1
        overwritten_row = read_row(ledger, ghana["shadow_id"])
        assert overwritten_row["result_status"] == "loss"
        assert overwritten_row["settlement_status"] == "overwritten"

        ambiguous_ledger = root / "reports" / "ambiguous_ledger.csv"
        ambiguous = add_entry(ambiguous_ledger, match_date="2026-06-24", league="EPL", home="M", away="N", side="home")
        ambiguous_results = root / "reports" / "ambiguous_results.csv"
        write_results(ambiguous_results, [
            {"fixture_id": "8", "date": "2026-06-24", "league": "EPL", "home_team": "M", "away_team": "N", "home_goals": "1", "away_goals": "0", "status": "FT", "is_finished": "True"},
            {"fixture_id": "9", "date": "2026-06-24", "league": "EPL", "home_team": "M", "away_team": "N", "home_goals": "2", "away_goals": "0", "status": "FT", "is_finished": "True"},
        ])
        ambiguous_report = shadow_result_matcher.match_results(str(ambiguous_ledger), str(ambiguous_results), dry_run=False, apply=True)
        assert ambiguous_report["ambiguous"] == 1
        assert ambiguous_report["updated"] == 0
        assert read_row(ambiguous_ledger, ambiguous["shadow_id"])["result_status"] == "unknown"

    print("test_shadow_result_matcher ok")


if __name__ == "__main__":
    main()
