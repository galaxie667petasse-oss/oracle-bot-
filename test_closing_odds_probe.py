import csv
import tempfile
from pathlib import Path

import closing_odds_probe


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
        source = root / "matches.csv"
        write_csv(
            source,
            ["Date", "HomeTeam", "AwayTeam", "B365H", "B365D", "B365A", "C_LTH", "C_LTD", "C_LTA", "PCO", "PCU"],
            [{"Date": "2024-01-01", "HomeTeam": "A", "AwayTeam": "B", "B365H": "2.0", "B365D": "3.2", "B365A": "4.0", "C_LTH": "1.9", "C_LTD": "3.1", "C_LTA": "4.2", "PCO": "1.8", "PCU": "2.0"}],
        )
        before = source.read_text(encoding="utf-8")
        report = closing_odds_probe.probe_csv(str(source))
        assert report["closing_available"] is True
        assert report["closing_odds_usable"] is True
        assert report["h2h_closing_available"] == "complete"
        assert report["h2h_closing_validated"] == "complete"
        assert report["h2h_home_closing_available"] is True
        assert report["h2h_draw_closing_available"] is True
        assert report["h2h_away_closing_available"] is True
        assert report["total_closing_available"] == "complete"
        assert report["column_profiles"]["C_LTH"]["verdict"] == "decimal_odds_plausible"
        assert report["recommended_mapping"]["h2h_home"] == "C_LTH"
        assert report["recommended_mapping"]["total_over"] == "PCO"

        partial_source = root / "partial_matches.csv"
        write_csv(
            partial_source,
            ["Date", "HomeTeam", "AwayTeam", "C_LTH", "C_LTA"],
            [{"Date": "2024-01-01", "HomeTeam": "A", "AwayTeam": "B", "C_LTH": "1.9", "C_LTA": "4.2"}],
        )
        partial = closing_odds_probe.probe_csv(str(partial_source))
        assert partial["closing_available"] is True
        assert partial["h2h_closing_available"] == "partial"
        assert partial["h2h_closing_validated"] == "partial"
        assert partial["h2h_home_closing_available"] is True
        assert partial["h2h_away_closing_available"] is True
        assert partial["h2h_draw_closing_available"] is False
        assert partial["total_closing_available"] == "none"

        binary_source = root / "binary_matches.csv"
        write_csv(
            binary_source,
            ["Date", "HomeTeam", "AwayTeam", "C_LTH"],
            [{"Date": f"2024-01-{day:02d}", "HomeTeam": "A", "AwayTeam": "B", "C_LTH": str(day % 2)} for day in range(1, 12)],
        )
        binary = closing_odds_probe.probe_csv(str(binary_source), profile_columns=["C_LTH"])
        assert binary["column_profiles"]["C_LTH"]["verdict"] == "numeric_but_not_odds"
        assert binary["closing_odds_usable"] is False
        assert "C_LTH" in binary["rejected_closing_columns"]
        assert "h2h_home" not in binary["recommended_mapping"]

        text_source = root / "text_matches.csv"
        write_csv(
            text_source,
            ["Date", "HomeTeam", "AwayTeam", "C_LTH"],
            [{"Date": "2024-01-01", "HomeTeam": "A", "AwayTeam": "B", "C_LTH": "home_close_code"}],
        )
        text_report = closing_odds_probe.probe_csv(str(text_source), profile_columns=["C_LTH"])
        assert text_report["column_profiles"]["C_LTH"]["verdict"] == "text_or_code"

        empty_source = root / "empty_matches.csv"
        write_csv(
            empty_source,
            ["Date", "HomeTeam", "AwayTeam", "C_LTH"],
            [
                {"Date": f"2024-02-{day:02d}", "HomeTeam": "A", "AwayTeam": "B", "C_LTH": "2.0" if day == 1 else ""}
                for day in range(1, 21)
            ],
        )
        empty_report = closing_odds_probe.probe_csv(str(empty_source), profile_columns=["C_LTH"])
        assert empty_report["column_profiles"]["C_LTH"]["verdict"] == "mostly_empty"

        no_closing = root / "no_closing.csv"
        write_csv(no_closing, ["Date", "HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"], [{"Date": "2024-01-01", "HomeTeam": "A", "AwayTeam": "B", "B365H": "2.0", "B365D": "3.2", "B365A": "4.0"}])
        absent = closing_odds_probe.probe_csv(str(no_closing))
        assert absent["closing_available"] is False
        assert absent["closing_odds_usable"] is False
        assert absent["h2h_closing_available"] == "none"

        out_json = root / "reports" / "closing_odds_probe.json"
        out_html = root / "reports" / "closing_odds_probe.html"
        closing_odds_probe.write_json(report, str(out_json))
        closing_odds_probe.write_html(report, str(out_html))
        assert out_json.exists()
        assert out_html.exists()
        assert "Closing Odds Probe" in out_html.read_text(encoding="utf-8")
        assert source.read_text(encoding="utf-8") == before

    print("test_closing_odds_probe ok")


if __name__ == "__main__":
    main()
