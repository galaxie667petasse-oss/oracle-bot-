import csv
import tempfile
from pathlib import Path

import calibration_report


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db = root / "oracle_db.json"
        db.write_text("{}", encoding="utf-8")
        before = db.read_text(encoding="utf-8")

        perfect_path = root / "perfect.csv"
        write_csv(perfect_path, ["prob", "target_win", "odds"], [
            {"prob": "1", "target_win": "1", "odds": "2.0"},
            {"prob": "0", "target_win": "0", "odds": "2.0"},
            {"prob": "1", "target_win": "1", "odds": "1.5"},
            {"prob": "0", "target_win": "0", "odds": "1.5"},
        ])
        perfect = calibration_report.build_calibration_report(str(perfect_path), prob_column="prob")
        assert perfect["status"] == "disponible"
        assert perfect["brier"] == 0.0
        assert perfect["ece"] == 0.0
        assert perfect["mce"] == 0.0

        bad_path = root / "bad.csv"
        write_csv(bad_path, ["prob", "result", "odds"], [
            {"prob": "0.90", "result": "loss", "odds": "2.0"},
            {"prob": "0.90", "result": "loss", "odds": "2.0"},
            {"prob": "0.10", "result": "win", "odds": "2.0"},
            {"prob": "0.10", "result": "win", "odds": "2.0"},
        ])
        bad = calibration_report.build_calibration_report(str(bad_path), prob_column="prob")
        assert bad["brier"] > perfect["brier"]
        assert bad["ece"] > 0.5
        assert bad["mce"] > 0.8

        missing_prob = root / "missing_prob.csv"
        write_csv(missing_prob, ["target_win"], [{"target_win": "1"}])
        absent = calibration_report.build_calibration_report(str(missing_prob), prob_column="prob")
        assert absent["status"] == "indisponible"
        assert "Colonne probabilite absente" in absent["message"]

        missing_target = root / "missing_target.csv"
        write_csv(missing_target, ["prob"], [{"prob": "0.5"}])
        no_target = calibration_report.build_calibration_report(str(missing_target), prob_column="prob")
        assert no_target["status"] == "indisponible"
        assert "Target" in no_target["message"]

        json_path = root / "reports" / "calibration_report.json"
        html_path = root / "reports" / "calibration_report.html"
        calibration_report.write_json(bad, str(json_path))
        calibration_report.write_html(bad, str(html_path))
        assert json_path.exists()
        assert html_path.exists()
        assert db.read_text(encoding="utf-8") == before

    print("test_calibration_report ok")


if __name__ == "__main__":
    main()
