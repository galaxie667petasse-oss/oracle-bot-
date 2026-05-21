import argparse
import csv
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backtest_evaluator import all_settled_records, pricing_records
from pricing import expected_value, fair_odds, implied_probability
from recency import period_bucket
from segment_analysis import h2h_side, odds_bucket


FEATURE_COLUMNS = [
    "date",
    "year",
    "period_bucket",
    "market_type",
    "pari",
    "result",
    "target_win",
    "odds",
    "odds_bucket",
    "implied_probability",
    "no_vig_probability",
    "market_margin",
    "fair_odds_market",
    "ev_market_baseline",
    "home_elo",
    "away_elo",
    "elo_diff",
    "elo_abs_diff",
    "elo_bucket",
    "form3_home",
    "form3_away",
    "form3_diff",
    "form5_home",
    "form5_away",
    "form5_diff",
    "is_h2h",
    "is_draw",
    "is_total",
    "is_favorite",
    "is_outsider",
    "is_low_odds",
    "is_mid_odds",
    "is_high_odds",
    "is_very_high_odds",
    "is_home_pick",
    "is_away_pick",
    "is_over",
    "is_under",
    "competition",
]


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _rounded(value: Any, digits: int = 6) -> Optional[float]:
    number = _num(value)
    if number is None:
        return None
    return round(number, digits)


def _date_key(record: Dict[str, Any]) -> str:
    return str(record.get("date_key") or record.get("date") or "")


def _year(date_key: str) -> Optional[int]:
    if len(date_key) < 4:
        return None
    try:
        return int(date_key[:4])
    except ValueError:
        return None


def _record_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    odds = round(_num(record.get("odds")) or 0.0, 4)
    return (
        _date_key(record),
        record.get("home"),
        record.get("away"),
        record.get("market_type"),
        record.get("pari"),
        odds,
    )


def _total_side(record: Dict[str, Any]) -> Optional[str]:
    if record.get("market_type") != "total":
        return None
    pari = str(record.get("pari") or "").lower()
    if "plus" in pari or "over" in pari or ">2.5" in pari:
        return "over"
    if "moins" in pari or "under" in pari or "<2.5" in pari:
        return "under"
    return None


def _diff(left: Any, right: Any) -> Optional[float]:
    left_number = _num(left)
    right_number = _num(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _elo_diff(record: Dict[str, Any]) -> Optional[float]:
    existing = _num(record.get("elo_diff"))
    if existing is not None:
        return existing
    return _diff(record.get("home_elo"), record.get("away_elo"))


def _elo_bucket(diff: Optional[float]) -> str:
    if diff is None:
        return ""
    if diff <= -120:
        return "elo_away_fort"
    if diff <= -40:
        return "elo_away_modere"
    if diff < 40:
        return "elo_equilibre"
    if diff < 120:
        return "elo_home_modere"
    return "elo_home_fort"


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    return value


def _split_name(date_key: str) -> str:
    if "2015-01-01" <= date_key <= "2022-12-31":
        return "train"
    if "2023-01-01" <= date_key <= "2023-12-31":
        return "validation"
    if date_key >= "2024-01-01":
        return "test"
    return "hors_split"


def _pricing_value(record: Dict[str, Any], key: str) -> Optional[float]:
    return _rounded(record.get(key))


def _complete_pricing(record: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(record)
    odds = _num(out.get("odds"))
    if odds is None:
        return out
    if _pricing_value(out, "implied_probability") is None:
        out["implied_probability"] = implied_probability(odds)
    no_vig = _pricing_value(out, "no_vig_probability")
    if no_vig is not None:
        if _pricing_value(out, "fair_odds_market") is None:
            out["fair_odds_market"] = fair_odds(no_vig)
        if _pricing_value(out, "ev_market_baseline") is None:
            out["ev_market_baseline"] = expected_value(no_vig, odds)
    return out


def build_feature_rows(db: Dict[str, Any], modern_from: str = "2015-01-01") -> List[Dict[str, Any]]:
    records = [
        record for record in all_settled_records(db)
        if record.get("result") in ("win", "loss") and _date_key(record) >= modern_from
    ]
    priced_records, _instances = pricing_records(records)
    priced_by_key = {_record_key(record): record for record in priced_records}

    rows: List[Dict[str, Any]] = []
    for original in records:
        record = _complete_pricing(priced_by_key.get(_record_key(original), original))
        date_key = _date_key(record)
        year = _year(date_key)
        odds = _num(record.get("odds"))
        bucket = odds_bucket(odds) if odds is not None else ""
        market_type = str(record.get("market_type") or "")
        side = h2h_side(record)
        total_side = _total_side(record)
        elo_diff = _elo_diff(record)
        form3_diff = _diff(record.get("form3_home"), record.get("form3_away"))
        form5_diff = _diff(record.get("form5_home"), record.get("form5_away"))

        rows.append({
            "date": date_key,
            "year": year,
            "period_bucket": record.get("period_bucket") or period_bucket(date_key),
            "market_type": market_type,
            "pari": record.get("pari") or "",
            "result": record.get("result") or "",
            "target_win": 1 if record.get("result") == "win" else 0,
            "odds": _rounded(odds, 4),
            "odds_bucket": bucket,
            "implied_probability": _pricing_value(record, "implied_probability"),
            "no_vig_probability": _pricing_value(record, "no_vig_probability"),
            "market_margin": _pricing_value(record, "market_margin"),
            "fair_odds_market": _pricing_value(record, "fair_odds_market"),
            "ev_market_baseline": _pricing_value(record, "ev_market_baseline"),
            "home_elo": _rounded(record.get("home_elo"), 3),
            "away_elo": _rounded(record.get("away_elo"), 3),
            "elo_diff": _rounded(elo_diff, 3),
            "elo_abs_diff": _rounded(abs(elo_diff), 3) if elo_diff is not None else None,
            "elo_bucket": _elo_bucket(elo_diff),
            "form3_home": _rounded(record.get("form3_home"), 3),
            "form3_away": _rounded(record.get("form3_away"), 3),
            "form3_diff": _rounded(form3_diff, 3),
            "form5_home": _rounded(record.get("form5_home"), 3),
            "form5_away": _rounded(record.get("form5_away"), 3),
            "form5_diff": _rounded(form5_diff, 3),
            "is_h2h": 1 if market_type == "h2h" else 0,
            "is_draw": 1 if market_type == "draw" else 0,
            "is_total": 1 if market_type == "total" else 0,
            "is_favorite": 1 if odds is not None and odds < 2.0 else 0,
            "is_outsider": 1 if odds is not None and odds >= 3.0 else 0,
            "is_low_odds": 1 if bucket == "low" else 0,
            "is_mid_odds": 1 if bucket == "mid" else 0,
            "is_high_odds": 1 if bucket == "high" else 0,
            "is_very_high_odds": 1 if bucket == "very_high" else 0,
            "is_home_pick": 1 if side == "home" else 0,
            "is_away_pick": 1 if side == "away" else 0,
            "is_over": 1 if total_side == "over" else 0,
            "is_under": 1 if total_side == "under" else 0,
            "competition": record.get("competition") or "",
        })
    return rows


def write_features(rows: Iterable[Dict[str, Any]], output_path: str) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in FEATURE_COLUMNS})


def summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    distribution = {"train": 0, "validation": 0, "test": 0, "hors_split": 0}
    by_market: Dict[str, int] = {}
    pricing_complete = 0
    for row in rows:
        distribution[_split_name(str(row.get("date") or ""))] += 1
        market = str(row.get("market_type") or "inconnu")
        by_market[market] = by_market.get(market, 0) + 1
        if row.get("no_vig_probability") not in (None, ""):
            pricing_complete += 1
    return {
        "rows": len(rows),
        "distribution": distribution,
        "by_market": by_market,
        "pricing_complete": pricing_complete,
    }


def print_summary(summary: Dict[str, Any], output_path: str) -> None:
    print("Resume feature matrix Oracle Bot")
    print(f"- Fichier ecrit: {output_path}")
    print(f"- Lignes exportees: {summary.get('rows', 0)}")
    print(f"- Lignes avec probabilite no-vig: {summary.get('pricing_complete', 0)}")
    print("- Distribution temporelle:")
    distribution = summary.get("distribution", {})
    print(f"  - train 2015-2022: {distribution.get('train', 0)}")
    print(f"  - validation 2023: {distribution.get('validation', 0)}")
    print(f"  - test 2024+: {distribution.get('test', 0)}")
    if distribution.get("hors_split", 0):
        print(f"  - hors split: {distribution.get('hors_split', 0)}")
    print("- Distribution par marche:")
    for market, count in sorted((summary.get("by_market") or {}).items()):
        print(f"  - {market}: {count}")
    print("- Note: la memoire n'a pas ete modifiee.")


def _load_db_local_only() -> Dict[str, Any]:
    os.environ["DATABASE_URL"] = ""
    from store import load_db
    import persistent_memory

    persistent_memory.DATABASE_URL = ""

    return load_db()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit une matrice de features locale sans modifier la memoire.")
    parser.add_argument("--output", required=True, help="Chemin CSV de sortie, ex: data/features_modern.csv")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    db = _load_db_local_only()
    rows = build_feature_rows(db)
    write_features(rows, args.output)
    print_summary(summarize_rows(rows), args.output)


if __name__ == "__main__":
    main()
