import json
import tempfile
from pathlib import Path

import shadow_ledger
import telegram_message_formatter as formatter


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-05",
            league="EPL",
            home="Arsenal",
            away="Chelsea",
            market="h2h",
            side="home",
            taken_odds="2.10",
            bookmaker="manual",
            reason="observation shadow",
        )
        text = formatter.format_ledger_preview(str(ledger))
        assert "OBSERVATION SHADOW" in text
        assert "preuve insuffisante" in text.lower()
        assert "conseil de pari" not in text.lower()
        near = root / "reports" / "near.json"
        near.write_text(json.dumps({
            "due_now_count": 1,
            "overdue_count": 0,
            "observations": [{
                "shadow_id": "sh_1",
                "home_team": "A",
                "away_team": "B",
                "kickoff_time": "2026-06-05T18:00:00",
                "market_type": "h2h",
                "side": "away",
                "near_close_status": "due_now",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        near_text = formatter.format_near_close_preview(str(near))
        assert "NEAR-CLOSE" in near_text
        proof = root / "reports" / "proof.json"
        proof.write_text(json.dumps({"global_status": "insufficient_evidence", "sections": {"shadow": {"sample": 1}, "evidence_gate": {"global_status": "insufficient_evidence"}}}, ensure_ascii=False), encoding="utf-8")
        proof_text = formatter.format_proof_preview(str(proof))
        assert "RAPPORT DE PREUVE" in proof_text
        out = formatter.write_text(text, str(root / "reports" / "telegram_preview.md"))
        assert out.exists()
        try:
            formatter.assert_message_policy("conseil de pari")
            raise AssertionError("terme interdit non bloque")
        except ValueError:
            pass
    print("test_telegram_message_formatter ok")


if __name__ == "__main__":
    main()
