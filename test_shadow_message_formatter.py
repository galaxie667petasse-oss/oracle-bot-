import json
import tempfile
from pathlib import Path

import shadow_ledger
import shadow_message_formatter


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path("shadow_message_formatter.py").read_text(encoding="utf-8").lower()
        assert "import telegram" not in source
        assert "bot_app" not in source
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home", taken_odds="2.10", reason="observation shadow")
        text = shadow_message_formatter.format_ledger_messages(str(ledger))
        assert "Oracle Shadow Mode" in text
        assert "observation seulement" in text
        assert "selection activee" not in text.lower()
        out = root / "reports" / "shadow_messages_preview.txt"
        shadow_message_formatter.write_text(text, str(out))
        assert out.exists()

        report_path = root / "reports" / "shadow_clv_report.json"
        report_path.write_text(json.dumps({"signals_total": 1, "pending_closing": 1, "pending_results": 1, "clv_coverage": 0.0, "clv_mean": None, "verdict": "not_validated", "warnings": ["CLV absente"]}, ensure_ascii=False), encoding="utf-8")
        summary = shadow_message_formatter.format_summary_message(str(report_path))
        assert "not_validated" in summary
        assert "selection activee" not in summary.lower()

    print("test_shadow_message_formatter ok")


if __name__ == "__main__":
    main()
