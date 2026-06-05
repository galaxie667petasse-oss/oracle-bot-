import tempfile
from pathlib import Path

from near_close_window_planner import build_window_plan, write_html, write_json
from shadow_ledger import add_shadow_entry


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="J League",
            home_team="A",
            away_team="B",
            market_type="h2h",
            side="home",
            taken_odds="2.10",
            bookmaker="Book",
            notes="source_event_id=123; kickoff_time=2026-06-05T20:00:00",
        )
        rows = build_window_plan(str(ledger), now="2026-06-05T18:30:00", hours_before=2)
        assert rows["due_now_count"] == 1
        item = rows["observations"][0]
        assert item["near_close_status"] == "due_now"
        assert "--fixture-id 123" in item["recommended_command"]

        overdue = build_window_plan(str(ledger), now="2026-06-05T21:00:00", hours_before=2)
        assert overdue["status_counts"]["overdue"] == 1

        output = root / "reports" / "near_close_window_plan.json"
        html = root / "reports" / "near_close_window_plan.html"
        write_json(rows, str(output))
        write_html(rows, str(html))
        assert output.exists() and html.exists()

    print("test_near_close_window_planner ok")


if __name__ == "__main__":
    main()
