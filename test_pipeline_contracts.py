import csv
import tempfile
from pathlib import Path

import pipeline_contracts as contracts


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    assert "odds_snapshot" in contracts.CONTRACTS
    assert contracts.CONTRACTS["odds_snapshot"]["required_columns"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        valid = root / "valid.csv"
        write_csv(valid, [contracts.CONTRACTS["odds_snapshot"]["minimal_example"]])
        result = contracts.validate_csv("odds_snapshot", str(valid))
        assert result["ok"], result
        invalid = root / "invalid.csv"
        write_csv(invalid, [contracts.CONTRACTS["odds_snapshot"]["rejected_example"]])
        bad = contracts.validate_csv("odds_snapshot", str(invalid))
        assert not bad["ok"]
        assert "cote" in " ".join(bad["errors"])
        json_path = root / "contracts.json"
        html_path = root / "contracts.html"
        contracts.write_json(str(json_path))
        contracts.write_html(str(html_path))
        assert json_path.exists()
        assert "Contrats" in html_path.read_text(encoding="utf-8")
    print("test_pipeline_contracts ok")


if __name__ == "__main__":
    main()
