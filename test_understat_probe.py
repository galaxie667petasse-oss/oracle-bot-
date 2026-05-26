import csv
import sys
import tempfile
import types
from pathlib import Path

import understat_probe


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    status = understat_probe.check_soccerdata_available("module_absent_pour_test_oracle")
    assert status["available"] is False
    assert "python -m pip install soccerdata" in status["message"]
    assert isinstance(understat_probe.as_path("external_data\\understat_probe\\x.csv"), Path)
    assert isinstance(understat_probe.as_path("external_data/understat_probe/x.csv"), Path)
    seasons = understat_probe.parse_seasons("2020,2021,2022,2023,2024")
    assert [season["label"] for season in seasons] == [
        "2020-2021",
        "2021-2022",
        "2022-2023",
        "2023-2024",
        "2024-2025",
    ]
    assert [season["soccerdata"] for season in seasons] == ["20-21", "21-22", "22-23", "23-24", "24-25"]
    assert len({season["soccerdata"] for season in seasons}) == 5
    assert understat_probe.parse_seasons("2020-2021")[0]["soccerdata"] == "20-21"
    assert understat_probe.parse_seasons("20-21")[0]["label"] == "2020-2021"
    try:
        understat_probe.parse_seasons("2020,20-21")
        raise AssertionError("doublon saison non bloque")
    except ValueError as exc:
        assert "doublon" in str(exc).lower()
    assert understat_probe.compact_soccerdata_season_to_label("2021") == "2020-2021"
    assert understat_probe.compact_soccerdata_season_to_label("2122") == "2021-2022"

    raw = [
        {
            "date": "2024-08-16",
            "league": "EPL",
            "season": "2024",
            "home_team": "Manchester Utd",
            "away_team": "Fulham",
            "home_goals": "1",
            "away_goals": "0",
            "home_xg": "2.4",
            "away_xg": "0.4",
            "match_id": "u1",
            "extra_col": "ignore",
        }
    ]
    mapped, meta = understat_probe.standardize_records(raw)
    assert mapped[0]["date"] == "2024-08-16"
    assert mapped[0]["home_team"] == "Manchester Utd"
    assert mapped[0]["home_xg"] == 2.4
    assert mapped[0]["away_xg"] == 0.4
    assert mapped[0]["result"] == "H"
    assert mapped[0]["source"] == "understat_soccerdata"
    assert meta["xg_available"] is True
    assert "extra_col" in meta["unrecognized_columns"]
    assert meta["duplicates_removed"] == 0

    zero_raw = [{
        "date": "2024-08-17",
        "league": "EPL",
        "season": "2024",
        "home_team": "Ipswich",
        "away_team": "Liverpool",
        "home_goals": 0,
        "away_goals": 2,
        "home_xg": 0.0,
        "away_xg": 1.8,
    }]
    zero_rows, _zero_meta = understat_probe.standardize_records(zero_raw)
    assert zero_rows[0]["home_goals"] == 0
    assert zero_rows[0]["home_xg"] == 0.0
    assert zero_rows[0]["result"] == "A"

    duplicated, duplicate_meta = understat_probe.standardize_records(raw + raw)
    assert len(duplicated) == 1
    assert duplicate_meta["duplicates_removed"] == 1

    alternative = [{
        "match_date": "16/08/2024",
        "competition": "EPL",
        "year": "2024",
        "home": "Arsenal",
        "away": "Wolves",
        "fthg": "2",
        "ftag": "0",
        "hxg": "1,8",
        "axg": "0,6",
        "understat_id": "alt1",
    }]
    alternative_rows, alternative_meta = understat_probe.standardize_records(alternative)
    assert alternative_rows[0]["date"] == "2024-08-16"
    assert alternative_rows[0]["home_goals"] == 2
    assert alternative_rows[0]["home_xg"] == 1.8
    assert alternative_meta["xg_available"] is True

    no_xg, no_xg_meta = understat_probe.standardize_records([{
        "date": "2024-08-16",
        "home_team": "A",
        "away_team": "B",
        "home_goals": "1",
        "away_goals": "1",
    }])
    assert no_xg[0]["home_xg"] == ""
    assert no_xg_meta["xg_available"] is False

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        matches_csv = root / "data" / "MATCHES.csv"
        oracle_db.write_text("{}", encoding="utf-8")
        matches_csv.parent.mkdir(parents=True, exist_ok=True)
        matches_csv.write_text("date,home,away\n", encoding="utf-8")
        before_db = oracle_db.read_text(encoding="utf-8")
        before_matches = matches_csv.read_text(encoding="utf-8")

        captured = {}

        class FakeFrame:
            columns = []

            def reset_index(self):
                self.columns = ["date", "home_team", "away_team", "home_xg", "away_xg"]
                return self

            def to_dict(self, _kind):
                return [{
                    "date": "2024-08-16",
                    "home_team": "A",
                    "away_team": "B",
                    "home_xg": "1.0",
                    "away_xg": "0.5",
                }]

        class FakeUnderstat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def read_schedule(self):
                return FakeFrame()

        fake_module = types.ModuleType("soccerdata")
        fake_module.Understat = FakeUnderstat
        previous = sys.modules.get("soccerdata")
        sys.modules["soccerdata"] = fake_module
        try:
            fetched = understat_probe.fetch_understat_records(["ENG-Premier League"], ["20-21", "21-22"], cache_dir=root / "external_data" / "understat_probe" / "cache")
        finally:
            if previous is None:
                sys.modules.pop("soccerdata", None)
            else:
                sys.modules["soccerdata"] = previous
        assert fetched[0]["home_team"] == "A"
        assert isinstance(captured["data_dir"], Path)
        assert captured["seasons"] == ["20-21", "21-22"]

        output = root / "external_data" / "understat_probe" / "sample.csv"
        understat_probe.write_csv(mapped, str(output))
        assert output.exists()
        profile = understat_probe.profile_csv(str(output))
        assert profile["rows"] == 1
        assert profile["date_min"] == "2024-08-16"
        assert profile["xg_available_rate"] == 100.0
        assert profile["verdict"] == "exploitable rolling xG"
        assert profile["sample_warning"] == "echantillon faible"

        rich_rows = []
        for index in range(120):
            rich_rows.append({
                "date": f"2024-09-{(index % 28) + 1:02d}",
                "league": "EPL",
                "season": "2024",
                "home_team": f"Home {index}",
                "away_team": f"Away {index}",
                "home_goals": "1",
                "away_goals": "0",
                "home_xg": "1.2",
                "away_xg": "0.8",
                "result": "H",
                "source": "understat_soccerdata",
                "source_match_id": str(index),
            })
        rich_path = root / "external_data" / "understat_probe" / "rich.csv"
        write_csv(rich_path, understat_probe.EXPECTED_COLUMNS, rich_rows)
        rich_profile = understat_probe.profile_csv(str(rich_path))
        assert rich_profile["verdict"] == "exploitable rolling xG"
        assert rich_profile["sample_warning"] == "echantillon faible"

        poor_path = root / "external_data" / "understat_probe" / "poor.csv"
        write_csv(poor_path, understat_probe.EXPECTED_COLUMNS, [{**row, "home_xg": "", "away_xg": ""} for row in rich_rows[:10]])
        poor_profile = understat_probe.profile_csv(str(poor_path))
        assert poor_profile["verdict"] == "inutilisable"

        no_date_path = root / "external_data" / "understat_probe" / "no_date.csv"
        write_csv(no_date_path, understat_probe.EXPECTED_COLUMNS, [{**row, "date": ""} for row in rich_rows])
        no_date_profile = understat_probe.profile_csv(no_date_path)
        assert no_date_profile["verdict"] == "inutilisable"

        try:
            understat_probe.validate_output_path(str(root / "data" / "bad.csv"))
            raise AssertionError("sortie data/ non bloquee")
        except ValueError as exc:
            assert "data/" in str(exc)

        before_files = sorted(path.relative_to(root) for path in (root / "data").rglob("*"))
        understat_probe.main(["--check"], soccerdata_module="module_absent_pour_test_oracle")
        after_files = sorted(path.relative_to(root) for path in (root / "data").rglob("*"))
        assert before_files == after_files
        assert oracle_db.read_text(encoding="utf-8") == before_db
        assert matches_csv.read_text(encoding="utf-8") == before_matches

    print("test_understat_probe ok")


if __name__ == "__main__":
    main()
