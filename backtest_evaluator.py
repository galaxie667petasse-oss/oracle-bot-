import argparse
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from calibration import (
    blocked_segment_for_pick,
    build_calibration,
    league_bucket,
    segment_adjustment_for_pick,
    segment_matches_for_pick,
)
from segment_analysis import h2h_side, odds_bucket
from recency import PERIOD_ORDER, date_min_max, record_period


STRATEGIES = (
    "baseline_all",
    "no_blocked_segments",
    "totals_only",
    "totals_low",
    "totals_low_mid",
    "favorites_only",
    "avoid_outsiders",
    "draw_high_watchlist",
    "favorites_h2h_only",
    "oracle_relaxed",
    "oracle_balanced",
    "oracle_strict",
    "strict_oracle",
    "modern_weighted_oracle",
    "recent_only_oracle",
)

STRATEGY_LABELS = {
    "baseline_all": "Baseline marché brut",
    "no_blocked_segments": "Sans segments bloqués",
    "totals_only": "Totals seulement",
    "totals_low": "Totals low",
    "totals_low_mid": "Totals low/mid",
    "favorites_only": "Favoris seulement",
    "avoid_outsiders": "Sans outsiders",
    "draw_high_watchlist": "Watchlist draw high",
    "favorites_h2h_only": "Favoris H2H seulement",
    "oracle_relaxed": "Oracle relaxe",
    "oracle_balanced": "Oracle equilibre",
    "oracle_strict": "Oracle strict",
    "strict_oracle": "Oracle strict (compat)",
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


def _blocked_segment(record: Dict[str, Any], train_db: Dict[str, Any]) -> Dict[str, Any]:
    return blocked_segment_for_pick(record, train_db, min_n=300)


def _blocked_by_train_segments(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    return bool(_blocked_segment(record, train_db))


def _segment_positive(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    return bool(segment_adjustment_for_pick(record, train_db).get("positive_reliable"))


def _market_bucket_risk(record: Dict[str, Any], train_db: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    calibration = train_db.get("calibration", {}) or {}
    market = str(record.get("market_type") or "")
    bucket = odds_bucket(_num(record.get("odds"), 2.0))
    market_risk = (calibration.get("banned_or_penalized_markets", {}) or {}).get(market, {}) or {}
    bucket_risk = (calibration.get("banned_or_penalized_odds_buckets", {}) or {}).get(bucket, {}) or {}
    return market_risk, bucket_risk


def _is_h2h_favorite(record: Dict[str, Any]) -> bool:
    return record.get("market_type") == "h2h" and _num(record.get("odds"), 99.0) < 2.0


def _is_elo_favorable_h2h(record: Dict[str, Any]) -> bool:
    if record.get("market_type") != "h2h" or record.get("elo_diff") in (None, ""):
        return False
    side = h2h_side(record)
    diff = _num(record.get("elo_diff"), 0.0)
    return (side == "home" and diff >= 75) or (side == "away" and diff <= -75)


def _oracle_relaxed(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    odds = _num(record.get("odds"), 99.0)
    bucket = odds_bucket(odds)
    if bucket == "very_high":
        return False
    if odds >= 3.0:
        return False
    if _blocked_by_train_segments(record, train_db):
        return False
    return True


def _oracle_balanced(record: Dict[str, Any], train_db: Dict[str, Any]) -> bool:
    if not _oracle_relaxed(record, train_db):
        return False
    calibration = train_db.get("calibration", {}) or {}
    market = str(record.get("market_type") or "")
    odds = _num(record.get("odds"), 99.0)
    bucket = odds_bucket(odds)
    segment = segment_adjustment_for_pick(record, train_db)
    segment_positive = bool(segment.get("positive_reliable"))
    market_risk, bucket_risk = _market_bucket_risk(record, train_db)

    if segment.get("n", 0) >= 300 and _num(segment.get("roi"), 0.0) < -8:
        return False
    if bucket_risk.get("block_top") and not segment_positive:
        return False
    if market_risk.get("block_top") and not segment_positive:
        return False
    if market == "h2h" and odds > _num(calibration.get("max_h2h_odds_for_top"), 2.6) and not segment_positive:
        return False
    if market == "draw" and not segment_positive:
        return False
    if bucket in ("high", "very_high") and not segment_positive:
        return False
    return True


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


def _strategy_decision(strategy: str, record: Dict[str, Any], train_db: Dict[str, Any]) -> Dict[str, Any]:
    odds = _num(record.get("odds"), 99.0)
    bucket = odds_bucket(odds)
    market = record.get("market_type")
    blocked = _blocked_segment(record, train_db)
    no_segment = not bool(segment_matches_for_pick(record, train_db, min_n=100))

    def keep(reason: str = "retenu") -> Dict[str, Any]:
        return {"keep": True, "reason": reason, "blocked_segment": blocked, "no_segment": no_segment}

    def reject(reason: str) -> Dict[str, Any]:
        return {"keep": False, "reason": reason, "blocked_segment": blocked, "no_segment": no_segment}

    if strategy == "baseline_all":
        return keep()
    if strategy == "no_blocked_segments":
        if blocked:
            return reject(f"segment bloque: {blocked.get('label', blocked.get('key', 'segment'))}")
        return keep()
    if strategy == "totals_only":
        return keep() if market == "total" else reject("marche non total")
    if strategy == "totals_low":
        return keep() if market == "total" and bucket == "low" else reject("pas total low")
    if strategy == "totals_low_mid":
        return keep() if market == "total" and bucket in ("low", "mid") else reject("pas total low/mid")
    if strategy == "favorites_only":
        return keep() if odds < 2.0 else reject("cote >= 2.0")
    if strategy == "avoid_outsiders":
        return keep() if odds < 3.0 else reject("outsider cote >= 3.0")
    if strategy == "draw_high_watchlist":
        return keep("watchlist seulement") if market == "draw" and bucket == "high" else reject("pas draw high")
    if strategy == "favorites_h2h_only":
        return keep() if _is_h2h_favorite(record) else reject("pas favori h2h")
    if strategy == "oracle_relaxed":
        if _oracle_relaxed(record, train_db):
            return keep()
        if blocked:
            return reject(f"segment tres negatif: {blocked.get('label', blocked.get('key', 'segment'))}")
        if bucket == "very_high":
            return reject("very_high refuse")
        if odds >= 3.0:
            return reject("outsider fort refuse")
        return reject("regle relaxe refuse")
    if strategy == "oracle_balanced":
        if _oracle_balanced(record, train_db):
            return keep()
        if not _oracle_relaxed(record, train_db):
            return reject(_strategy_decision("oracle_relaxed", record, train_db)["reason"])
        segment = segment_adjustment_for_pick(record, train_db)
        if segment.get("n", 0) >= 300 and _num(segment.get("roi"), 0.0) < -8:
            return reject(f"segment defavorable ROI {segment.get('roi')}%")
        market_risk, bucket_risk = _market_bucket_risk(record, train_db)
        if market_risk.get("block_top"):
            return reject(f"marche bloque: {market}")
        if bucket_risk.get("block_top"):
            return reject(f"tranche bloquee: {bucket}")
        if market == "draw" and not _segment_positive(record, train_db):
            return reject("draw sans segment positif fiable")
        if bucket == "high" and not _segment_positive(record, train_db):
            return reject("high sans segment positif fiable")
        return reject("equilibre refuse")
    if strategy in ("oracle_strict", "strict_oracle"):
        return keep() if _strict_oracle(record, train_db) else reject("seuils stricts non atteints")
    if strategy == "modern_weighted_oracle":
        if record_period(record) not in ("modern_2015_2019", "recent_2020_2023", "test_2024_plus"):
            return reject("periode trop ancienne")
        return keep() if _oracle_balanced(record, train_db) else reject("oracle moderne refuse")
    if strategy == "recent_only_oracle":
        if record_period(record) not in ("recent_2020_2023", "test_2024_plus"):
            return reject("periode non recente")
        return keep() if _oracle_balanced(record, train_db) else reject("oracle recent refuse")
    raise ValueError(f"Strategie inconnue: {strategy}")


def select_strategy_records(strategy: str, test_records: List[Dict[str, Any]], train_db: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [record for record in test_records if _strategy_decision(strategy, record, train_db)["keep"]]
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


def debug_strategy_report(test_records: List[Dict[str, Any]], train_db: Dict[str, Any]) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    blocked_total = len((train_db.get("segment_report", {}) or {}).get("blocked_segments", []) or [])
    for strategy in STRATEGIES:
        kept_by_market: Counter = Counter()
        reject_reasons: Counter = Counter()
        blocked_examples: List[Dict[str, Any]] = []
        no_segment_count = 0
        kept = 0
        rejected = 0
        for record in test_records:
            decision = _strategy_decision(strategy, record, train_db)
            if decision.get("no_segment"):
                no_segment_count += 1
            if decision["keep"]:
                kept += 1
                kept_by_market[str(record.get("market_type") or "?")] += 1
                continue
            rejected += 1
            reject_reasons[decision.get("reason", "refus")] += 1
            blocked = decision.get("blocked_segment") or {}
            if blocked and len(blocked_examples) < 5:
                blocked_examples.append({
                    "segment": blocked.get("key", ""),
                    "label": blocked.get("label", ""),
                    "roi": blocked.get("roi", 0),
                    "n": blocked.get("n", 0),
                    "record": {
                        "date": _date_key(record),
                        "market_type": record.get("market_type"),
                        "pari": record.get("pari"),
                        "odds": record.get("odds"),
                    },
                })
        warning = ""
        if strategy == "no_blocked_segments":
            if blocked_total == 0:
                warning = "aucun segment bloque dans le train"
            elif rejected == 0:
                warning = "aucun segment bloque ne matche le test"
        report[strategy] = {
            "kept": kept,
            "rejected": rejected,
            "reject_reasons": dict(reject_reasons.most_common(8)),
            "blocked_examples": blocked_examples,
            "records_without_segment": no_segment_count,
            "kept_by_market": dict(kept_by_market),
            "blocked_segments_in_train": blocked_total,
            "warning": warning,
        }
    return report


def _year_from_record(record: Dict[str, Any]) -> str:
    date_key = _date_key(record)
    return date_key[:4] if len(date_key) >= 4 else "inconnue"


def targeted_reports(test_records: List[Dict[str, Any]], train_db: Dict[str, Any]) -> Dict[str, Any]:
    h2h_favorites = [r for r in test_records if _is_h2h_favorite(r)]
    return {
        "favorites_h2h": {
            "all": summarize_records(h2h_favorites),
            "odds_lt_1_6": summarize_records([r for r in h2h_favorites if _num(r.get("odds"), 99.0) < 1.6]),
            "odds_lt_1_8": summarize_records([r for r in h2h_favorites if _num(r.get("odds"), 99.0) < 1.8]),
            "home_favorite": summarize_records([r for r in h2h_favorites if h2h_side(r) == "home"]),
            "away_favorite": summarize_records([r for r in h2h_favorites if h2h_side(r) == "away"]),
            "elo_favorable": summarize_records([r for r in h2h_favorites if _is_elo_favorable_h2h(r)]),
        },
        "total_low_by_period": _group_stats(
            [r for r in test_records if r.get("market_type") == "total" and odds_bucket(_num(r.get("odds"), 2.0)) == "low"],
            _year_from_record,
        ),
        "draw_high_watchlist": summarize_records(
            [r for r in test_records if r.get("market_type") == "draw" and odds_bucket(_num(r.get("odds"), 2.0)) == "high"]
        ),
    }


def _rule_effective_max(rule: Dict[str, Any]) -> float:
    max_odds = float(rule["odds_max"])
    if rule.get("exclude_outsiders"):
        max_odds = min(max_odds, 2.9999)
    if rule.get("exclude_very_high"):
        max_odds = min(max_odds, 3.1999)
    return max_odds


def _rule_label(rule: Dict[str, Any]) -> str:
    bits = [
        f"market={rule['market']}",
        f"bucket={rule['odds_bucket']}",
        f"odds<={rule['odds_max']}",
        f"min_train_roi={rule['min_train_roi']}%",
        f"min_n={rule['min_segment_n']}",
    ]
    if rule.get("exclude_outsiders"):
        bits.append("sans outsiders")
    if rule.get("exclude_very_high"):
        bits.append("sans very_high")
    return ", ".join(bits)


def _rule_key(rule: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        rule["market"],
        rule["odds_bucket"],
        rule["odds_max"],
        rule["exclude_outsiders"],
        rule["exclude_very_high"],
    )


def _records_for_rule(records: List[Dict[str, Any]], rule: Dict[str, Any], cache: Dict[Tuple[Any, ...], List[Dict[str, Any]]], dataset: str) -> List[Dict[str, Any]]:
    key = (dataset,) + _rule_key(rule)
    if key in cache:
        return cache[key]
    max_odds = _rule_effective_max(rule)
    selected = [
        r
        for r in records
        if r.get("market_type") == rule["market"]
        and odds_bucket(_num(r.get("odds"), 2.0)) == rule["odds_bucket"]
        and _num(r.get("odds"), 99.0) <= max_odds
    ]
    cache[key] = selected
    return selected


def _dedupe_rule_entries(entries: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for entry in entries:
        key = (
            entry["rule"]["market"],
            entry["rule"]["odds_bucket"],
            entry["train"]["picks"],
            entry["train"]["profit"],
            entry["validation"]["picks"],
            entry["validation"]["profit"],
            entry["test"]["picks"],
            entry["test"]["profit"],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def threshold_sweep(train_records: List[Dict[str, Any]], validation_records: List[Dict[str, Any]], test_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    odds_max_values = [1.6, 1.8, 2.0, 2.2, 2.5, 3.0]
    markets = ["h2h", "draw", "total"]
    buckets = ["low", "mid", "high", "very_high"]
    min_train_rois = [-2.0, -1.0, 0.0, 1.0, 2.0]
    min_segment_ns = [100, 300, 500, 1000]
    cache: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    candidates: List[Dict[str, Any]] = []

    for market in markets:
        for bucket in buckets:
            for odds_max in odds_max_values:
                for exclude_outsiders in (False, True):
                    for exclude_very_high in (False, True):
                        base_rule = {
                            "market": market,
                            "odds_bucket": bucket,
                            "odds_max": odds_max,
                            "exclude_outsiders": exclude_outsiders,
                            "exclude_very_high": exclude_very_high,
                        }
                        train_selected = _records_for_rule(train_records, base_rule, cache, "train")
                        train_stat = summarize_records(train_selected, include_groups=False)
                        validation_selected = _records_for_rule(validation_records, base_rule, cache, "validation")
                        validation_stat = summarize_records(validation_selected, include_groups=False)
                        test_selected = _records_for_rule(test_records, base_rule, cache, "test")
                        test_stat = summarize_records(test_selected, include_groups=False)
                        for min_train_roi in min_train_rois:
                            for min_segment_n in min_segment_ns:
                                if train_stat["picks"] < min_segment_n or train_stat["roi"] < min_train_roi:
                                    continue
                                rule = dict(base_rule)
                                rule["min_train_roi"] = min_train_roi
                                rule["min_segment_n"] = min_segment_n
                                entry = {
                                    "rule": rule,
                                    "label": _rule_label(rule),
                                    "selection_basis": "train_et_validation_sans_test",
                                    "train": train_stat,
                                    "validation": validation_stat,
                                    "test": test_stat,
                                    "fragile_train_positive_test_negative": train_stat["roi"] > 0 and test_stat["picks"] >= 100 and test_stat["roi"] < 0,
                                }
                                candidates.append(entry)

    top_train = _dedupe_rule_entries(sorted(candidates, key=lambda e: (e["train"]["roi"], e["train"]["picks"]), reverse=True), 10)
    top_validation = _dedupe_rule_entries(sorted(
        candidates,
        key=lambda e: (e["validation"]["picks"] >= 100, e["validation"]["roi"], e["train"]["roi"], e["train"]["picks"]),
        reverse=True,
    ), 10)
    rejected = [e for e in candidates if e["fragile_train_positive_test_negative"]]
    rejected = _dedupe_rule_entries(sorted(rejected, key=lambda e: (e["train"]["roi"], e["test"]["roi"]), reverse=True), 10)
    return {
        "candidates_tested": len(candidates),
        "selection_policy": "les regles sont filtrees sur train puis triees par train/validation; le test sert uniquement a verifier",
        "top_train_rules": top_train,
        "top_validation_rules": top_validation,
        "rejected_train_positive_test_negative": rejected,
    }


def prudent_conclusion(report: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    strategies = report.get("strategies", {})
    robust = [
        name for name, stat in strategies.items()
        if stat.get("picks", 0) >= 300 and stat.get("roi", 0) > 0 and stat.get("max_drawdown", 0) <= max(50, stat.get("picks", 0) * 0.25)
    ]
    if not robust:
        lines.append("Aucune regle jouable: ROI test <= 0 ou echantillon trop faible sur les strategies principales.")
    else:
        lines.append("Regles candidates a surveiller seulement: " + ", ".join(robust))
    fragile = report.get("threshold_sweep", {}).get("rejected_train_positive_test_negative", [])
    if fragile:
        lines.append("Signal fragile: certaines regles positives train deviennent negatives sur le test final.")
    baseline = strategies.get("baseline_all", {})
    strict = strategies.get("oracle_strict") or strategies.get("strict_oracle", {})
    if baseline.get("roi", 0) < 0 and strict.get("picks", 0) == 0:
        lines.append("Le refus reste le comportement rationnel tant que le test final ne valide pas une niche robuste.")
    return lines


def evaluate_backtest(db: Dict[str, Any], train_to: str = "2023-12-31", test_from: str = "2024-01-01", preset: str = "", debug_strategies: bool = False) -> Dict[str, Any]:
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
    sweep = threshold_sweep(train_records, validation_records, test_records)
    report = {
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
        "targeted_reports": targeted_reports(test_records, train_db),
        "threshold_sweep": sweep,
        "conclusion": "Aucune stratégie positive robuste sur le test." if not positive else "Au moins une stratégie est positive sur le test, à confirmer hors échantillon.",
    }


    report["prudence"] = prudent_conclusion(report)
    if debug_strategies:
        report["debug_strategies"] = debug_strategy_report(test_records, train_db)
    return report


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


def _short_stat(stat: Dict[str, Any]) -> str:
    return f"n={stat.get('picks', 0)}, ROI={_fmt_pct(stat.get('roi', 0))}, profit={stat.get('profit', 0)}"


def print_targeted_reports(report: Dict[str, Any]) -> None:
    targeted = report.get("targeted_reports", {})
    if not targeted:
        return
    print("\nAnalyses ciblees")
    fav = targeted.get("favorites_h2h", {})
    if fav:
        print("- Favoris H2H:")
        for key in ("all", "odds_lt_1_6", "odds_lt_1_8", "home_favorite", "away_favorite", "elo_favorable"):
            print(f"  - {key}: {_short_stat(fav.get(key, {}))}")
    print("- Total low par annee test:")
    for year, stat in sorted((targeted.get("total_low_by_period") or {}).items()):
        print(f"  - {year}: {_short_stat(stat)}")
    draw_high = targeted.get("draw_high_watchlist", {})
    if draw_high:
        print(f"- Draw high watchlist: {_short_stat(draw_high)} (surveillance, pas une regle de jeu)")


def print_threshold_sweep(report: Dict[str, Any]) -> None:
    sweep = report.get("threshold_sweep", {})
    if not sweep:
        return
    print("\nThreshold sweep train/validation -> test")
    print(f"- Regles candidates testees apres filtre train: {sweep.get('candidates_tested', 0)}")
    print(f"- Politique: {sweep.get('selection_policy', '')}")
    print("- Top regles train:")
    for entry in (sweep.get("top_train_rules") or [])[:5]:
        print(f"  - {entry['label']}")
        print(f"    train {_short_stat(entry['train'])} | validation {_short_stat(entry['validation'])} | test {_short_stat(entry['test'])}")
    print("- Top regles validation:")
    for entry in (sweep.get("top_validation_rules") or [])[:5]:
        print(f"  - {entry['label']}")
        print(f"    train {_short_stat(entry['train'])} | validation {_short_stat(entry['validation'])} | test {_short_stat(entry['test'])}")
    rejected = sweep.get("rejected_train_positive_test_negative") or []
    if rejected:
        print("- Regles positives train mais negatives test final:")
        for entry in rejected[:5]:
            print(f"  - {entry['label']} | train {_short_stat(entry['train'])} | test {_short_stat(entry['test'])}")


def print_debug_strategies(report: Dict[str, Any]) -> None:
    debug = report.get("debug_strategies", {})
    if not debug:
        return
    print("\nDebug strategies")
    for strategy in STRATEGIES:
        info = debug.get(strategy, {})
        print(f"- {STRATEGY_LABELS.get(strategy, strategy)}: retenus={info.get('kept', 0)}, rejetes={info.get('rejected', 0)}, sans segment={info.get('records_without_segment', 0)}")
        if info.get("warning"):
            print(f"  Attention: {info['warning']}")
        reasons = info.get("reject_reasons") or {}
        if reasons:
            print("  Raisons principales:")
            for reason, count in list(reasons.items())[:4]:
                print(f"    - {reason}: {count}")
        examples = info.get("blocked_examples") or []
        if examples:
            print("  Exemples de segments bloques:")
            for ex in examples[:3]:
                print(f"    - {ex.get('label') or ex.get('segment')}: ROI={_fmt_pct(ex.get('roi', 0))}, n={ex.get('n', 0)}")
        kept_by_market = info.get("kept_by_market") or {}
        if kept_by_market:
            print("  Retenus par marche: " + ", ".join(f"{k}={v}" for k, v in kept_by_market.items()))


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
    print_targeted_reports(report)
    print_threshold_sweep(report)
    print_debug_strategies(report)
    if report.get("prudence"):
        print("\nConclusion prudente")
        for line in report["prudence"]:
            print(f"- {line}")
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
    modern_new = stats.get("modern_2015_2019") or {}
    recent_new = stats.get("recent_2020_2023") or {}
    test_new = stats.get("test_2024_plus") or {}
    archive_new = stats.get("archive_pre2012") or {}
    modern_ok = modern_new.get("picks", 0) >= 100 and modern_new.get("roi", 0) > 0
    recent_ok = recent_new.get("picks", 0) >= 100 and recent_new.get("roi", 0) > 0
    test_seen = test_new.get("picks", 0) >= 100
    test_ok = test_seen and test_new.get("roi", 0) >= 0
    if modern_ok and recent_ok and test_seen and not test_ok:
        return "positif train/recent mais non confirme sur test final"
    if modern_ok and recent_ok and test_ok:
        return "signal confirme train/recent/test"
    if archive_new.get("picks", 0) >= 100 and archive_new.get("roi", 0) > 2 and not (modern_ok or recent_ok):
        return "signal ancien seulement"
    if modern_new.get("picks", 0) >= 100 and recent_new.get("picks", 0) >= 100 and test_seen:
        if modern_new.get("roi", 0) < 0 and recent_new.get("roi", 0) < 0 and test_new.get("roi", 0) < 0:
            return "signal negatif robuste"
    if any(s.get("picks", 0) >= 100 and s.get("roi", 0) < -8 for s in stats.values()):
        return "signal negatif robuste"
    return "signal instable"
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
    parser.add_argument("--debug-strategies", action="store_true", help="Affiche les raisons de rejet et les segments appliques")
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
    report = evaluate_backtest(db, args.train_to, args.test_from, args.preset, debug_strategies=args.debug_strategies)
    print_report(report)
    if args.json_path:
        write_json(report, args.json_path)


if __name__ == "__main__":
    main()
