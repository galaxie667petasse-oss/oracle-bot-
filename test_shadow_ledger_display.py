import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        ledger = Path(tmp) / "reports" / "shadow_ledger.csv"
        entry = shadow_ledger.add_shadow_entry(
            str(ledger),
            match_date="2026-06-17",
            league="World Cup",
            home="Ghana",
            away="Panama",
            market="h2h",
            side="home",
            taken_odds="2.26",
            closing_odds="2.26",
            result="win",
            status="settled",
        )
        rows = shadow_ledger.read_ledger(str(ledger))
        rows[0].update({
            "shadow_id": entry["shadow_id"],
            "result_status": "win",
            "result_home_goals": "1",
            "result_away_goals": "0",
            "profit_units": "1.26",
            "settlement_status": "settled",
            "clv": "0.0",
        })
        shadow_ledger.write_ledger(rows, str(ledger))

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            shadow_ledger.print_rows(shadow_ledger.read_ledger(str(ledger)))
        text = buffer.getvalue()
        assert "Ghana - Panama" in text
        assert "h2h home" in text
        assert "cote=2.26" in text
        assert "CLV=0.0" in text
        assert "resultat=win" in text
        assert "score=1-0" in text
        assert "profit=+1.26u" in text
        assert "statut=settled" in text

    print("test_shadow_ledger_display ok")


if __name__ == "__main__":
    main()
