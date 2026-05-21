import argparse
import csv
import math
import os
from itertools import groupby
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backtest_evaluator import all_settled_records, pricing_records
from pricing import expected_value, fair_odds, implied_probability
from recency import period_bucket
from segment_analysis import h2h_side, odds_bucket
from xgabora_dataset_import import DATE_COLUMNS, SCORE_AWAY_COLUMNS, SCORE_HOME_COLUMNS, _value, parse_date, parse_int, xgabora_match_stats


POST_MATCH_FEATURES = [
    "home_shots",
    "away_shots",
    "shots_diff",
    "home_target",
    "away_target",
    "target_diff",
    "total_shots",
    "total_target",
    "home_corners",
    "away_corners",
    "corners_diff",
    "total_corners",
    "home_yellow",
    "away_yellow",
    "cards_diff",
    "home_red",
    "away_red",
    "red_card_any",
    "ht_home",
    "ht_away",
    "ht_total_goals",
    "ft_total_goals",
    "second_half_goals",
    "home_clean_sheet",
    "away_clean_sheet",
    "both_teams_scored",
    "over_2_5_result",
    "under_2_5_result",
    "attacking_pressure_home",
    "attacking_pressure_away",
    "attacking_pressure_diff",
    "shot_accuracy_home",
    "shot_accuracy_away",
    "shot_accuracy_diff",
    "tempo_proxy",
    "discipline_risk",
]

ROLLING_FEATURES = [
    "home_team_goals_for_avg5",
    "home_team_goals_against_avg5",
    "away_team_goals_for_avg5",
    "away_team_goals_against_avg5",
    "home_team_shots_avg5",
    "away_team_shots_avg5",
    "home_team_target_avg5",
    "away_team_target_avg5",
    "home_team_corners_avg5",
    "away_team_corners_avg5",
    "home_team_btts_rate5",
    "away_team_btts_rate5",
    "home_team_over25_rate5",
    "away_team_over25_rate5",
]


FEATURE_COLUMNS = [
    "date",
    "year",
    "period_bucket",
    "home",
    "away",
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
    *POST_MATCH_FEATURES,
    *ROLLING_FEATURES,
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


def _sum_optional(*values: Any) -> Optional[float]:
    numbers = [_num(value) for value in values]
    if any(value is None for value in numbers):
        return None
    return sum(float(value) for value in numbers)


def _safe_ratio(numerator: Any, denominator: Any) -> Optional[float]:
    num = _num(numerator)
    den = _num(denominator)
    if num is None or den is None or den == 0:
        return None
    return num / den


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


def match_key_from_values(date_key: Any, home: Any, away: Any) -> Tuple[str, str, str]:
    return (
        str(date_key or ""),
        str(home or "").strip().lower(),
        str(away or "").strip().lower(),
    )


def _match_key(record: Dict[str, Any]) -> Tuple[str, str, str]:
    return match_key_from_values(_date_key(record), record.get("home"), record.get("away"))


def _score_goals(record: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
    score = str(record.get("score") or "").strip()
    if "-" in score:
        left, right = score.split("-", 1)
        try:
            return int(float(left.strip())), int(float(right.strip()))
        except ValueError:
            pass
    ft_total = _num(record.get("ft_total_goals"))
    if ft_total is not None:
        return None, None
    return None, None


def _auto_matches_csv_path() -> Optional[Path]:
    for candidate in (Path("data/MATCHES.csv"), Path("data/Matches.csv")):
        if candidate.exists():
            return candidate
    return None


def load_match_csv_context(csv_path: Optional[str] = None) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    path = Path(csv_path) if csv_path else _auto_matches_csv_path()
    if not path or not path.exists():
        return {}
    context: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            date_key = parse_date(_value(row, *DATE_COLUMNS))
            home = _value(row, "HomeTeam")
            away = _value(row, "AwayTeam")
            home_goals = parse_int(_value(row, *SCORE_HOME_COLUMNS))
            away_goals = parse_int(_value(row, *SCORE_AWAY_COLUMNS))
            if not date_key or not home or not away or home_goals is None or away_goals is None:
                continue
            stats = xgabora_match_stats(row, home_goals, away_goals)
            stats.update({
                "score": f"{home_goals}-{away_goals}",
                "home": home,
                "away": away,
            })
            context[match_key_from_values(date_key, home, away)] = stats
    return context


def _merge_match_context(record: Dict[str, Any], match_context: Dict[Tuple[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(record)
    context = match_context.get(_match_key(record)) or {}
    for key, value in context.items():
        if out.get(key) in (None, "") and value is not None:
            out[key] = value
    return out


def _post_match_fields(record: Dict[str, Any]) -> Dict[str, Optional[float]]:
    fields = {key: _rounded(record.get(key), 6) for key in POST_MATCH_FEATURES}
    home_shots = _num(record.get("home_shots"))
    away_shots = _num(record.get("away_shots"))
    home_target = _num(record.get("home_target"))
    away_target = _num(record.get("away_target"))
    total_shots = _num(record.get("total_shots"))
    total_corners = _num(record.get("total_corners"))
    home_yellow = _num(record.get("home_yellow"))
    away_yellow = _num(record.get("away_yellow"))
    home_red = _num(record.get("home_red"))
    away_red = _num(record.get("away_red"))
    pressure_home = _sum_optional(home_shots, 2 * home_target if home_target is not None else None)
    pressure_away = _sum_optional(away_shots, 2 * away_target if away_target is not None else None)
    fields["attacking_pressure_home"] = _rounded(pressure_home)
    fields["attacking_pressure_away"] = _rounded(pressure_away)
    fields["attacking_pressure_diff"] = _rounded(_diff(pressure_home, pressure_away))
    fields["shot_accuracy_home"] = _rounded(_safe_ratio(home_target, home_shots))
    fields["shot_accuracy_away"] = _rounded(_safe_ratio(away_target, away_shots))
    fields["shot_accuracy_diff"] = _rounded(_diff(fields["shot_accuracy_home"], fields["shot_accuracy_away"]))
    fields["tempo_proxy"] = _rounded(_sum_optional(total_shots, total_corners))
    total_yellows = _sum_optional(home_yellow, away_yellow)
    total_reds = _sum_optional(home_red, away_red)
    fields["discipline_risk"] = _rounded(_sum_optional(total_yellows, 2 * total_reds if total_reds is not None else None))
    return fields


def _avg_last(history: List[Dict[str, Any]], key: str, limit: int = 5) -> Optional[float]:
    values = [_num(item.get(key)) for item in history[-limit:]]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _unique_match_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matches: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for record in records:
        key = _match_key(record)
        if not key[0] or not key[1] or not key[2]:
            continue
        if key not in matches:
            matches[key] = record
    return sorted(matches.values(), key=lambda record: (_date_key(record), str(record.get("home") or ""), str(record.get("away") or "")))


def rolling_feature_context(records: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Optional[float]]]:
    history: Dict[str, List[Dict[str, Any]]] = {}
    context: Dict[Tuple[str, str, str], Dict[str, Optional[float]]] = {}
    matches = _unique_match_records(records)

    for date_key, day_iter in groupby(matches, key=_date_key):
        day_matches = list(day_iter)
        for match in day_matches:
            home = str(match.get("home") or "")
            away = str(match.get("away") or "")
            home_history = history.get(home, [])
            away_history = history.get(away, [])
            context[_match_key(match)] = {
                "home_team_goals_for_avg5": _avg_last(home_history, "goals_for"),
                "home_team_goals_against_avg5": _avg_last(home_history, "goals_against"),
                "away_team_goals_for_avg5": _avg_last(away_history, "goals_for"),
                "away_team_goals_against_avg5": _avg_last(away_history, "goals_against"),
                "home_team_shots_avg5": _avg_last(home_history, "shots"),
                "away_team_shots_avg5": _avg_last(away_history, "shots"),
                "home_team_target_avg5": _avg_last(home_history, "target"),
                "away_team_target_avg5": _avg_last(away_history, "target"),
                "home_team_corners_avg5": _avg_last(home_history, "corners"),
                "away_team_corners_avg5": _avg_last(away_history, "corners"),
                "home_team_btts_rate5": _avg_last(home_history, "btts"),
                "away_team_btts_rate5": _avg_last(away_history, "btts"),
                "home_team_over25_rate5": _avg_last(home_history, "over25"),
                "away_team_over25_rate5": _avg_last(away_history, "over25"),
            }

        for match in day_matches:
            home_goals, away_goals = _score_goals(match)
            if home_goals is None or away_goals is None:
                continue
            home = str(match.get("home") or "")
            away = str(match.get("away") or "")
            total_goals = home_goals + away_goals
            btts = 1 if home_goals > 0 and away_goals > 0 else 0
            over25 = 1 if total_goals >= 3 else 0
            history.setdefault(home, []).append({
                "goals_for": home_goals,
                "goals_against": away_goals,
                "shots": _num(match.get("home_shots")),
                "target": _num(match.get("home_target")),
                "corners": _num(match.get("home_corners")),
                "btts": btts,
                "over25": over25,
            })
            history.setdefault(away, []).append({
                "goals_for": away_goals,
                "goals_against": home_goals,
                "shots": _num(match.get("away_shots")),
                "target": _num(match.get("away_target")),
                "corners": _num(match.get("away_corners")),
                "btts": btts,
                "over25": over25,
            })
    return context


def build_feature_rows(db: Dict[str, Any], modern_from: str = "2015-01-01", matches_csv: Optional[str] = None) -> List[Dict[str, Any]]:
    raw_records = [
        record for record in all_settled_records(db)
        if record.get("result") in ("win", "loss")
    ]
    match_context = load_match_csv_context(matches_csv)
    records = [_merge_match_context(record, match_context) for record in raw_records]
    priced_records, _instances = pricing_records(records)
    priced_by_key = {_record_key(record): record for record in priced_records}
    rolling_context = rolling_feature_context(records)

    rows: List[Dict[str, Any]] = []
    for original in records:
        if _date_key(original) < modern_from:
            continue
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
        post_match = _post_match_fields(record)
        rolling = {key: _rounded(value) for key, value in (rolling_context.get(_match_key(record)) or {}).items()}

        rows.append({
            "date": date_key,
            "year": year,
            "period_bucket": record.get("period_bucket") or period_bucket(date_key),
            "home": record.get("home") or "",
            "away": record.get("away") or "",
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
            **post_match,
            **rolling,
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
    post_match_complete = 0
    rolling_complete = 0
    for row in rows:
        distribution[_split_name(str(row.get("date") or ""))] += 1
        market = str(row.get("market_type") or "inconnu")
        by_market[market] = by_market.get(market, 0) + 1
        if row.get("no_vig_probability") not in (None, ""):
            pricing_complete += 1
        if any(row.get(column) not in (None, "") for column in POST_MATCH_FEATURES):
            post_match_complete += 1
        if any(row.get(column) not in (None, "") for column in ROLLING_FEATURES):
            rolling_complete += 1
    return {
        "rows": len(rows),
        "distribution": distribution,
        "by_market": by_market,
        "pricing_complete": pricing_complete,
        "post_match_complete": post_match_complete,
        "rolling_complete": rolling_complete,
    }


def print_summary(summary: Dict[str, Any], output_path: str) -> None:
    print("Resume feature matrix Oracle Bot")
    print(f"- Fichier ecrit: {output_path}")
    print(f"- Lignes exportees: {summary.get('rows', 0)}")
    print(f"- Lignes avec probabilite no-vig: {summary.get('pricing_complete', 0)}")
    print(f"- Lignes avec stats post-match: {summary.get('post_match_complete', 0)}")
    print(f"- Lignes avec rolling pre-match: {summary.get('rolling_complete', 0)}")
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
    parser.add_argument("--matches-csv", default=None, help="CSV MATCHES optionnel pour enrichissement local en lecture seule")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    db = _load_db_local_only()
    rows = build_feature_rows(db, matches_csv=args.matches_csv)
    write_features(rows, args.output)
    print_summary(summarize_rows(rows), args.output)


if __name__ == "__main__":
    main()
