import tempfile
from pathlib import Path

import the_odds_active_sports as active


def main():
    fixture = "tests/fixtures/the_odds_active_sports.json"
    payload = active.read_fixture(fixture)
    report = active.build_report(payload, group="Soccer")
    assert report["active_count"] == 3
    assert "soccer_japan_j_league" in report["sport_keys"]
    assert all(row["group"] == "Soccer" for row in report["sports"])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "reports" / "active.json"
        html = root / "reports" / "active.html"
        active.write_json(report, str(output))
        active.write_html(report, str(html))
        assert output.exists() and html.exists()
        assert active.main(["--dry-run"]) == 0
        assert active.main(["--from-fixture", fixture, "--group", "Soccer", "--output", str(output)]) == 0
    print("test_the_odds_active_sports ok")


if __name__ == "__main__":
    main()
