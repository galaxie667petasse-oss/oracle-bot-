import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from calibration import build_calibration, league_bucket, segment_adjustment_for_pick
from segment_analysis import odds_bucket
from recency import PERIOD_ORDER, date_min_max, record_period


STRATEGIES = (
    "baseline_all",
    "no_blocked_segments",
    "totals_only",
    "totals_low",
    "totals_low_mid",
    "strict_oracle",
    "favorites_only",
    "avoid_outsiders",
    "modern_weighted_oracle",
    "recent_only_oracle",
)

STRATEGY_LABELS = {
    "baseline_all": "Baseline marché brut",
    "no_blocked_segments": "Sans segments bloqués",
    "totals_only": "Totals seulement",
    "totals_low": "Totals low",
    "totals_low_mid": "Totals low/mid",
    "strict_oracle": "Oracle strict",
    "favorites_only": "Favoris seulement",
    "avoid_outsiders": "Sans outsiders",
    "modern_weighted_oracle": "Oracle moderne pondéré",
    "recent_only_oracle": "Oracle récent seulement",
}

PRESETS = {
    "modern": {
        "train_from": "2015-01-01",
        "train_to": "2022-12-31",
        "validation_from": "2023-01-01",
        "validation_to": "2023-12-31",
        "test_from": "2024-01-01",
        "test_to": "",
    },
    "recent": {
        "train_from": "2020-01-01",
        "train_to": "2023-12-31",
        "validation_from": "",
        "validation_to": "",
        "test_from": "2024-01-01",
        "test_to": "",
    },
    "long": {
        "train_from": "2012-01-01",
        "train_to": "2022-12-31",
        "validation_from": "",
        "validation_to": "",
        "test_from": "2023-01-01",
        "test_to": "",
    },
    "archive-check": {
        "train_from": "2000-01-01",
        "train_to": "2010-12-31",
        "validation_from": "",
        "validation_to": "",
        "test_from": "2011-01-01",
        "test_to": "2014-12-31",
    },
}


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _date_key(record: Dict[str, Any]) -> str:
    return str(record.get("date_key") or record.get("date") or "")


def _record_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    odds = round(_num(record.get("odds"), 0.0), 4)
    return (
        _date_key(record),
        record.get("home"),
        record.get("away"),
        record.get("market_type"),
        record.get("pari"),
        odds,
    )


def unit_profit(record: Dict[str, Any]) -> float:
    odds = _num(record.get("odds"), 1.0)
    return odds - 1.0 if record.get("result") == "win" else -1.0


def all_settled_records(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    for scan in db.get("scans", {}).values():
        for record in (scan.get("picks", []) or []) + (scan.get("candidates", []) or []):
            if record.get("result") not in ("win", "loss"):
                continue
            key = _record_key(record)
            if key in seen:
                continue
            seen.add(key)
            rows.append(deepcopy(record))
    return sorted(rows, key=lambda record: (_date_key(record), str(record.get("home", "")), str(record.get("pari", ""))))


def split_train_test(records: Iterable[Dict[str, Any]], train_to: str, test_from: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    train: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    for record in records:
        date_key = _date_key(record)
        if date_key and date_key <= train_to:
            train.append(record)
        if date_key and date_key >= test_from:
            test.append(record)
    return train, test


def in_range(record: Dict[str, Any], date_from: str = "", date_to: str = "") -> bool:
    date_key = _date_key(record)
    if not date_key:
        return False
    if date_from and date_key < date_from:
        return False
    if date_to and date_key > date_to:
        return False
    return True


def split_by_ranges(records: Iterable[Dict[str, Any]], params: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    train = [r for r in records if in_range(r, params.get("train_from", ""), params.get("train_to", ""))]
    validation = [r for r in records if params.get("validation_from") and in_range(r, params.get("validation_from", ""), params.get("validation_to", ""))]
    test = [r for r in records if in_range(r, params.get("test_from", ""), params.get("test_to", ""))]
    return train, validation, test


def resolve_params(train_to: str = "2023-12-31", test_from: str = "2024-01-01", preset: str = "") -> Dict[str, str]:
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"Preset inconnu: {preset}")
        out = dict(PRESETS[preset])
        out["preset"] = preset
        return out
    return {
        "preset": "",
        "train_from": "",
        "train_to": train_to,
        "validation_from": "",
        "validation_to": "",
        "test_from": test_from,
        "test_to": "",
    }


def db_from_records(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    db: Dict[str, Any] = {"scans": {}, "learning": {}, "calibration": {}, "segment_report": {}}
    for record in records:
        date_key = _date_key(record) or "unknown"
        scan = db["scans"].setdefault(date_key, {
            "date_key": date_key,
            "date_label": date_key,
            "mode": "backtest_train",
            "version": "BACKTEST-TRAIN",
            "picks": [],
            "candidates": [],
        })
        scan["candidates"].append(deepcopy(record))
    return db


def _group_stats(records: Iterable[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(key_fn(record)), []).append(record)
    return {key: summarize_records(group, include_groups=False) for key, group in sorted(groups.items())}


def _learning_group(records: Iterable[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, Dict[str, Any]] = {}
    for record in records:
        key = str(key_fn(record))
        stat = groups.setdefault(key, {"n": 0, "w": 0, "profit": 0.0})
        stat["n"] += 1
        stat["w"] += 1 if record.get("result") == "win" else 0
        stat["profit"] += unit_profit(record)
    for stat in groups.values():
        n = stat["n"]
        stat["profit"] = round(stat["profit"], 2)
        stat["wr"] = round(stat["w"] / n * 100, 1) if n else 0.0
        stat["roi"] = round(stat["profit"] / n * 100, 1) if n else 0.0
    return groups


def max_drawdown(records: Iterable[Dict[str, Any]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for record in sorted(records, key=lambda item: _date_key(item)):
        cumulative += unit_profit(record)
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return round(drawdown, 2)


def summarize_records(records: Iterable[Dict[str, Any]], include_groups: bool = True) -> Dict[str, Any]:
    rows = list(records)
    n = len(rows)
    wins = sum(1 for record in rows if record.get("result") == "win")
    profit = round(sum(unit_profit(record) for record in rows), 2)
    odds_sum = sum(_num(record.get("odds"), 0.0) for record in rows)
    summary = {
        "picks": n,
        "wins": wins,
        "winrate": round(wins / n * 100, 1) if n else 0.0,
        "roi": round(profit / n * 100, 1) if n else 0.0,
        "profit": profit,
        "average_odds": round(odds_sum / n, 2) if n else 0.0,
        "max_drawdown": max_drawdown(rows),
        "warning": "échantillon faible" if n < 100 else "",
    }
    if include_groups:
        summary["by_market"] = _group_stats(rows, lambda record: record.get("market_type", "?"))
        summary["by_odds"] = _group_stats(rows, lambda record: odds_bucket(_num(record.get("odds"), 2.0)))
    return summary


def _learning_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "samples": len(records),
        "visible_samples": sum(1 for record in records if not record.get("shadow")),
        "shadow_samples": sum(1 for record in records if record.get("shadow")),
        "by_market": _learning_group(records, lambda record: record.get("market_type", "?")),
        "by_odds": _learning_group(records, lambda record: odds_bucket(_num(record.get("odds"), 2.0))),
        "by_league": _learning_group(records, lambda record: league_bucket(record.get("competition", ""))),
        "memory_backend": "backtest train local",
        "updated_at": "backtest",
    }


def build_train_context(train_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    train_db = db_from_records(train_records)
    learning = _learning_from_records(train_records)
    train_db["learning"] = learning
    train_db["calibration"] = build_calibration(train_db, learning)
    return train_db


def _blocked_by_train_segments(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    return bool(segment_adjustment_for_pick(record, train_db).get("block_top"))


def _strict_oracle(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    calibration = train_db.get("calibration", {}) or {}
    segment = segment_adjustment_for_pick(record, train_db)
    market = str(record.get("market_type") or "")
    odds = _num(record.get("odds"), 0.0)
    bucket = odds_bucket(odds)
    market_risk = (calibration.get("banned_or_penalized_markets", {}) or {}).get(market, {}) or {}
    bucket_risk = (calibration.get("banned_or_penalized_odds_buckets", {}) or {}).get(bucket, {}) or {}
    segment_positive = bool(segment.get("positive_reliable"))

    if segment.get("block_top"):
        return False
    if bucket == "very_high" and bucket_risk.get("block_top"):
        return False
    if market_risk.get("block_top") and not segment_positive:
        return False
    if bucket_risk.get("block_top") and not segment_positive:
        return False
    if market == "h2h" and odds > _num(calibration.get("max_h2h_odds_for_top"), 2.6) and not segment_positive:
        return False
    if market == "draw" and not segment_positive:
        return False

    ev = record.get("ev_pct")
    if ev is not None and _num(ev) < _num(calibration.get("min_ev_for_top"), 1.8):
        return False
    danger = record.get("danger")
    if danger is not None and _num(danger) > _num(calibration.get("max_danger_for_top"), 56):
        return False

    council_score = _num(record.get("council_score"), 0.0)
    if council_score < _num(calibration.get("min_council_score_for_top"), 7.0):
        return False
    if int(record.get("agent_rejects", 0) or 0) > 0:
        return False
    return True


def select_strategy_records(strategy: str, test_records: List[Dict[str, Any]], train_db: Dict[str, Any]) -> List[Dict[str, Any]]:
    if strategy == "baseline_all":
        return list(test_records)
    if strategy == "no_blocked_segments":
        return [record for record in test_records if not _blocked_by_train_segments(record, train_db)]
    if strategy == "totals_only":
        return [record for record in test_records if record.get("market_type") == "total"]
    if strategy == "totals_low":
        return [
            record
            for record in test_records
            if record.get("market_type") == "total" and odds_bucket(_num(record.get("odds"), 2.0)) == "low"
        ]
    if strategy == "totals_low_mid":
        return [
            record
            for record in test_records
            if record.get("market_type") == "total" and odds_bucket(_num(record.get("odds"), 2.0)) in ("low", "mid")
        ]
    if strategy == "strict_oracle":
        return [record for record in test_records if _strict_oracle(record, train_db)]
    if strategy == "favorites_only":
        return [record for record in test_records if _num(record.get("odds"), 99.0) < 2.0]
    if strategy == "avoid_outsiders":
        return [record for record in test_records if _num(record.get("odds"), 99.0) < 3.0]
    if strategy == "modern_weighted_oracle":
        return [
            record
            for record in test_records
            if record_period(record) in ("modern_2015_2019", "recent_2020_2023", "test_2024_plus") and _strict_oracle(record, train_db)
        ]
    if strategy == "recent_only_oracle":
        return [
            record
            for record in test_records
            if record_period(record) in ("recent_2020_2023", "test_2024_plus") and _strict_oracle(record, train_db)
        ]
    raise ValueError(f"Stratégie inconnue: {strategy}")


def evaluate_backtest(db: Dict[str, Any], train_to: str = "2023-12-31", test_from: str = "2024-01-01", preset: str = "") -> Dict[str, Any]:
    records = all_settled_records(db)
    params = resolve_params(train_to, test_from, preset)
    train_records, validation_records, test_records = split_by_ranges(records, params)
    train_db = build_train_context(train_records)
    strategies = {}
    for strategy in STRATEGIES:
        selected = select_strategy_records(strategy, test_records, train_db)
        summary = summarize_records(selected)
        summary["label"] = STRATEGY_LABELS[strategy]
        strategies[strategy] = summary
    positive = [name for name, stat in strategies.items() if stat["picks"] >= 100 and stat["roi"] > 0]
    return {
        "params": params,
        "all_records": len(records),
        "train": {
            "samples": len(train_records),
            "date_min": date_min_max(train_records)[0],
            "date_max": date_min_max(train_records)[1],
            "by_market": train_db.get("calibration", {}).get("by_market", {}),
            "calibration": train_db.get("calibration", {}),
            "segment_report_samples": train_db.get("segment_report", {}).get("samples", 0),
        },
        "validation": {
            "samples": len(validation_records),
            "date_min": date_min_max(validation_records)[0],
            "date_max": date_min_max(validation_records)[1],
        },
        "test": {
            "samples": len(test_records),
            "date_min": date_min_max(test_records)[0],
            "date_max": date_min_max(test_records)[1],
            "warning": "pas assez de données test" if len(test_records) < 100 else "",
            "recency_warning": "le test ne contient pas de données 2024+" if test_records and not any(record_period(r) == "test_2024_plus" for r in test_records) else "",
        },
        "strategies": strategies,
        "positive_strategies": positive,
        "conclusion": "Aucune stratégie positive robuste sur le test." if not positive else "Au moins une stratégie est positive sur le test, à confirmer hors échantillon.",
    }


def _fmt_pct(value: Any) -> str:
    return f"{_num(value):.1f}%"


def print_strategy(name: str, stat: Dict[str, Any]) -> None:
    warning = f" · {stat['warning']}" if stat.get("warning") else ""
    print(f"\n{STRATEGY_LABELS.get(name, name)}{warning}")
    print(f"- Picks: {stat['picks']}")
    print(f"- Gagnés: {stat['wins']}")
    print(f"- Winrate: {_fmt_pct(stat['winrate'])}")
    print(f"- ROI: {_fmt_pct(stat['roi'])}")
    print(f"- Profit unité: {stat['profit']}")
    print(f"- Cote moyenne: {stat['average_odds']}")
    print(f"- Max drawdown: {stat['max_drawdown']}")
    print("- Par marché:")
    for key, group in stat.get("by_market", {}).items():
        print(f"  - {key}: n={group['picks']}, ROI={_fmt_pct(group['roi'])}, profit={group['profit']}")
    print("- Par tranche de cote:")
    for key, group in stat.get("by_odds", {}).items():
        print(f"  - {key}: n={group['picks']}, ROI={_fmt_pct(group['roi'])}, profit={group['profit']}")


def print_report(report: Dict[str, Any]) -> None:
    params = report["params"]
    print("Backtest temporel Oracle Bot")
    if params.get("preset"):
        print(f"- Preset: {params['preset']}")
    print(f"- Train: {params.get('train_from') or 'début'} -> {params['train_to']}")
    if params.get("validation_from"):
        print(f"- Validation: {params['validation_from']} -> {params['validation_to']}")
    print(f"- Test: {params['test_from']} -> {params.get('test_to') or 'fin'}")
    print(f"- Records train: {report['train']['samples']} ({report['train'].get('date_min') or 'aucune'} -> {report['train'].get('date_max') or 'aucune'})")
    if report["validation"]["samples"]:
        print(f"- Records validation: {report['validation']['samples']} ({report['validation'].get('date_min')} -> {report['validation'].get('date_max')})")
    print(f"- Records test: {report['test']['samples']} ({report['test'].get('date_min') or 'aucune'} -> {report['test'].get('date_max') or 'aucune'})")
    if report["test"].get("warning"):
        print(f"Attention: {report['test']['warning']}")
    if report["test"].get("recency_warning"):
        print(f"Attention: {report['test']['recency_warning']}")
    for strategy in STRATEGIES:
        print_strategy(strategy, report["strategies"][strategy])
    print("")
    print(report["conclusion"])
    print("Rappel: le ROI test compte davantage que le ROI train, et un ROI positif faible n'est jamais une preuve définitive.")


def write_json(report: Dict[str, Any], path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON écrit: {target}")


def period_report(db: Dict[str, Any]) -> Dict[str, Any]:
    records = all_settled_records(db)
    report = {
        "by_period": _group_stats(records, lambda record: record_period(record)),
        "market_period": _group_stats(records, lambda record: f"{record.get('market_type', '?')}|{record_period(record)}"),
        "focus": {
            "total_low": _group_stats([r for r in records if r.get("market_type") == "total" and odds_bucket(_num(r.get("odds"), 2.0)) == "low"], lambda r: record_period(r)),
            "total_mid": _group_stats([r for r in records if r.get("market_type") == "total" and odds_bucket(_num(r.get("odds"), 2.0)) == "mid"], lambda r: record_period(r)),
            "h2h_very_high": _group_stats([r for r in records if r.get("market_type") == "h2h" and odds_bucket(_num(r.get("odds"), 2.0)) == "very_high"], lambda r: record_period(r)),
            "draw_high": _group_stats([r for r in records if r.get("market_type") == "draw" and odds_bucket(_num(r.get("odds"), 2.0)) == "high"], lambda r: record_period(r)),
        },
    }
    return report


def _period_conclusion(stats: Dict[str, Any]) -> str:
    recent = stats.get("recent_2020_2023") or stats.get("test_2024_plus") or {}
    modern = stats.get("modern_2015_2019") or {}
    archive = stats.get("archive_pre2012") or {}
    if recent and recent.get("picks", 0) >= 100 and recent.get("roi", 0) > 2:
        return "signal confirmé récemment"
    if archive and archive.get("picks", 0) >= 100 and archive.get("roi", 0) > 2 and not (modern.get("roi", 0) > 0 or recent.get("roi", 0) > 0):
        return "signal ancien seulement"
    if any(s.get("picks", 0) >= 100 and s.get("roi", 0) < -8 for s in stats.values()):
        return "signal négatif robuste"
    return "signal instable"


def print_period_report(report: Dict[str, Any]) -> None:
    print("Rapport par période")
    print("- ROI par période:")
    for period in PERIOD_ORDER:
        stat = report["by_period"].get(period)
        if stat:
            print(f"  - {period}: n={stat['picks']}, ROI={_fmt_pct(stat['roi'])}, profit={stat['profit']}")
    print("- Focus prudence:")
    for name, stats in report["focus"].items():
        print(f"  - {name}: {_period_conclusion(stats)}")
        for period in PERIOD_ORDER:
            stat = stats.get(period)
            if stat:
                print(f"    - {period}: n={stat['picks']}, ROI={_fmt_pct(stat['roi'])}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Backtest temporel train/test Oracle Bot sans API ni Telegram.")
    parser.add_argument("--train-to", default="2023-12-31", help="Date maximale du train, format YYYY-MM-DD")
    parser.add_argument("--test-from", default="2024-01-01", help="Date minimale du test, format YYYY-MM-DD")
    parser.add_argument("--preset", choices=sorted(PRESETS.keys()), default="", help="Preset de découpage temporel")
    parser.add_argument("--period-report", action="store_true", help="Affiche un rapport ROI par période sans backtest")
    parser.add_argument("--json", dest="json_path", default=None, help="Chemin de sortie JSON optionnel")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    from store import load_db

    db = load_db()
    if args.period_report:
        report = period_report(db)
        print_period_report(report)
        if args.json_path:
            write_json(report, args.json_path)
        return
    report = evaluate_backtest(db, args.train_to, args.test_from, args.preset)
    print_report(report)
    if args.json_path:
        write_json(report, args.json_path)


if __name__ == "__main__":
    main()
