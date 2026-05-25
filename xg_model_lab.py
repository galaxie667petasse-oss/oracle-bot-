import argparse
import csv
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


EDGE_THRESHOLDS = [0.01, 0.02, 0.03, 0.05]
CALIBRATION_BUCKETS = [
    (0.40, 0.45, "0.40-0.45"),
    (0.45, 0.50, "0.45-0.50"),
    (0.50, 0.55, "0.50-0.55"),
    (0.55, 0.60, "0.55-0.60"),
    (0.60, 0.65, "0.60-0.65"),
    (0.65, 1.01, "0.65+"),
]
BASE_FEATURES = [
    "odds",
    "no_vig_probability",
    "implied_probability",
    "market_margin",
    "elo_diff",
    "elo_abs_diff",
    "form3_diff",
    "form5_diff",
]
XG_FEATURES = [
    "home_xg_for_avg3",
    "home_xg_for_avg5",
    "home_xg_against_avg3",
    "home_xg_against_avg5",
    "away_xg_for_avg3",
    "away_xg_for_avg5",
    "away_xg_against_avg3",
    "away_xg_against_avg5",
    "xg_diff_avg3",
    "xg_diff_avg5",
    "home_xg_trend_3_vs_5",
    "away_xg_trend_3_vs_5",
    "home_xg_matches_available",
    "away_xg_matches_available",
]


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def read_rows(path: str) -> List[Dict[str, Any]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def usable_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("result") not in ("win", "loss"):
            continue
        if _num(row.get("odds")) is None or _num(row.get("no_vig_probability")) is None:
            continue
        if _num(row.get("xg_diff_avg3")) is None:
            continue
        if _num(row.get("home_xg_for_avg3")) is None or _num(row.get("away_xg_for_avg3")) is None:
            continue
        row = dict(row)
        row["target_win"] = "1" if row.get("result") == "win" else "0"
        out.append(row)
    return out


def split_rows(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    splits = {"fit": [], "validation": [], "train": [], "test": [], "hors_split": []}
    for row in rows:
        date_key = str(row.get("date") or "")
        if "2024-08-16" <= date_key <= "2024-11-30":
            splits["fit"].append(row)
            splits["train"].append(row)
        elif "2024-12-01" <= date_key <= "2024-12-31":
            splits["validation"].append(row)
            splits["train"].append(row)
        elif "2025-01-01" <= date_key <= "2025-05-25":
            splits["test"].append(row)
        else:
            splits["hors_split"].append(row)
    if not splits["fit"] or len({row["target_win"] for row in splits["fit"]}) < 2:
        splits["fit"] = list(splits["train"])
    if not splits["validation"]:
        splits["validation"] = list(splits["train"])
    return splits


def unit_profit(row: Dict[str, Any]) -> float:
    odds = _num(row.get("odds")) or 1.0
    return odds - 1.0 if row.get("result") == "win" or str(row.get("target_win")) == "1" else -1.0


def max_drawdown(rows: Sequence[Dict[str, Any]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for row in sorted(rows, key=lambda item: str(item.get("date") or "")):
        cumulative += unit_profit(row)
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return round(drawdown, 2)


def summarize_bets(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    wins = sum(1 for row in rows if row.get("result") == "win" or str(row.get("target_win")) == "1")
    profit = round(sum(unit_profit(row) for row in rows), 2)
    odds_values = [_num(row.get("odds")) for row in rows]
    odds_clean = [value for value in odds_values if value is not None]
    return {
        "picks": n,
        "wins": wins,
        "winrate": round(wins / n * 100.0, 2) if n else 0.0,
        "roi": round(profit / n * 100.0, 2) if n else 0.0,
        "profit": profit,
        "drawdown": max_drawdown(rows),
        "average_odds": round(sum(odds_clean) / len(odds_clean), 3) if odds_clean else 0.0,
    }


def brier_score(y_true: Sequence[float], probabilities: Sequence[float]) -> float:
    if not y_true:
        return 0.0
    return sum((p - y) ** 2 for p, y in zip(probabilities, y_true)) / len(y_true)


def log_loss_score(y_true: Sequence[float], probabilities: Sequence[float]) -> float:
    if not y_true:
        return 0.0
    total = 0.0
    for y, probability in zip(y_true, probabilities):
        p = min(1.0 - 1e-6, max(1e-6, probability))
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(y_true)


def market_probabilities(rows: Sequence[Dict[str, Any]]) -> List[float]:
    return [max(0.0, min(1.0, _num(row.get("no_vig_probability")) or 0.0)) for row in rows]


def target_values(rows: Sequence[Dict[str, Any]]) -> List[float]:
    return [1.0 if row.get("result") == "win" or str(row.get("target_win")) == "1" else 0.0 for row in rows]


def metric_block(rows: Sequence[Dict[str, Any]], probabilities: Sequence[float]) -> Dict[str, Any]:
    y_true = target_values(rows)
    return {
        "n": len(rows),
        "brier": round(brier_score(y_true, probabilities), 6),
        "log_loss": round(log_loss_score(y_true, probabilities), 6),
    }


def edge_simulation(rows: Sequence[Dict[str, Any]], probabilities: Sequence[float]) -> Dict[float, Dict[str, Any]]:
    out: Dict[float, Dict[str, Any]] = {}
    for threshold in EDGE_THRESHOLDS:
        selected = []
        for row, probability in zip(rows, probabilities):
            baseline = _num(row.get("no_vig_probability"))
            if baseline is None:
                continue
            if probability - baseline > threshold:
                selected.append(row)
        out[threshold] = summarize_bets(selected)
    return out


def choose_threshold(validation_edges: Dict[float, Dict[str, Any]]) -> Tuple[Optional[float], str]:
    candidates = [
        (threshold, stat) for threshold, stat in validation_edges.items()
        if stat.get("picks", 0) >= 30 and stat.get("roi", 0.0) > 0
    ]
    if candidates:
        threshold, _stat = max(candidates, key=lambda item: (item[1]["roi"], item[1]["picks"]))
        return threshold, "seuil choisi sur validation interne, pas sur test"
    non_empty = [(threshold, stat) for threshold, stat in validation_edges.items() if stat.get("picks", 0) > 0]
    if non_empty:
        threshold, _stat = max(non_empty, key=lambda item: (item[1]["roi"], item[1]["picks"]))
        return threshold, "aucun seuil robuste; meilleur seuil validation conserve en observation"
    return None, "aucun edge positif sur validation interne"


def calibration_buckets(rows: Sequence[Dict[str, Any]], probabilities: Sequence[float]) -> List[Dict[str, Any]]:
    buckets = []
    for low, high, label in CALIBRATION_BUCKETS:
        pairs = [(row, p) for row, p in zip(rows, probabilities) if low <= p < high]
        selected = [row for row, _p in pairs]
        predicted = [p for _row, p in pairs]
        stat = summarize_bets(selected)
        actual = stat["winrate"] / 100.0 if stat["picks"] else 0.0
        avg_predicted = sum(predicted) / len(predicted) if predicted else 0.0
        buckets.append({
            "bucket": label,
            "n": stat["picks"],
            "predicted": round(avg_predicted, 4),
            "actual": round(actual, 4),
            "gap": round(avg_predicted - actual, 4),
            "roi": stat["roi"],
        })
    return buckets


def sklearn_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False


def _matrix(rows: Sequence[Dict[str, Any]], features: Sequence[str]) -> Tuple[List[List[float]], List[float]]:
    matrix = []
    for row in rows:
        matrix.append([_num(row.get(feature)) if _num(row.get(feature)) is not None else float("nan") for feature in features])
    return matrix, target_values(rows)


def train_predict(fit_rows: Sequence[Dict[str, Any]], predict_rows: Sequence[Dict[str, Any]], features: Sequence[str]) -> List[float]:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    x_fit, y_fit = _matrix(fit_rows, features)
    x_predict, _y_predict = _matrix(predict_rows, features)
    if len(set(y_fit)) < 2:
        raise ValueError("train interne inutilisable: une seule classe cible.")
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=300, C=0.5))
    model.fit(x_fit, y_fit)
    return [float(item[1]) for item in model.predict_proba(x_predict)]


def evaluate_model(label: str, fit_rows: List[Dict[str, Any]], validation_rows: List[Dict[str, Any]], test_rows: List[Dict[str, Any]], features: Sequence[str]) -> Dict[str, Any]:
    validation_prob = train_predict(fit_rows, validation_rows, features)
    test_prob = train_predict(fit_rows, test_rows, features)
    validation_edges = edge_simulation(validation_rows, validation_prob)
    test_edges = edge_simulation(test_rows, test_prob)
    threshold, reason = choose_threshold(validation_edges)
    selected_validation = validation_edges.get(threshold, summarize_bets([])) if threshold is not None else summarize_bets([])
    selected_test = test_edges.get(threshold, summarize_bets([])) if threshold is not None else summarize_bets([])
    return {
        "label": label,
        "features": list(features),
        "validation_metrics": metric_block(validation_rows, validation_prob),
        "test_metrics": metric_block(test_rows, test_prob),
        "validation_edges": validation_edges,
        "test_edges": test_edges,
        "selected_threshold": threshold,
        "threshold_reason": reason,
        "selected_validation": selected_validation,
        "selected_test": selected_test,
        "calibration": calibration_buckets(test_rows, test_prob),
    }


def build_xg_model_report(features_path: str) -> Dict[str, Any]:
    raw_rows = read_rows(features_path)
    rows = usable_rows(raw_rows)
    splits = split_rows(rows)
    market_validation = market_probabilities(splits["validation"])
    market_test = market_probabilities(splits["test"])
    report = {
        "features_path": features_path,
        "rows_total": len(raw_rows),
        "rows_with_rolling_xg": len(rows),
        "unique_matches_with_rolling_xg": len({(row.get("date"), row.get("home"), row.get("away")) for row in rows}),
        "splits": {key: len(value) for key, value in splits.items()},
        "market_baseline": {
            "validation": metric_block(splits["validation"], market_validation),
            "test": metric_block(splits["test"], market_test),
        },
        "models": [],
        "notes": [],
    }
    if len(splits["test"]) < 300:
        report["notes"].append("Echantillon test inferieur a 300 lignes candidates: observation seulement.")
    if not sklearn_available():
        report["error"] = "sklearn indisponible: regression logistique xG ignoree; rapport descriptif seulement."
        report["governance_metrics"] = {
            "validation": summarize_bets([]),
            "test": summarize_bets([]),
            "post_match_features_allowed": False,
            "leak_risk": "controlled_rolling",
            "features_used": ["rolling_xg_descriptif"],
            "test_period": "2025-01-01 -> 2025-05-25",
        }
        return report
    try:
        base = evaluate_model("Modele sans xG", splits["fit"], splits["validation"], splits["test"], BASE_FEATURES)
        with_xg = evaluate_model("Modele avec rolling xG", splits["fit"], splits["validation"], splits["test"], BASE_FEATURES + XG_FEATURES)
        report["models"] = [base, with_xg]
        report["governance_metrics"] = {
            "validation": with_xg["selected_validation"],
            "test": with_xg["selected_test"],
            "probability_metrics": {
                "brier_test": with_xg["test_metrics"]["brier"],
                "market_brier_test": report["market_baseline"]["test"]["brier"],
                "log_loss_test": with_xg["test_metrics"]["log_loss"],
                "market_log_loss_test": report["market_baseline"]["test"]["log_loss"],
            },
            "post_match_features_allowed": False,
            "leak_risk": "controlled_rolling",
            "features_used": ["rolling_xg_avg3_avg5", "market_no_vig"],
            "test_period": "2025-01-01 -> 2025-05-25",
        }
        xg_brier = with_xg["test_metrics"]["brier"]
        base_brier = base["test_metrics"]["brier"]
        market_brier = report["market_baseline"]["test"]["brier"]
        if xg_brier < base_brier and xg_brier < market_brier:
            report["conclusion"] = "xG ameliore le Brier sur test, observation seulement."
        else:
            report["conclusion"] = "xG n'ameliore pas clairement le modele ou le marche sur test."
        if with_xg["selected_test"].get("roi", 0.0) < 0:
            report["conclusion"] += " Signal edge invalide si ROI test negatif."
    except Exception as exc:
        report["error"] = f"Modele xG indisponible: {exc}"
        report["governance_metrics"] = {
            "validation": summarize_bets([]),
            "test": summarize_bets([]),
            "post_match_features_allowed": False,
            "leak_risk": "controlled_rolling",
            "features_used": ["rolling_xg_erreur"],
            "test_period": "2025-01-01 -> 2025-05-25",
        }
    return report


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def print_model(model: Dict[str, Any]) -> None:
    print(f"\n{model['label']}")
    print(f"- Variables: {len(model.get('features', []))}")
    print(f"- Validation: Brier={model['validation_metrics']['brier']}, log loss={model['validation_metrics']['log_loss']}")
    print(f"- Test: Brier={model['test_metrics']['brier']}, log loss={model['test_metrics']['log_loss']}")
    print(f"- Seuil retenu: {_fmt(model.get('selected_threshold'))} ({model.get('threshold_reason')})")
    print(f"- Edge validation retenu: picks={model['selected_validation']['picks']}, ROI={model['selected_validation']['roi']}%")
    print(f"- Edge test retenu: picks={model['selected_test']['picks']}, ROI={model['selected_test']['roi']}%, DD={model['selected_test']['drawdown']}")
    print("- Calibration test:")
    for bucket in model.get("calibration", []):
        print(f"  - {bucket['bucket']}: n={bucket['n']}, pred={bucket['predicted']}, reel={bucket['actual']}, ecart={bucket['gap']}, ROI={bucket['roi']}%")


def print_report(report: Dict[str, Any]) -> None:
    print("xG Model Lab Oracle Bot")
    print(f"- Features: {report.get('features_path')}")
    print(f"- Lignes totales: {report.get('rows_total', 0)}")
    print(f"- Lignes avec rolling xG: {report.get('rows_with_rolling_xg', 0)}")
    print(f"- Matchs uniques avec rolling xG: {report.get('unique_matches_with_rolling_xg', 0)}")
    splits = report.get("splits", {})
    print(f"- Split interne: train={splits.get('train', 0)}, validation={splits.get('validation', 0)}, test={splits.get('test', 0)}")
    market = report.get("market_baseline", {})
    print(f"- Marche no-vig validation: Brier={market.get('validation', {}).get('brier')}, log loss={market.get('validation', {}).get('log_loss')}")
    print(f"- Marche no-vig test: Brier={market.get('test', {}).get('brier')}, log loss={market.get('test', {}).get('log_loss')}")
    for note in report.get("notes", []):
        print(f"- Note: {note}")
    if report.get("error"):
        print(f"- Erreur non bloquante: {report['error']}")
        print("- Conclusion: rapport descriptif seulement, aucun signal promu.")
        return
    for model in report.get("models", []):
        print_model(model)
    print(f"- Conclusion prudente: {report.get('conclusion', 'observation seulement')}")
    print("- Rappel: le seuil n'est jamais choisi sur le test et aucun pick Telegram n'est modifie.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evalue localement les rolling features xG, sans API ni Telegram.")
    parser.add_argument("--features", required=True, help="CSV rolling xG produit dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        print_report(build_xg_model_report(args.features))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
