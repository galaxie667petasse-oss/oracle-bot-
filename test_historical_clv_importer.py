import csv
import tempfile
from pathlib import Path

import historical_clv_importer


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
        write_csv(source, [
            {"Date": "2024-01-01", "Div": "EPL", "HomeTeam": "A", "AwayTeam": "B", "FTHG": "2", "FTAG": "1", "B365H": "2.0", "B365D": "3.2", "B365A": "4.0", "B365CH": "1.8", "B365CD": "3.1", "B365CA": "4.2"},
        ])
        output = root / "reports" / "historical_clv.csv"
        report = historical_clv_importer.import_historical_clv(str(source), output=str(output))
        assert output.exists()
        assert report["valid_rows"] == 3
        rows = list(csv.DictReader(output.open(newline="", encoding="utf-8")))
        home = [row for row in rows if row["side"] == "home"][0]
        assert float(home["clv_percent"]) > 0
        assert float(home["profit_unit"]) > 0
        try:
            historical_clv_importer.import_historical_clv(str(source), output=str(root / "data" / "bad.csv"))
            raise AssertionError("ecriture data acceptee")
        except ValueError:
            pass
    print("test_historical_clv_importer ok")


if __name__ == "__main__":
    main()
