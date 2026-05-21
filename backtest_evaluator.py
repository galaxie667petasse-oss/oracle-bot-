import argparse
import json
import math
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from calibration import (
    blocked_segment_for_pick,
    build_calibration,
    league_bucket,
    segment_adjustment_for_pick,
    segment_matches_for_pick,
)
from segment_analysis import h2h_side, odds_bucket
from recency import PERIOD_ORDER, date_min_max, record_period
from pricing import expected_value, fair_odds, implied_probability, market_margin, remove_vig_1x2, remove_vig_two_way


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

PRICING_LOW_MARGIN = 0.03
PRICING_HIGH_MARGIN = 0.08
PRICING_TOO_HIGH_MARGIN = 0.10


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _optional_num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def _round_metric(value: Any, digits: int = 6) -> Optional[float]:
    number = _optional_num(value)
    if number is None:
        return None
    return round(number, digits)


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


def _match_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    match_id = record.get("match_id")
    if match_id:
        return ("match_id", match_id)
    return (
        "match",
        _date_key(record),
        record.get("home"),
        record.get("away"),
        record.get("competition"),
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


def _pricing_market_label(record: Dict[str, Any]) -> str:
    market = str(record.get("market_type") or "")
    if market in ("h2h", "draw"):
        return "H2H 1X2"
    if market == "total":
        return "Over/Under 2.5"
    return market or "marche inconnu"


def _with_pricing(record: Dict[str, Any], market_label: str, no_vig_probability: Optional[float] = None, margin: Optional[float] = None) -> Dict[str, Any]:
    item = deepcopy(record)
    item["pricing_market"] = market_label
    implied = _round_metric(implied_probability(item.get("odds")))
    if implied is not None:
        item["implied_probability"] = implied
    if no_vig_probability is None:
        no_vig_probability = _optional_num(item.get("no_vig_probability"))
    if margin is None:
        margin = _optional_num(item.get("market_margin"))
    if no_vig_probability is None or margin is None:
        return item
    fair = fair_odds(no_vig_probability)
    ev = expected_value(no_vig_probability, item.get("odds"))
    item["no_vig_probability"] = _round_metric(no_vig_probability)
    item["market_margin"] = _round_metric(margin)
    fair_value = _round_metric(fair, digits=4)
    ev_value = _round_metric(ev)
    if fair_value is not None:
        item["fair_odds_market"] = fair_value
    if ev_value is not None:
        item["ev_market_baseline"] = ev_value
    return item


def _market_instance(label: str, key: Tuple[Any, ...], margin: Optional[float], records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if margin is None:
        return None
    return {
        "pricing_market": label,
        "match_key": key,
        "market_margin": _round_metric(margin),
        "records": len(records),
    }


def pricing_records(records: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(_match_key(record), []).append(record)

    priced: List[Dict[str, Any]] = []
    instances: List[Dict[str, Any]] = []
    seen = set()

    for key, group in groups.items():
        home = next((r for r in group if r.get("market_type") == "h2h" and h2h_side(r) == "home"), None)
        draw = next((r for r in group if r.get("market_type") == "draw" or str(r.get("import_family", "")).lower() == "draw"), None)
        away = next((r for r in group if r.get("market_type") == "h2h" and h2h_side(r) == "away"), None)
        if home and draw and away:
            probabilities = [implied_probability(home.get("odds")), implied_probability(draw.get("odds")), implied_probability(away.get("odds"))]
            margin = market_margin(probabilities) if all(p is not None for p in probabilities) else None
            no_vig = remove_vig_1x2(home.get("odds"), draw.get("odds"), away.get("odds"))
            if no_vig is not None and margin is not None:
                instance = _market_instance("H2H 1X2", key, margin, [home, draw, away])
                if instance:
                    instances.append(instance)
                for record, side in ((home, "home"), (draw, "draw"), (away, "away")):
                    priced_record = _with_pricing(record, "H2H 1X2", no_vig[side], margin)
                    priced.append(priced_record)
                    seen.add(_record_key(record))

        over = next((r for r in group if _total_side(r) == "over"), None)
        under = next((r for r in group if _total_side(r) == "under"), None)
        if over and under:
            probabilities = [implied_probability(over.get("odds")), implied_probability(under.get("odds"))]
            margin = market_margin(probabilities) if all(p is not None for p in probabilities) else None
            no_vig = remove_vig_two_way(over.get("odds"), under.get("odds"))
            if no_vig is not None and margin is not None:
                instance = _market_instance("Over/Under 2.5", key, margin, [over, under])
                if instance:
                    instances.append(instance)
                for record, side in ((over, "over"), (under, "under")):
                    priced_record = _with_pricing(record, "Over/Under 2.5", no_vig[side], margin)
                    priced.append(priced_record)
                    seen.add(_record_key(record))

    for record in records:
        if _record_key(record) in seen:
            continue
        if _optional_num(record.get("no_vig_probability")) is None or _optional_num(record.get("market_margin")) is None:
            continue
        priced.append(_with_pricing(record, _pricing_market_label(record)))

    return priced, instances


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


def _average(values: Iterable[Any]) -> Optional[float]:
    numbers = [_optional_num(value) for value in values]
    clean = [number for number in numbers if number is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _margin_bucket(margin: Any) -> str:
    value = _num(margin, 0.0)
    if value < 0.02:
        return "marge < 2%"
    if value < 0.05:
        return "2% <= marge < 5%"
    if value < 0.08:
        return "5% <= marge < 8%"
    if value < 0.12:
        return "8% <= marge < 12%"
    return "marge >= 12%"


def _pricing_group(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        margin = _optional_num(record.get("market_margin"))
        if margin is None:
            continue
        groups.setdefault(_margin_bucket(margin), []).append(record)
    ordered = ["marge < 2%", "2% <= marge < 5%", "5% <= marge < 8%", "8% <= marge < 12%", "marge >= 12%"]
    return {bucket: summarize_records(groups[bucket], include_groups=False) for bucket in ordered if bucket in groups}


def _pricing_comparison(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [
        record for record in records
        if _optional_num(record.get("implied_probability")) is not None and _optional_num(record.get("no_vig_probability")) is not None
    ]
    gaps = [_num(record.get("implied_probability")) - _num(record.get("no_vig_probability")) for record in rows]
    return {
        "picks": len(rows),
        "average_raw_odds": _average(record.get("odds") for record in rows),
        "average_implied_probability": _average(record.get("implied_probability") for record in rows),
        "average_no_vig_probability": _average(record.get("no_vig_probability") for record in rows),
        "average_probability_gap": _average(gaps),
        "average_fair_odds_market": _average(record.get("fair_odds_market") for record in rows),
        "average_ev_market_baseline": _average(record.get("ev_market_baseline") for record in rows),
    }


def build_pricing_report(db: Dict[str, Any]) -> Dict[str, Any]:
    records = all_settled_records(db)
    priced, instances = pricing_records(records)
    h2h_instances = [item for item in instances if item.get("pricing_market") == "H2H 1X2"]
    total_instances = [item for item in instances if item.get("pricing_market") == "Over/Under 2.5"]
    low_records = [record for record in priced if _optional_num(record.get("market_margin")) is not None and _num(record.get("market_margin")) <= PRICING_LOW_MARGIN]
    high_records = [record for record in priced if _optional_num(record.get("market_margin")) is not None and _num(record.get("market_margin")) >= PRICING_HIGH_MARGIN]

    comparison: Dict[str, Dict[str, Any]] = {"global": _pricing_comparison(priced)}
    for market in sorted({str(record.get("pricing_market") or "marche inconnu") for record in priced}):
        comparison[market] = _pricing_comparison([record for record in priced if record.get("pricing_market") == market])

    too_high_records = [record for record in priced if _optional_num(record.get("market_margin")) is not None and _num(record.get("market_margin")) >= PRICING_TOO_HIGH_MARGIN]
    too_high_by_market: Dict[str, Dict[str, Any]] = {}
    for market in sorted({str(record.get("pricing_market") or "marche inconnu") for record in too_high_records}):
        rows = [record for record in too_high_records if record.get("pricing_market") == market]
        market_rows = [record for record in priced if record.get("pricing_market") == market]
        stat = summarize_records(rows, include_groups=False)
        stat["average_margin"] = _average(record.get("market_margin") for record in rows)
        stat["share_of_market"] = round(len(rows) / len(market_rows) * 100, 1) if market_rows else 0.0
        too_high_by_market[market] = stat

    return {
        "records_total": len(records),
        "priced_records": len(priced),
        "market_instances": len(instances),
        "h2h_market_count": len(h2h_instances),
        "over_under_market_count": len(total_instances),
        "average_margin_h2h": _average(item.get("market_margin") for item in h2h_instances),
        "average_margin_over_under": _average(item.get("market_margin") for item in total_instances),
        "roi_by_margin": _pricing_group(priced),
        "low_margin": summarize_records(low_records, include_groups=False),
        "high_margin": summarize_records(high_records, include_groups=False),
        "comparison": comparison,
        "too_high_threshold": PRICING_TOO_HIGH_MARGIN,
        "too_high_markets": too_high_by_market,
    }


def _favorite_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [record for record in records if _is_h2h_favorite(record)]


def _odds_favorite_bucket(record: Dict[str, Any]) -> str:
    odds = _num(record.get("odds"), 99.0)
    if odds < 1.40:
        return "cote < 1.40"
    if odds < 1.60:
        return "1.40 <= cote < 1.60"
    if odds < 1.80:
        return "1.60 <= cote < 1.80"
    return "1.80 <= cote < 2.00"


def _favorite_side(record: Dict[str, Any]) -> str:
    side = h2h_side(record)
    if side == "home":
        return "domicile favori"
    if side == "away":
        return "exterieur favori"
    return "favori non determine"


def _relative_edge(record: Dict[str, Any], home_key: str, away_key: str) -> Any:
    home_value = record.get(home_key)
    away_value = record.get(away_key)
    if home_value in (None, "") or away_value in (None, ""):
        return None
    side = h2h_side(record)
    diff = _num(home_value) - _num(away_value)
    if side == "home":
        return diff
    if side == "away":
        return -diff
    return None


def _elo_favorite_bucket(record: Dict[str, Any]) -> str:
    edge = _relative_edge(record, "home_elo", "away_elo")
    if edge is None and record.get("elo_diff") not in (None, ""):
        side = h2h_side(record)
        diff = _num(record.get("elo_diff"))
        if side == "home":
            edge = diff
        elif side == "away":
            edge = -diff
    if edge is None:
        return "elo_diff faible ou contradictoire"
    if edge >= 75:
        return "elo_diff fort positif"
    if edge >= 25:
        return "elo_diff modere positif"
    return "elo_diff faible ou contradictoire"


def _form_favorite_bucket(record: Dict[str, Any], window: str) -> str:
    edge = _relative_edge(record, f"{window}_home", f"{window}_away")
    if edge is None:
        return f"{window} indisponible"
    if edge > 0:
        return f"{window} favorable"
    if edge < 0:
        return f"{window} defavorable"
    return f"{window} neutre"


def _competition_key(record: Dict[str, Any]) -> str:
    return str(record.get("competition") or record.get("Division") or "competition inconnue")


def _favorite_status(train: Dict[str, Any], validation: Dict[str, Any], test: Dict[str, Any]) -> str:
    test_n = int(test.get("picks", 0) or 0)
    train_roi = _num(train.get("roi"), 0.0)
    validation_roi = _num(validation.get("roi"), 0.0)
    test_roi = _num(test.get("roi"), 0.0)
    if test_n < 300:
        return "echantillon faible"
    if train_roi > 0 and test_roi <= 0:
        return "non confirme sur test"
    if test_roi > 0 and train_roi < 0:
        return "fragile"
    if test_roi <= 0:
        return "negatif a eviter"
    if 0 < test_roi < 1:
        return "observation seulement"
    if train_roi > 0 and validation_roi >= -1 and test_roi >= 1:
        return "robuste positif"
    return "fragile"


def _favorite_segment_entry(label: str, train_records: List[Dict[str, Any]], validation_records: List[Dict[str, Any]], test_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    train = summarize_records(train_records, include_groups=False)
    validation = summarize_records(validation_records, include_groups=False)
    test = summarize_records(test_records, include_groups=False)
    return {
        "label": label,
        "train": train,
        "validation": validation,
        "test": test,
        "status": _favorite_status(train, validation, test),
    }


def _favorite_group(records: List[Dict[str, Any]], key_fn) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        groups.setdefault(str(key_fn(record)), []).append(record)
    return groups


def _build_favorite_group(label: str, train: List[Dict[str, Any]], validation: List[Dict[str, Any]], test: List[Dict[str, Any]], key_fn, limit: int = 0) -> Dict[str, Any]:
    train_groups = _favorite_group(train, key_fn)
    validation_groups = _favorite_group(validation, key_fn)
    test_groups = _favorite_group(test, key_fn)
    keys = sorted(set(train_groups) | set(validation_groups) | set(test_groups))
    entries = [
        _favorite_segment_entry(
            key,
            train_groups.get(key, []),
            validation_groups.get(key, []),
            test_groups.get(key, []),
        )
        for key in keys
    ]
    if limit:
        entries = sorted(entries, key=lambda entry: entry["test"]["picks"], reverse=True)[:limit]
    return {"label": label, "segments": entries}


def _build_favorite_static_group(label: str, train: List[Dict[str, Any]], validation: List[Dict[str, Any]], test: List[Dict[str, Any]], specs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    entries = [
        _favorite_segment_entry(
            segment_label,
            [record for record in train if predicate(record)],
            [record for record in validation if predicate(record)],
            [record for record in test if predicate(record)],
        )
        for segment_label, predicate in specs
    ]
    return {"label": label, "segments": entries}


def build_favorite_report(db: Dict[str, Any]) -> Dict[str, Any]:
    records = all_settled_records(db)
    params = dict(PRESETS["modern"])
    train_records, validation_records, test_records = split_by_ranges(records, params)
    train = _favorite_records(train_records)
    validation = _favorite_records(validation_records)
    test = _favorite_records(test_records)
    groups = [
        _build_favorite_group("Tranches de cotes", train, validation, test, _odds_favorite_bucket),
        _build_favorite_group("Domicile / exterieur", train, validation, test, _favorite_side),
        _build_favorite_group("Elo relatif au favori", train, validation, test, _elo_favorite_bucket),
        _build_favorite_group("Forme 3 matchs", train, validation, test, lambda r: _form_favorite_bucket(r, "form3")),
        _build_favorite_group("Forme 5 matchs", train, validation, test, lambda r: _form_favorite_bucket(r, "form5")),
        _build_favorite_static_group("Annees test", train, validation, test, [
            ("annee 2024", lambda r: _year_from_record(r) == "2024"),
            ("annee 2025", lambda r: _year_from_record(r) == "2025"),
        ]),
        _build_favorite_group("Competition", train, validation, test, _competition_key, limit=20),
    ]
    all_entry = _favorite_segment_entry("Tous favoris H2H", train, validation, test)
    report = {
        "params": params,
        "scope": "market_type=h2h et odds<2.0",
        "overall": all_entry,
        "groups": groups,
    }
    report["conclusion"] = favorite_report_conclusion(report)
    return report


def _favorite_entries(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for group in report.get("groups", []):
        for entry in group.get("segments", []):
            item = dict(entry)
            item["group"] = group.get("label", "")
            entries.append(item)
    return entries


def favorite_report_conclusion(report: Dict[str, Any]) -> Dict[str, Any]:
    entries = _favorite_entries(report)
    best = sorted(
        [e for e in entries if e["test"]["picks"] >= 300 and e["test"]["roi"] > 0],
        key=lambda e: (e["test"]["roi"], e["test"]["picks"]),
        reverse=True,
    )[:8]
    invalidated = sorted(
        [e for e in entries if e["train"]["roi"] > 0 and e["test"]["picks"] >= 300 and e["test"]["roi"] <= 0],
        key=lambda e: (e["train"]["roi"], -e["test"]["roi"]),
        reverse=True,
    )[:8]
    avoid = sorted(
        [e for e in entries if e["test"]["picks"] >= 300 and e["test"]["roi"] <= 0],
        key=lambda e: (e["test"]["roi"], -e["test"]["picks"]),
    )[:8]
    recommendation = "Aucun segment favori H2H ne doit devenir top pick automatiquement."
    if best:
        recommendation += " Les meilleurs signaux restent seulement des observations a confirmer hors echantillon."
    else:
        recommendation += " Le rapport confirme une posture de refus/prudence."
    return {
        "best_segments": best,
        "invalidated_segments": invalidated,
        "avoid_segments": avoid,
        "recommendation": recommendation,
    }


def _stability_strategies() -> List[Tuple[str, str, Any]]:
    return [
        ("baseline_all", "Baseline marche brut", lambda r: True),
        ("favorites_only", "Favoris seulement", lambda r: _num(r.get("odds"), 99.0) < 2.0),
        ("h2h_favorites_all", "Favoris H2H tous", _is_h2h_favorite),
        (
            "h2h_favorites_odds_1_60_1_80",
            "Favoris H2H cote 1.60-1.80",
            lambda r: _is_h2h_favorite(r) and 1.60 <= _num(r.get("odds"), 99.0) < 1.80,
        ),
        ("h2h_home_favorite", "H2H domicile favori", lambda r: _is_h2h_favorite(r) and h2h_side(r) == "home"),
        ("h2h_away_favorite", "H2H exterieur favori", lambda r: _is_h2h_favorite(r) and h2h_side(r) == "away"),
        ("h2h_favorite_strong_elo", "H2H favori Elo fort positif", lambda r: _is_h2h_favorite(r) and _elo_favorite_bucket(r) == "elo_diff fort positif"),
        ("totals_only", "Totals seulement", lambda r: r.get("market_type") == "total"),
        ("totals_low", "Totals low", lambda r: r.get("market_type") == "total" and odds_bucket(_num(r.get("odds"), 2.0)) == "low"),
        ("totals_low_mid", "Totals low/mid", lambda r: r.get("market_type") == "total" and odds_bucket(_num(r.get("odds"), 2.0)) in ("low", "mid")),
        ("draw_high_watchlist", "Watchlist draw high", lambda r: r.get("market_type") == "draw" and odds_bucket(_num(r.get("odds"), 2.0)) == "high"),
    ]


def _annual_stats(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return _group_stats(records, _year_from_record)


def _stability_score(annual: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    qualified = {year: stat for year, stat in annual.items() if stat.get("picks", 0) >= 300}
    positive = {year: stat for year, stat in qualified.items() if stat.get("roi", 0) > 0}
    negative = {year: stat for year, stat in qualified.items() if stat.get("roi", 0) <= 0}
    if qualified:
        avg_roi = round(sum(_num(stat.get("roi")) for stat in qualified.values()) / len(qualified), 2)
        worst_year, worst_stat = min(qualified.items(), key=lambda item: item[1].get("roi", 0))
        best_year, best_stat = max(qualified.items(), key=lambda item: item[1].get("roi", 0))
        max_dd = max(_num(stat.get("max_drawdown")) for stat in qualified.values())
    else:
        avg_roi = 0.0
        worst_year, worst_stat = "", {}
        best_year, best_stat = "", {}
        max_dd = 0.0
    return {
        "positive_years": len(positive),
        "negative_years": len(negative),
        "qualified_years": len(qualified),
        "average_annual_roi": avg_roi,
        "worst_year": {"year": worst_year, "roi": worst_stat.get("roi", 0), "n": worst_stat.get("picks", 0)},
        "best_year": {"year": best_year, "roi": best_stat.get("roi", 0), "n": best_stat.get("picks", 0)},
        "max_drawdown_observed": round(max_dd, 2),
    }


def _stability_note(annual: Dict[str, Dict[str, Any]], train: Dict[str, Any], validation: Dict[str, Any], test: Dict[str, Any]) -> str:
    score = _stability_score(annual)
    qualified_years = score["qualified_years"]
    if qualified_years < 2:
        return "echantillon faible"
    positive_years = score["positive_years"]
    negative_years = score["negative_years"]
    positive_ratio = positive_years / qualified_years if qualified_years else 0.0
    recent_stats = [annual.get("2024", {}), annual.get("2025", {})]
    recent_qualified = [stat for stat in recent_stats if stat.get("picks", 0) >= 300]
    recent_negative = any(stat.get("roi", 0) <= 0 for stat in recent_qualified)
    pre_2024 = [stat for year, stat in annual.items() if year < "2024" and stat.get("picks", 0) >= 300]
    pre_2024_positive = bool(pre_2024) and sum(_num(stat.get("profit")) for stat in pre_2024) > 0
    if pre_2024_positive and recent_negative:
        return "degradation recente"
    if positive_ratio >= 0.70 and test.get("roi", 0) > 0 and not recent_negative:
        return "stable positif"
    if negative_years > positive_years:
        return "negatif robuste"
    if positive_years and negative_years:
        return "instable"
    if test.get("picks", 0) < 300:
        return "echantillon faible"
    return "instable"


def build_stability_report(db: Dict[str, Any]) -> Dict[str, Any]:
    records = all_settled_records(db)
    params = dict(PRESETS["modern"])
    train_records, validation_records, test_records = split_by_ranges(records, params)
    all_modern_records = train_records + validation_records + test_records
    strategies = []
    for key, label, predicate in _stability_strategies():
        selected_all = [record for record in all_modern_records if predicate(record)]
        selected_train = [record for record in train_records if predicate(record)]
        selected_validation = [record for record in validation_records if predicate(record)]
        selected_test = [record for record in test_records if predicate(record)]
        annual = _annual_stats(selected_all)
        train = summarize_records(selected_train, include_groups=False)
        validation = summarize_records(selected_validation, include_groups=False)
        test = summarize_records(selected_test, include_groups=False)
        score = _stability_score(annual)
        note = _stability_note(annual, train, validation, test)
        strategies.append({
            "key": key,
            "label": label,
            "annual": annual,
            "train": train,
            "validation": validation,
            "test": test,
            "score": score,
            "stability_note": note,
            "candidate_allowed": (
                note == "stable positif"
                and train.get("roi", 0) > 0
                and validation.get("roi", 0) > 0
                and test.get("roi", 0) >= 1.0
                and annual.get("2025", {}).get("roi", 0) > 0
            ),
        })
    report = {
        "params": params,
        "scope": "stabilite annuelle sur donnees modernes 2015-2025",
        "strategies": strategies,
    }
    report["conclusion"] = stability_report_conclusion(report)
    return report


def stability_report_conclusion(report: Dict[str, Any]) -> Dict[str, Any]:
    strategies = report.get("strategies", [])
    stable = [s for s in strategies if s.get("candidate_allowed")]
    observations = [
        s for s in strategies
        if s.get("stability_note") in ("stable positif", "instable") and s.get("test", {}).get("roi", 0) > 0 and not s.get("candidate_allowed")
    ]
    degraded = [s for s in strategies if s.get("stability_note") == "degradation recente"]
    negative = [s for s in strategies if s.get("stability_note") == "negatif robuste"]
    return {
        "candidate_segments": stable,
        "observation_segments": observations,
        "degraded_segments": degraded,
        "negative_segments": negative,
        "recommendation": "Aucun segment ne doit devenir pick conseille si 2025 est negatif ou si le ROI test reste inferieur a 1%. Un segment positif mais instable reste une observation.",
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


def _fmt_margin(value: Any) -> str:
    number = _optional_num(value)
    if number is None:
        return "n/a"
    return f"{number * 100:.2f}%"


def _fmt_decimal(value: Any, digits: int = 2) -> str:
    number = _optional_num(value)
    if number is None:
        return "n/a"
    return f"{number:.{digits}f}"


def print_pricing_report(report: Dict[str, Any]) -> None:
    print("Rapport pricing Oracle Bot")
    print(f"- Records regles: {report.get('records_total', 0)}")
    print(f"- Records avec pricing exploitable: {report.get('priced_records', 0)}")
    print(f"- Marches complets reconstruits: {report.get('market_instances', 0)}")
    print(f"- Marge moyenne H2H: {_fmt_margin(report.get('average_margin_h2h'))} (marches={report.get('h2h_market_count', 0)})")
    print(f"- Marge moyenne Over/Under: {_fmt_margin(report.get('average_margin_over_under'))} (marches={report.get('over_under_market_count', 0)})")

    print("\nROI par tranche de marge")
    roi_by_margin = report.get("roi_by_margin") or {}
    if roi_by_margin:
        for bucket, stat in roi_by_margin.items():
            print(f"- {bucket}: {_short_stat(stat)}, cote moy={stat.get('average_odds', 0)}")
    else:
        print("- Aucune tranche disponible.")

    print("\nROI selon niveau de marge")
    print(f"- Marge faible (<= {_fmt_margin(PRICING_LOW_MARGIN)}): {_short_stat(report.get('low_margin', {}))}")
    print(f"- Marge elevee (>= {_fmt_margin(PRICING_HIGH_MARGIN)}): {_short_stat(report.get('high_margin', {}))}")

    print("\nComparaison cotes brutes vs probabilite no-vig")
    comparison = report.get("comparison") or {}
    if comparison:
        for market, stat in comparison.items():
            if not stat.get("picks"):
                continue
            print(
                f"- {market}: n={stat.get('picks', 0)}, "
                f"cote brute moy={_fmt_decimal(stat.get('average_raw_odds'))}, "
                f"proba implicite={_fmt_margin(stat.get('average_implied_probability'))}, "
                f"proba no-vig={_fmt_margin(stat.get('average_no_vig_probability'))}, "
                f"ecart={_fmt_margin(stat.get('average_probability_gap'))}, "
                f"cote juste marche={_fmt_decimal(stat.get('average_fair_odds_market'))}, "
                f"EV baseline={_fmt_margin(stat.get('average_ev_market_baseline'))}"
            )
    else:
        print("- Aucune comparaison disponible.")

    print("\nMarches ou la marge est trop elevee")
    print(f"- Seuil: >= {_fmt_margin(report.get('too_high_threshold'))}")
    too_high = report.get("too_high_markets") or {}
    if too_high:
        for market, stat in too_high.items():
            print(
                f"- {market}: {_short_stat(stat)}, "
                f"marge moy={_fmt_margin(stat.get('average_margin'))}, "
                f"part du marche={_fmt_decimal(stat.get('share_of_market'), 1)}%"
            )
    else:
        print("- Aucun marche au-dessus du seuil.")
    print("- Note prudente: ce rapport nettoie le prix marche; il n'ajoute aucune selection automatique.")


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


def _print_favorite_entry(entry: Dict[str, Any], prefix: str = "  - ") -> None:
    print(f"{prefix}{entry['label']} [{entry['status']}]")
    print(f"{prefix}  train {_short_stat(entry['train'])}")
    print(f"{prefix}  validation {_short_stat(entry['validation'])}")
    print(f"{prefix}  test {_short_stat(entry['test'])}, wins={entry['test'].get('wins', 0)}, WR={_fmt_pct(entry['test'].get('winrate', 0))}, cote moy={entry['test'].get('average_odds', 0)}, DD={entry['test'].get('max_drawdown', 0)}")


def print_favorite_report(report: Dict[str, Any]) -> None:
    params = report["params"]
    print("Rapport favoris H2H Oracle Bot")
    print(f"- Scope: {report['scope']}")
    print(f"- Train: {params['train_from']} -> {params['train_to']}")
    print(f"- Validation: {params['validation_from']} -> {params['validation_to']}")
    print(f"- Test: {params['test_from']} -> fin")
    print("\nVue globale")
    _print_favorite_entry(report["overall"])
    for group in report.get("groups", []):
        print(f"\n{group['label']}")
        for entry in group.get("segments", []):
            _print_favorite_entry(entry)
    conclusion = report.get("conclusion", {})
    print("\nConclusion favoris H2H")
    best = conclusion.get("best_segments", [])
    invalidated = conclusion.get("invalidated_segments", [])
    avoid = conclusion.get("avoid_segments", [])
    if best:
        print("- Meilleurs segments observes:")
        for entry in best[:5]:
            print(f"  - {entry.get('group')}: {entry['label']} | test {_short_stat(entry['test'])} | statut={entry['status']}")
    else:
        print("- Aucun segment positif robuste detecte sur le test.")
    if invalidated:
        print("- Segments invalides train positif / test negatif:")
        for entry in invalidated[:5]:
            print(f"  - {entry.get('group')}: {entry['label']} | train {_short_stat(entry['train'])} | test {_short_stat(entry['test'])}")
    if avoid:
        print("- Segments a eviter:")
        for entry in avoid[:5]:
            print(f"  - {entry.get('group')}: {entry['label']} | test {_short_stat(entry['test'])} | statut={entry['status']}")
    print(f"- Recommandation prudente: {conclusion.get('recommendation', '')}")


def print_stability_report(report: Dict[str, Any]) -> None:
    params = report["params"]
    print("Rapport de stabilite annuelle Oracle Bot")
    print(f"- Scope: {report['scope']}")
    print(f"- Train: {params['train_from']} -> {params['train_to']}")
    print(f"- Validation: {params['validation_from']} -> {params['validation_to']}")
    print(f"- Test: {params['test_from']} -> fin")
    for strategy in report.get("strategies", []):
        score = strategy.get("score", {})
        print(f"\n{strategy['label']} [{strategy['stability_note']}]")
        print(f"- Train: {_short_stat(strategy['train'])}")
        print(f"- Validation: {_short_stat(strategy['validation'])}")
        print(f"- Test: {_short_stat(strategy['test'])}")
        print(
            "- Score stabilite: "
            f"annees positives={score.get('positive_years', 0)}, "
            f"annees negatives={score.get('negative_years', 0)}, "
            f"ROI annuel moyen={_fmt_pct(score.get('average_annual_roi', 0))}, "
            f"pire={score.get('worst_year', {}).get('year', '')} ({_fmt_pct(score.get('worst_year', {}).get('roi', 0))}), "
            f"meilleure={score.get('best_year', {}).get('year', '')} ({_fmt_pct(score.get('best_year', {}).get('roi', 0))}), "
            f"DD max={score.get('max_drawdown_observed', 0)}"
        )
        print("- Par annee:")
        for year, stat in sorted(strategy.get("annual", {}).items()):
            print(
                f"  - {year}: n={stat['picks']}, wins={stat['wins']}, WR={_fmt_pct(stat['winrate'])}, "
                f"ROI={_fmt_pct(stat['roi'])}, profit={stat['profit']}, cote moy={stat['average_odds']}, DD={stat['max_drawdown']}"
            )
    conclusion = report.get("conclusion", {})
    print("\nConclusion stabilite")
    candidates = conclusion.get("candidate_segments", [])
    observations = conclusion.get("observation_segments", [])
    degraded = conclusion.get("degraded_segments", [])
    negative = conclusion.get("negative_segments", [])
    if candidates:
        print("- Segments candidats coherents:")
        for strategy in candidates:
            print(f"  - {strategy['label']}: test {_short_stat(strategy['test'])}, note={strategy['stability_note']}")
    else:
        print("- Aucun segment candidat coherent train/validation/test/stabilite annuelle.")
    if observations:
        print("- Segments seulement en observation:")
        for strategy in observations[:5]:
            print(f"  - {strategy['label']}: test {_short_stat(strategy['test'])}, note={strategy['stability_note']}")
    if degraded:
        print("- Degradations recentes:")
        for strategy in degraded[:5]:
            print(f"  - {strategy['label']}: 2024 ROI={_fmt_pct(strategy.get('annual', {}).get('2024', {}).get('roi', 0))}, 2025 ROI={_fmt_pct(strategy.get('annual', {}).get('2025', {}).get('roi', 0))}")
    if negative:
        print("- Negatifs robustes:")
        for strategy in negative[:5]:
            print(f"  - {strategy['label']}: test {_short_stat(strategy['test'])}")
    print(f"- Recommandation prudente: {conclusion.get('recommendation', '')}")


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
    parser.add_argument("--favorite-report", action="store_true", help="Analyse locale detaillee des favoris H2H")
    parser.add_argument("--stability-report", action="store_true", help="Analyse la stabilite annuelle des strategies locales")
    parser.add_argument("--pricing-report", action="store_true", help="Analyse les marges marche, probabilites no-vig et ROI associe")
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
    if args.favorite_report:
        report = build_favorite_report(db)
        print_favorite_report(report)
        if args.json_path:
            write_json(report, args.json_path)
        return
    if args.stability_report:
        report = build_stability_report(db)
        print_stability_report(report)
        if args.json_path:
            write_json(report, args.json_path)
        return
    if args.pricing_report:
        report = build_pricing_report(db)
        print_pricing_report(report)
        if args.json_path:
            write_json(report, args.json_path)
        return
    report = evaluate_backtest(db, args.train_to, args.test_from, args.preset, debug_strategies=args.debug_strategies)
    print_report(report)
    if args.json_path:
        write_json(report, args.json_path)


if __name__ == "__main__":
    main()
