import csv
import tempfile
from pathlib import Path

from historical_dataset_builder import (
    CSV_COLUMNS,
    BuildStats,
    Match,
    Odd,
    dedupe_rows,
    result_for_market,
    rows_for_match,
    write_csv,
)


def sample_match(home_goals=2, away_goals=1):
    return Match(
        date="2026-01-10",
        home="Alpha FC",
        away="Beta FC",
        competition="PL",
        home_goals=home_goals,
        away_goals=away_goals,
        kickoff="2026-01-10T15:00:00Z",
        source="test",
    )


def test_results():
    match = sample_match(2, 1)
    assert result_for_market(match, "h2h_home") == "win"
    assert result_for_market(match, "h2h_away") == "loss"
    assert result_for_market(match, "draw") == "loss"
    assert result_for_market(match, "over25") == "win"
    assert result_for_market(match, "under25") == "loss"
    assert result_for_market(match, "btts_yes") == "win"
    assert result_for_market(match, "btts_no") == "loss"

    draw = sample_match(0, 0)
    assert result_for_market(draw, "draw") == "win"
    assert result_for_market(draw, "under25") == "win"
    assert result_for_market(draw, "btts_no") == "win"


def test_deduplication():
    row = {
        "date": "2026-01-10",
        "home": "Alpha FC",
        "away": "Beta FC",
        "market_type": "h2h",
        "pari": "Victoire Alpha FC",
    }
    unique, skipped = dedupe_rows([dict(row), dict(row)])
    assert len(unique) == 1
    assert skipped == 1


def test_missing_odds_ignored():
    stats = BuildStats()
    odds = {
        "h2h_home": Odd(2.0, "TestBook", "test"),
        "h2h_away": Odd(2.8, "TestBook", "test"),
    }
    rows = rows_for_match(sample_match(), odds, stats)
    assert len(rows) == 2
    assert stats.rows_skipped == 5
    assert all(row["odds"] for row in rows)


def test_csv_columns():
    odds = {
        "h2h_home": Odd(2.0, "TestBook", "test"),
        "draw": Odd(3.1, "TestBook", "test"),
        "over25": Odd(1.9, "TestBook", "test"),
    }
    rows = rows_for_match(sample_match(), odds)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "historical_backtest.csv"
        write_csv(rows, str(path))
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert tuple(reader.fieldnames) == CSV_COLUMNS
            loaded = list(reader)
            assert loaded
            for column in ("date", "home", "away", "competition", "market_type", "pari", "odds", "result", "bookmaker", "source", "visible"):
                assert column in loaded[0]


def main():
    test_results()
    test_deduplication()
    test_missing_odds_ignored()
    test_csv_columns()
    print("test_historical_dataset_builder ok")


if __name__ == "__main__":
    main()
