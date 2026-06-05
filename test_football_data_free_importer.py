import csv
import tempfile
from pathlib import Path

from football_data_free_importer import build_import


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = rows[0].keys()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "E0.csv"
        write_csv(source, [{
            "Div": "E0",
            "Date": "01/01/2024",
            "HomeTeam": "Arsenal",
            "AwayTeam": "Chelsea",
            "FTHG": "2",
            "FTAG": "1",
            "FTR": "H",
            "B365H": "2.00",
            "B365D": "3.40",
            "B365A": "3.80",
        }])
        report = build_import(
            str(source),
            output=str(root / "reports" / "football_data_normalized.csv"),
            summary_json=str(root / "reports" / "summary.json"),
            html_output=str(root / "reports" / "summary.html"),
        )
        assert report["rows"] == 1
        assert report["has_results"] is True
        assert report["has_odds"] is True
        assert report["can_compute_roi"] is True
        assert report["can_compute_clv"] is False
        assert "historical_odds_available_but_closing_uncertain" in report["warnings"]
        assert (root / "reports" / "football_data_normalized.csv").exists()

    print("test_football_data_free_importer ok")


if __name__ == "__main__":
    main()
