import csv
import tempfile
from pathlib import Path

import historical_odds_schema_detector as detector


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "reports" / "hist.csv"
        rows = [
            {"Date": "2024-01-01", "Div": "EPL", "HomeTeam": "A", "AwayTeam": "B", "FTHG": "2", "FTAG": "1", "B365H": "2.0", "B365D": "3.4", "B365A": "3.8", "B365CH": "1.9", "B365CD": "3.5", "B365CA": "4.0", "C_LTH": "0.5"},
            {"Date": "2024-01-02", "Div": "EPL", "HomeTeam": "C", "AwayTeam": "D", "FTHG": "0", "FTAG": "0", "B365H": "1.8", "B365D": "3.2", "B365A": "4.5", "B365CH": "1.7", "B365CD": "3.1", "B365CA": "4.8", "C_LTH": "0.7"},
        ]
        write_csv(source, rows)
        report = detector.detect_schema(str(source), profile_columns="C_LTH")
        assert report["verdict"] == "h2h_complete"
        assert report["detected_columns"]["closing_home"] == "B365CH"
        assert report["column_profiles"]["C_LTH"]["verdict"] == "numeric_but_not_odds"
        out = root / "reports" / "schema.json"
        html = root / "reports" / "schema.html"
        detector.write_json(report, str(out))
        detector.write_html(report, str(html))
        assert out.exists() and html.exists()
    print("test_historical_odds_schema_detector ok")


if __name__ == "__main__":
    main()
