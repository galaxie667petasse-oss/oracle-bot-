import csv
import tempfile
from pathlib import Path

import understat_xg_pipeline


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
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")
        data_dir = root / "data"
        data_dir.mkdir()

        try:
            understat_xg_pipeline.build_pipeline(str(root / "absent.csv"), str(root / "features.csv"))
            raise AssertionError("fichier externe absent non bloque")
        except FileNotFoundError as exc:
            assert "externe" in str(exc)

        external = root / "external.csv"
        write_csv(external, ["date", "season", "home_team", "away_team", "home_xg", "away_xg", "home_goals", "away_goals"], [{
            "date": "2024-08-01",
            "season": "2024-2025",
            "home_team": "Alpha",
            "away_team": "Beta",
            "home_xg": "1.0",
            "away_xg": "0.5",
            "home_goals": "1",
            "away_goals": "0",
        }])
        try:
            understat_xg_pipeline.build_pipeline(str(external), str(root / "missing_features.csv"))
            raise AssertionError("features absent non bloque")
        except FileNotFoundError as exc:
            assert "Feature matrix" in str(exc)

        features = root / "features.csv"
        write_csv(features, ["date", "home", "away", "market_type", "pari", "result", "odds", "no_vig_probability"], [{
            "date": "2024-08-01",
            "home": "Alpha",
            "away": "Beta",
            "market_type": "h2h",
            "pari": "Victoire Alpha",
            "result": "win",
            "odds": "1.8",
            "no_vig_probability": "0.55",
        }])

        dry = understat_xg_pipeline.build_pipeline(str(external), str(features), out_prefix="dry", dry_run=True)
        assert dry["dry_run"] is True
        assert not (Path("reports") / "dry_pipeline_summary.json").exists()

        summary = understat_xg_pipeline.build_pipeline(
            str(external),
            str(features),
            out_prefix="tmp_pipeline_test",
            expected_seasons="2024-2025",
            skip_model=True,
            skip_benchmark=True,
        )
        assert summary["quality"]["ok"] is True
        assert summary["join_diagnostics"]["ok"] is True
        assert summary["join_rate_after_alias"] == 100.0
        assert summary["join_quality"] == "excellent"
        assert summary["modeling_allowed_by_join_quality"] is True
        assert summary["rolling_features"]["ok"] is True
        assert summary["xg_model"]["ok"] is False
        assert summary["benchmark"]["ok"] is False
        assert (Path("reports") / "tmp_pipeline_test_pipeline_summary.json").exists()

        bad_external = root / "bad_external.csv"
        write_csv(bad_external, ["date", "season", "home_team", "away_team", "home_xg", "away_xg"], [{
            "date": "2024-08-02",
            "season": "2024-2025",
            "home_team": "No Match Home",
            "away_team": "No Match Away",
            "home_xg": "1.0",
            "away_xg": "1.0",
        }])
        try:
            understat_xg_pipeline.build_pipeline(
                str(bad_external),
                str(features),
                out_prefix="tmp_pipeline_strict",
                expected_seasons="2024-2025",
                skip_benchmark=True,
                strict_join=True,
            )
            raise AssertionError("strict-join aurait du bloquer")
        except ValueError as exc:
            assert "strict-join" in str(exc)
        assert (Path("reports") / "tmp_pipeline_strict_join_diagnostics.json").exists()
        assert oracle_db.read_text(encoding="utf-8") == before
        assert list(data_dir.iterdir()) == []

    print("test_understat_xg_pipeline ok")


if __name__ == "__main__":
    main()
