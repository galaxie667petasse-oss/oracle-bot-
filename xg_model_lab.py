import argparse
import csv
import html
import json
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


def match_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(row.get("date") or ""), str(row.get("home") or ""), str(row.get("away") or ""))


def unique_match_count(rows: Sequence[Dict[str, Any]]) -> int:
    return len({match_key(row) for row in rows})


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


def split_rows(
    rows: Iterable[Dict[str, Any]],
    train_to: str = "2022-12-31",
    validation_from: str = "2023-01-01",
    validation_to: str = "2023-12-31",
    test_from: str = "2024-01-01",
) -> Dict[str, List[Dict[str, Any]]]:
    splits = {"fit": [], "validation": [], "train": [], "test": [], "hors_split": []}
    for row in rows:
        date_key = str(row.get("date") or "")
        if date_key and date_key <= train_to:
            splits["fit"].append(row)
            splits["train"].append(row)
        elif validation_from <= date_key <= validation_to:
            splits["validation"].append(row)
            splits["train"].append(row)
        elif date_key >= test_from:
            splits["test"].append(row)
        else:
            splits["hors_split"].append(row)
    if not splits["validation"]:
        splits["validation"] = list(splits["fit"])
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
        "unique_matches": unique_match_count(rows),
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
        "unique_matches": unique_match_count(rows),
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
        return threshold, "seuil choisi sur validation interne, pas sur test; aucun seuil robuste"
    return None, "seuil choisi sur validation interne, pas sur test; aucun edge positif"


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


def split_summary(splits: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, int]]:
    return {
        key: {"rows": len(value), "unique_matches": unique_match_count(value)}
        for key, value in splits.items()
    }


def compare_models(report: Dict[str, Any], base: Dict[str, Any], with_xg: Dict[str, Any]) -> Dict[str, Any]:
    market_test = report["market_baseline"]["test"]
    base_test = base["test_metrics"]
    xg_test = with_xg["test_metrics"]
    return {
        "without_xg": base_test,
        "with_xg": xg_test,
        "market": market_test,
        "delta_brier_xg_vs_without_xg": round(xg_test["brier"] - base_test["brier"], 6),
        "delta_log_loss_xg_vs_without_xg": round(xg_test["log_loss"] - base_test["log_loss"], 6),
        "delta_brier_xg_vs_market": round(xg_test["brier"] - market_test["brier"], 6),
        "delta_log_loss_xg_vs_market": round(xg_test["log_loss"] - market_test["log_loss"], 6),
    }


def build_verdict(report: Dict[str, Any], with_xg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    comparison = report.get("comparison") or {}
    selected_test = with_xg.get("selected_test") if with_xg else summarize_bets([])
    xg_improves_brier = (comparison.get("delta_brier_xg_vs_without_xg") is not None and comparison.get("delta_brier_xg_vs_without_xg") < 0)
    xg_improves_log_loss = (comparison.get("delta_log_loss_xg_vs_without_xg") is not None and comparison.get("delta_log_loss_xg_vs_without_xg") < 0)
    xg_beats_market = (
        (comparison.get("delta_brier_xg_vs_market") is not None and comparison.get("delta_brier_xg_vs_market") <= 0)
        and (comparison.get("delta_log_loss_xg_vs_market") is not None and comparison.get("delta_log_loss_xg_vs_market") <= 0)
    )
    edge_test_positive = (selected_test or {}).get("roi", 0.0) > 0
    sample_test_sufficient = (selected_test or {}).get("picks", 0) >= 1000
    clv_available = False
    rejection_reasons = []
    if not clv_available:
        rejection_reasons.append("CLV absente")
    if not edge_test_positive:
        rejection_reasons.append("ROI edge test non positif")
    if not sample_test_sufficient:
        rejection_reasons.append("sample edge test inferieur a 1000")
    if not xg_beats_market:
        rejection_reasons.append("Brier/log loss xG ne battent pas clairement le marche")
    promotion_allowed = False
    if xg_improves_brier and not edge_test_positive:
        note = "observation technique: Brier ameliore legerement, mais ROI test non positif ou non prouve."
    else:
        note = "laboratoire xG uniquement; promotion bloquee sans preuve complete et CLV positive."
    return {
        "xg_improves_brier": bool(xg_improves_brier),
        "xg_improves_log_loss": bool(xg_improves_log_loss),
        "edge_test_positive": bool(edge_test_positive),
        "sample_test_sufficient": bool(sample_test_sufficient),
        "clv_available": clv_available,
        "promotion_allowed": promotion_allowed,
        "selected_test": selected_test or summarize_bets([]),
        "rejection_reasons": rejection_reasons,
        "governance_note": note,
    }


def build_xg_model_report(
    features_path: str,
    train_to: str = "2022-12-31",
    validation_from: str = "2023-01-01",
    validation_to: str = "2023-12-31",
    test_from: str = "2024-01-01",
) -> Dict[str, Any]:
    raw_rows = read_rows(features_path)
    rows = usable_rows(raw_rows)
    splits = split_rows(rows, train_to=train_to, validation_from=validation_from, validation_to=validation_to, test_from=test_from)
    market_validation = market_probabilities(splits["validation"])
    market_test = market_probabilities(splits["test"])
    dates = [str(row.get("date") or "") for row in rows if str(row.get("date") or "")]
    unique_matches = unique_match_count(rows)
    report = {
        "features_path": features_path,
        "rows_total": len(raw_rows),
        "rows_with_rolling_xg": len(rows),
        "unique_matches_with_rolling_xg": unique_matches,
        "candidates_per_match_avg": round(len(rows) / unique_matches, 4) if unique_matches else 0.0,
        "date_min": min(dates) if dates else "",
        "date_max": max(dates) if dates else "",
        "split_config": {
            "train_to": train_to,
            "validation_from": validation_from,
            "validation_to": validation_to,
            "test_from": test_from,
        },
        "splits": {key: len(value) for key, value in splits.items()},
        "split_unique_matches": {key: unique_match_count(value) for key, value in splits.items()},
        "split_detail": split_summary(splits),
        "market_baseline": {
            "validation": metric_block(splits["validation"], market_validation),
            "test": metric_block(splits["test"], market_test),
        },
        "models": [],
        "notes": ["seuil choisi sur validation interne, pas sur test"],
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
            "test_period": f"{test_from} -> fin",
        }
        report["verdict"] = build_verdict(report)
        return report
    try:
        base = evaluate_model("Modele sans xG", splits["fit"], splits["validation"], splits["test"], BASE_FEATURES)
        with_xg = evaluate_model("Modele avec rolling xG", splits["fit"], splits["validation"], splits["test"], BASE_FEATURES + XG_FEATURES)
        report["models"] = [base, with_xg]
        report["comparison"] = compare_models(report, base, with_xg)
        report["verdict"] = build_verdict(report, with_xg)
        report["governance_metrics"] = {
            "validation": with_xg["selected_validation"],
            "test": with_xg["selected_test"],
            "probability_metrics": {
                "brier": with_xg["test_metrics"]["brier"],
                "log_loss": with_xg["test_metrics"]["log_loss"],
                "brier_test": with_xg["test_metrics"]["brier"],
                "market_brier_test": report["market_baseline"]["test"]["brier"],
                "log_loss_test": with_xg["test_metrics"]["log_loss"],
                "market_log_loss_test": report["market_baseline"]["test"]["log_loss"],
            },
            "post_match_features_allowed": False,
            "leak_risk": "controlled_rolling",
            "features_used": ["rolling_xg_avg3_avg5", "market_no_vig"],
            "test_period": f"{test_from} -> fin",
        }
        report["conclusion"] = report["verdict"]["governance_note"]
    except Exception as exc:
        report["error"] = f"Modele xG indisponible: {exc}"
        report["governance_metrics"] = {
            "validation": summarize_bets([]),
            "test": summarize_bets([]),
            "post_match_features_allowed": False,
            "leak_risk": "controlled_rolling",
            "features_used": ["rolling_xg_erreur"],
            "test_period": f"{test_from} -> fin",
        }
        report["verdict"] = build_verdict(report)
    return report


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    comparison = report.get("comparison") or {}
    verdict = report.get("verdict") or {}
    rows = [
        ("Lignes totales", report.get("rows_total")),
        ("Lignes rolling xG", report.get("rows_with_rolling_xg")),
        ("Matchs uniques", report.get("unique_matches_with_rolling_xg")),
        ("Brier marche", ((report.get("market_baseline") or {}).get("test") or {}).get("brier")),
        ("Brier sans xG", (comparison.get("without_xg") or {}).get("brier")),
        ("Brier avec xG", (comparison.get("with_xg") or {}).get("brier")),
        ("Delta Brier xG vs marche", comparison.get("delta_brier_xg_vs_market")),
        ("ROI edge test", (verdict.get("selected_test") or {}).get("roi")),
        ("Promotion allowed", verdict.get("promotion_allowed")),
    ]
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>xG Model Lab</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}</style>",
        "</head><body><h1>xG Model Lab</h1>",
        "<table><thead><tr><th>Mesure</th><th>Valeur</th></tr></thead><tbody>",
        *[f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>" for key, value in rows],
        "</tbody></table>",
        f"<p>{html.escape(str(verdict.get('governance_note') or report.get('conclusion') or 'observation seulement'))}</p>",
        "<p>Aucun pick automatique, seuil choisi sur validation interne, pas sur test.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


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


def print_report(report: Dict[str, Any]) -> None:
    print("xG Model Lab Oracle Bot")
    print(f"- Features: {report.get('features_path')}")
    print(f"- Lignes totales: {report.get('rows_total', 0)}")
    print(f"- Lignes avec rolling xG: {report.get('rows_with_rolling_xg', 0)}")
    print(f"- Matchs uniques avec rolling xG: {report.get('unique_matches_with_rolling_xg', 0)}")
    print(f"- Candidats par match moyen: {report.get('candidates_per_match_avg')}")
    print(f"- Periode: {report.get('date_min') or 'n/a'} -> {report.get('date_max') or 'n/a'}")
    print(f"- Split lignes: {report.get('splits', {})}")
    print(f"- Split matchs uniques: {report.get('split_unique_matches', {})}")
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
    comparison = report.get("comparison") or {}
    if comparison:
        print("- Comparaison test:")
        print(f"  - Delta Brier xG vs sans xG: {comparison.get('delta_brier_xg_vs_without_xg')}")
        print(f"  - Delta log loss xG vs sans xG: {comparison.get('delta_log_loss_xg_vs_without_xg')}")
        print(f"  - Delta Brier xG vs marche: {comparison.get('delta_brier_xg_vs_market')}")
        print(f"  - Delta log loss xG vs marche: {comparison.get('delta_log_loss_xg_vs_market')}")
    verdict = report.get("verdict") or {}
    print(f"- Promotion allowed: {verdict.get('promotion_allowed')}")
    print(f"- Raisons de rejet: {', '.join(verdict.get('rejection_reasons') or []) or 'aucune'}")
    print(f"- Conclusion prudente: {report.get('conclusion') or verdict.get('governance_note') or 'observation seulement'}")
    print("- Rappel: seuil choisi sur validation interne, pas sur test; aucun pick Telegram n'est modifie.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Evalue localement les rolling features xG, sans API ni Telegram.")
    parser.add_argument("--features", required=True, help="CSV rolling xG produit dans reports/")
    parser.add_argument("--train-to", default="2022-12-31", help="Fin train")
    parser.add_argument("--validation-from", default="2023-01-01", help="Debut validation")
    parser.add_argument("--validation-to", default="2023-12-31", help="Fin validation")
    parser.add_argument("--test-from", default="2024-01-01", help="Debut test")
    parser.add_argument("--output", default="", help="Rapport JSON dans reports/")
    parser.add_argument("--html", default="", help="Rapport HTML dans reports/")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_xg_model_report(
            args.features,
            train_to=args.train_to,
            validation_from=args.validation_from,
            validation_to=args.validation_to,
            test_from=args.test_from,
        )
        if args.output:
            path = write_json(report, args.output)
            print(f"- Rapport JSON xG model ecrit: {path}")
        if args.html:
            path = write_html(report, args.html)
            print(f"- Rapport HTML xG model ecrit: {path}")
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
