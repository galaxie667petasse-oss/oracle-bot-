import json
import tempfile
from pathlib import Path

import near_close_today_helper as helper
import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        sport_map = root / "config" / "sport_map.json"
        output = root / "reports" / "near_today.json"
        sport_map.parent.mkdir(parents=True, exist_ok=True)
        sport_map.write_text(json.dumps({"Serie A": "soccer_italy_serie_a"}), encoding="utf-8")
        shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-04",
            league="Serie A",
            home="Parma",
            away="Napoli",
            market="h2h",
            side="home",
            taken_odds="2.10",
            notes="source=api_football; source_event_id=7001; kickoff_time=2026-06-04T18:00:00+00:00",
        )
        shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="Serie A",
            home="Milan",
            away="Inter",
            market="h2h",
            side="away",
            taken_odds="2.30",
        )
        report = helper.build_today_helper(str(ledger), sport_map=str(sport_map), date="2026-06-04")
        assert report["pending_today"] == 1
        assert report["sport_keys"]["Serie A"] == "soccer_italy_serie_a"
        assert report["api_football_fixture_ids"] == ["7001"]
        assert any("near_close_batch_runner.py" in command for command in report["commands"])
        assert any("api_football_odds_adapter.py" in command for command in report["commands"])
        helper.write_json(report, str(output))
        assert output.exists()
        assert helper.main(["--ledger", str(ledger), "--sport-map", str(sport_map), "--date", "2026-06-04", "--output", str(output)]) == 0
    print("test_near_close_today_helper ok")


if __name__ == "__main__":
    main()
