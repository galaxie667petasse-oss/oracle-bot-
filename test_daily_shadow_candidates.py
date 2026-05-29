import csv
import tempfile
from pathlib import Path

import daily_shadow_candidates


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "live.csv"
        output = root / "reports" / "daily_shadow_candidates.csv"
        data_dir = root / "data"
        data_dir.mkdir()
        write_csv(
            source,
            ["date", "league", "home", "away", "market_type", "pari", "odds", "model_probability", "market_probability", "is_home_pick"],
            [
                {"date": "2026-06-01", "league": "EPL", "home": "Arsenal", "away": "Chelsea", "market_type": "h2h", "pari": "home", "odds": "2.10", "model_probability": "0.52", "market_probability": "0.48", "is_home_pick": "1"},
                {"date": "2026-06-01", "league": "EPL", "home": "Spurs", "away": "Everton", "market_type": "h2h", "pari": "home", "odds": "1.80", "model_probability": "0.50", "market_probability": "0.51", "is_home_pick": "1"},
                {"date": "2026-06-02", "league": "EPL", "home": "A", "away": "B", "market_type": "total", "pari": "over", "odds": "1.90", "model_probability": "0.53", "market_probability": "0.50", "is_home_pick": "0"},
            ],
        )
        summary = daily_shadow_candidates.build_daily_candidates(str(source), "2026-06-01", str(output))
        assert summary["rows_for_date"] == 2
        assert summary["candidates_written"] == 2
        rows = read_rows(output)
        assert rows[0]["status"] == "watchlist"
        assert rows[0]["reason"] == "observation shadow sans conseil de mise"
        assert rows[1]["status"] == "rejected"

        empty_output = root / "reports" / "empty.csv"
        empty = daily_shadow_candidates.build_daily_candidates(str(source), "2026-06-03", str(empty_output))
        assert empty["candidates_written"] == 0
        assert read_rows(empty_output) == []

        try:
            daily_shadow_candidates.build_daily_candidates(str(source), "2026-06-01", str(data_dir / "daily.csv"))
            raise AssertionError("ecriture data non bloquee")
        except ValueError:
            pass
        assert list(data_dir.iterdir()) == []

    print("test_daily_shadow_candidates ok")


if __name__ == "__main__":
    main()
