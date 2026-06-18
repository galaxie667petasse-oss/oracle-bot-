import csv
import tempfile
from pathlib import Path

import api_football_near_close_apply as near_apply


LEDGER_FIELDS = [
    "shadow_id",
    "match_date",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "side",
    "taken_odds",
    "bookmaker",
    "status",
    "result",
    "closing_odds",
    "closing_source",
    "clv_percent",
    "clv_available",
    "notes",
]

NEAR_FIELDS = [
    "snapshot_id",
    "captured_at",
    "source",
    "source_event_id",
    "league",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "bookmaker",
    "market_type",
    "side",
    "odds",
]


def write_csv(path: Path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def read_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def base_row(shadow_id: str, event_id: str, bookmaker: str, taken: str = "2.00"):
    return {
        "shadow_id": shadow_id,
        "match_date": "2026-06-17",
        "league": "Test League",
        "home_team": "A",
        "away_team": "B",
        "market_type": "h2h",
        "side": "home",
        "taken_odds": taken,
        "bookmaker": bookmaker,
        "status": "observation",
        "result": "unknown",
        "notes": f"source=api_football; source_event_id={event_id}",
    }


def near_row(event_id: str, bookmaker: str, odds: str):
    return {
        "snapshot_id": f"odds_{event_id}_{bookmaker}",
        "captured_at": "2026-06-17T21:20:43",
        "source": "api_football",
        "source_event_id": event_id,
        "league": "Test League",
        "match_date": "2026-06-17",
        "kickoff_time": "2026-06-17T23:00:00+00:00",
        "home_team": "A",
        "away_team": "B",
        "bookmaker": bookmaker,
        "market_type": "h2h",
        "side": "home",
        "odds": odds,
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger = root / "reports" / "shadow_ledger.csv"
        near = root / "reports" / "near.csv"
        write_csv(
            ledger,
            LEDGER_FIELDS,
            [
                base_row("sh_exact", "100", "10Bet"),
                base_row("sh_cross", "200", "10Bet", taken="2.00"),
                base_row("sh_ambiguous", "300", "10Bet", taken="2.00"),
                base_row("sh_dry", "400", "10Bet", taken="2.00"),
            ],
        )
        write_csv(
            near,
            NEAR_FIELDS,
            [
                near_row("100", "10Bet", "2.20"),
                near_row("100", "Other", "2.30"),
                near_row("200", "Other", "1.90"),
                near_row("300", "OtherA", "1.90"),
                near_row("300", "OtherB", "1.95"),
                near_row("400", "10Bet", "2.10"),
            ],
        )
        before = ledger.read_text(encoding="utf-8")

        dry = near_apply.apply_near_close(str(ledger), str(near), shadow_id="sh_dry", apply=False)
        assert dry["would_update"] == 1
        assert dry["updated"] == 0
        assert dry["closing_quality"] == "same_bookmaker"
        assert ledger.read_text(encoding="utf-8") == before

        exact = near_apply.apply_near_close(str(ledger), str(near), shadow_id="sh_exact", apply=True)
        assert exact["updated"] == 1
        assert exact["closing_quality"] == "same_bookmaker"
        assert exact["clv"] == 0.1
        rows = {row["shadow_id"]: row for row in read_rows(ledger)}
        assert rows["sh_exact"]["closing_odds"] == "2.2"
        assert rows["sh_exact"]["closing_bookmaker"] == "10Bet"
        assert rows["sh_exact"]["closing_source"] == "api_football_near_close"
        assert rows["sh_exact"]["closing_status"] == "captured"
        assert rows["sh_exact"]["clv"] == "0.1"
        assert rows["sh_exact"]["clv_pct"] == "10.0"
        assert rows["sh_exact"]["clv_available"] == "True"

        cross = near_apply.apply_near_close(str(ledger), str(near), shadow_id="sh_cross", apply=True)
        assert cross["updated"] == 1
        assert cross["closing_quality"] == "cross_bookmaker_same_market"
        rows = {row["shadow_id"]: row for row in read_rows(ledger)}
        assert rows["sh_cross"]["closing_bookmaker"] == "Other"
        assert rows["sh_cross"]["clv"] == "-0.05"
        assert rows["sh_cross"]["clv_pct"] == "-5.0"

        ambiguous_before = ledger.read_text(encoding="utf-8")
        ambiguous = near_apply.apply_near_close(str(ledger), str(near), shadow_id="sh_ambiguous", apply=True)
        assert ambiguous["updated"] == 0
        assert ambiguous["closing_status"] == "ambiguous"
        assert ledger.read_text(encoding="utf-8") == ambiguous_before

        single_ledger = root / "reports" / "single_ledger.csv"
        write_csv(single_ledger, LEDGER_FIELDS, [base_row("sh_single", "100", "10Bet")])
        no_shadow_id = near_apply.apply_near_close(str(single_ledger), str(near), apply=False)
        assert no_shadow_id["ledger_matches"] >= 1
        assert no_shadow_id["closing_quality"] == "same_bookmaker"

    print("test_api_football_near_close_apply ok")


if __name__ == "__main__":
    main()
