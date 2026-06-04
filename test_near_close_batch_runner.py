import tempfile
from pathlib import Path

import near_close_batch_runner
import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="J League", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        sport_map = root / "config" / "sport_key_map.example.json"
        sport_map.parent.mkdir(parents=True, exist_ok=True)
        sport_map.write_text('{"J League":"soccer_japan_j_league"}', encoding="utf-8")
        report = near_close_batch_runner.run_batch(str(ledger), sport_map=str(sport_map), output_dir=str(root / "reports"), dry_run=True)
        assert report["pending_total"] == 1
        assert report["commands"]
        assert report["network_allowed"] is False
        out = root / "reports" / "near_batch.json"
        html = root / "reports" / "near_batch.html"
        near_close_batch_runner.write_json(report, str(out))
        near_close_batch_runner.write_html(report, str(html))
        assert out.exists() and html.exists()
    print("test_near_close_batch_runner ok")


if __name__ == "__main__":
    main()
