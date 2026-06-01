import csv
import tempfile
from pathlib import Path

import matchday_pack
import matchday_status_report


def fill_manual(path: Path, near_close: bool = False) -> None:
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    for row in rows:
        row["captured_at"] = "2026-06-01T18:55:00" if near_close else "2026-06-01T10:00:00"
        row["bookmaker"] = "Book"
        row["side"] = "home"
        row["odds"] = "2.00" if near_close else "2.10"
        row["is_near_close"] = "true" if near_close else "false"
        row["notes"] = "source manuelle reelle"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_source(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["match_date", "league", "home_team", "away_team", "kickoff_time"])
        writer.writeheader()
        writer.writerow({"match_date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea", "kickoff_time": "2026-06-01T19:00:00"})


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "matches.csv"
        write_source(source)
        pack = root / "reports" / "matchday_2026_06_01"
        matchday_pack.create_pack("2026-06-01", str(pack), str(source))
        empty = matchday_status_report.build_status_report(str(pack))
        assert empty["phase_detected"] == "empty"
        fill_manual(pack / "matchday_manual_odds.csv", near_close=False)
        pre = matchday_status_report.build_status_report(str(pack))
        assert pre["phase_detected"] == "pre_match_ready"
        assert pre["next_actions"]
        fill_manual(pack / "matchday_near_close.csv", near_close=True)
        near = matchday_status_report.build_status_report(str(pack))
        assert near["phase_detected"] == "near_close_ready"
        with (pack / "matchday_results.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["shadow_id", "result", "notes"])
            writer.writeheader()
            writer.writerow({"shadow_id": "sh_test", "result": "win", "notes": "manuel"})
        complete = matchday_status_report.build_status_report(str(pack))
        assert complete["phase_detected"] == "complete"
        out = root / "reports" / "matchday_status.json"
        html = root / "reports" / "matchday_status.html"
        matchday_status_report.write_json(complete, str(out))
        matchday_status_report.write_html(complete, str(html))
        assert out.exists() and html.exists()
    print("test_matchday_status_report ok")


if __name__ == "__main__":
    main()
