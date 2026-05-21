import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import numpy as np
except Exception:
    np = None


NUMERIC_FEATURES = [
    "odds",
    "implied_probability",
    "no_vig_probability",
    "market_margin",
    "fair_odds_market",
    "ev_market_baseline",
    "home_elo",
    "away_elo",
    "elo_diff",
    "elo_abs_diff",
    "form3_home",
    "form3_away",
    "form3_diff",
    "form5_home",
    "form5_away",
    "form5_diff",
]

BINARY_FEATURES = [
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
]

CATEGORICAL_FEATURES = ["market_type", "odds_bucket", "elo_bucket", "competition"]
EDGE_THRESHOLDS = [0.01, 0.02, 0.03, 0.05]
CALIBRATION_BUCKETS = [
    (0.40, 0.45, "0.40-0.45"),
    (0.45, 0.50, "0.45-0.50"),
    (0.50, 0.55, "0.50-0.55"),
    (0.55, 0.60, "0.55-0.60"),
    (0.60, 0.65, "0.60-0.65"),
    (0.65, 1.01, "0.65+"),
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


def _date_key(row: Dict[str, Any]) -> str:
    return str(row.get("date") or row.get("date_key") or "")


def split_name(date_key: str) -> str:
    if "2015-01-01" <= date_key <= "2022-12-31":
        return "train"
    if "2023-01-01" <= date_key <= "2023-12-31":
        return "validation"
    if date_key >= "2024-01-01":
        return "test"
    return "hors_split"


def read_feature_rows(path: str, market: str = "") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if market and row.get("market_type") != market:
                continue
            if row.get("result") not in ("win", "loss"):
                continue
            if _num(row.get("target_win")) is None:
                row["target_win"] = "1" if row.get("result") == "win" else "0"
            rows.append(row)
    return rows


def usable_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    usable = []
    for row in rows:
        if split_name(_date_key(row)) == "hors_split":
            continue
        if _num(row.get("target_win")) is None:
            continue
        if _num(row.get("odds")) is None:
            continue
        if _num(row.get("no_vig_probability")) is None:
            continue
        usable.append(row)
    return usable


def temporal_split(rows: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    splits = {"train": [], "validation": [], "test": [], "hors_split": []}
    for row in rows:
        splits[split_name(_date_key(row))].append(row)
    return splits


@dataclass
class FeatureTransformer:
    numeric_medians: Dict[str, float]
    numeric_means: Dict[str, float]
    numeric_stds: Dict[str, float]
    categories: Dict[str, List[str]]
    feature_names: List[str]


def fit_feature_transformer(train_rows: List[Dict[str, Any]]) -> FeatureTransformer:
    if np is None:
        raise RuntimeError("numpy est requis pour entrainer le modele local.")
    numeric_medians: Dict[str, float] = {}
    numeric_means: Dict[str, float] = {}
    numeric_stds: Dict[str, float] = {}
    for column in NUMERIC_FEATURES:
        values = [_num(row.get(column)) for row in train_rows]
        clean = np.asarray([value for value in values if value is not None], dtype=np.float32)
        median = float(np.median(clean)) if clean.size else 0.0
        filled = np.asarray([value if value is not None else median for value in values], dtype=np.float32)
        mean = float(np.mean(filled)) if filled.size else 0.0
        std = float(np.std(filled)) if filled.size else 1.0
        if std <= 1e-9:
            std = 1.0
        numeric_medians[column] = median
        numeric_means[column] = mean
        numeric_stds[column] = std

    categories: Dict[str, List[str]] = {}
    for column in CATEGORICAL_FEATURES:
        values = sorted({str(row.get(column) or "inconnu") for row in train_rows})
        categories[column] = values

    feature_names = list(NUMERIC_FEATURES) + list(BINARY_FEATURES)
    for column in CATEGORICAL_FEATURES:
        feature_names.extend([f"{column}={value}" for value in categories[column]])
    return FeatureTransformer(numeric_medians, numeric_means, numeric_stds, categories, feature_names)


def transform_rows(rows: List[Dict[str, Any]], transformer: FeatureTransformer):
    if np is None:
        raise RuntimeError("numpy est requis pour entrainer le modele local.")
    matrix = np.zeros((len(rows), len(transformer.feature_names)), dtype=np.float32)
    for row_index, row in enumerate(rows):
        col_index = 0
        for column in NUMERIC_FEATURES:
            value = _num(row.get(column))
            if value is None:
                value = transformer.numeric_medians[column]
            matrix[row_index, col_index] = (float(value) - transformer.numeric_means[column]) / transformer.numeric_stds[column]
            col_index += 1
        for column in BINARY_FEATURES:
            matrix[row_index, col_index] = 1.0 if _num(row.get(column)) and _num(row.get(column)) > 0 else 0.0
            col_index += 1
        for column in CATEGORICAL_FEATURES:
            value = str(row.get(column) or "inconnu")
            for category in transformer.categories[column]:
                matrix[row_index, col_index] = 1.0 if value == category else 0.0
                col_index += 1
    target = np.asarray([1.0 if _num(row.get("target_win")) and _num(row.get("target_win")) >= 0.5 else 0.0 for row in rows], dtype=np.float32)
    return matrix, target


class LocalLogisticRegression:
    def __init__(self, learning_rate: float = 0.12, iterations: int = 80, l2: float = 0.001):
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.l2 = l2
        self.weights = None
        self.bias = 0.0

    @staticmethod
    def _sigmoid(values):
        clipped = np.clip(values, -35.0, 35.0)
        return 1.0 / (1.0 + np.exp(-clipped))

    def fit(self, x_train, y_train):
        n_rows, n_cols = x_train.shape
        self.weights = np.zeros(n_cols, dtype=np.float32)
        self.bias = 0.0
        for _ in range(self.iterations):
            probabilities = self._sigmoid(x_train @ self.weights + self.bias)
            errors = probabilities - y_train
            grad_w = (x_train.T @ errors) / max(1, n_rows) + self.l2 * self.weights
            grad_b = float(np.mean(errors)) if n_rows else 0.0
            self.weights -= self.learning_rate * grad_w
            self.bias -= self.learning_rate * grad_b
        return self

    def predict_proba(self, x_values):
        probabilities = self._sigmoid(x_values @ self.weights + self.bias)
        return probabilities.astype(np.float32)


def sklearn_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False


def train_models(x_train, y_train) -> Tuple[List[Tuple[str, Any]], List[str]]:
    notes: List[str] = []
    unique_classes = set(float(value) for value in y_train.tolist())
    if len(unique_classes) < 2:
        return [], ["Train inutilisable: une seule classe cible est presente."]

    models: List[Tuple[str, Any]] = []
    if sklearn_available():
        from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        models.append(("Regression logistique", LogisticRegression(max_iter=300, C=0.5)))
        models.append(("Random forest leger", RandomForestClassifier(n_estimators=60, max_depth=4, min_samples_leaf=80, max_samples=0.35, n_jobs=-1, random_state=42)))
        models.append(("Gradient boosting leger", HistGradientBoostingClassifier(max_iter=60, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=80, random_state=42)))
    else:
        notes.append("sklearn indisponible: random forest et gradient boosting ignores; regression logistique locale utilisee.")
        models.append(("Regression logistique locale", LocalLogisticRegression()))

    fitted: List[Tuple[str, Any]] = []
    for name, model in models:
        model.fit(x_train, y_train)
        fitted.append((name, model))
    return fitted, notes


def predict_probability(model: Any, x_values):
    probabilities = model.predict_proba(x_values)
    if hasattr(probabilities, "ndim") and probabilities.ndim == 2:
        return probabilities[:, 1].astype(np.float32)
    return probabilities.astype(np.float32)


def brier_score(y_true, probabilities) -> float:
    if len(y_true) == 0:
        return 0.0
    return float(np.mean((probabilities - y_true) ** 2))


def log_loss_score(y_true, probabilities) -> float:
    if len(y_true) == 0:
        return 0.0
    clipped = np.clip(probabilities, 1e-6, 1.0 - 1e-6)
    return float(-np.mean(y_true * np.log(clipped) + (1.0 - y_true) * np.log(1.0 - clipped)))


def accuracy_score_local(y_true, probabilities) -> float:
    if len(y_true) == 0:
        return 0.0
    return float(np.mean((probabilities >= 0.5) == (y_true >= 0.5)))


def market_probabilities(rows: List[Dict[str, Any]]):
    return np.asarray([_num(row.get("no_vig_probability")) or 0.0 for row in rows], dtype=np.float32)


def metrics_for(rows: List[Dict[str, Any]], y_true, probabilities) -> Dict[str, float]:
    return {
        "n": len(rows),
        "brier": round(brier_score(y_true, probabilities), 6),
        "log_loss": round(log_loss_score(y_true, probabilities), 6),
        "accuracy": round(accuracy_score_local(y_true, probabilities) * 100.0, 2),
    }


def unit_profit(row: Dict[str, Any]) -> float:
    odds = _num(row.get("odds")) or 1.0
    return odds - 1.0 if row.get("target_win") in ("1", 1, 1.0) or row.get("result") == "win" else -1.0


def max_drawdown(rows: Sequence[Dict[str, Any]]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for row in sorted(rows, key=_date_key):
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
        "winrate": round(wins / n * 100.0, 1) if n else 0.0,
        "roi": round(profit / n * 100.0, 2) if n else 0.0,
        "profit": profit,
        "drawdown": max_drawdown(rows),
        "average_odds": round(sum(odds_clean) / len(odds_clean), 3) if odds_clean else 0.0,
    }


def _group_summary(rows: Sequence[Dict[str, Any]], key_fn) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(key_fn(row)), []).append(row)
    return {key: summarize_bets(items) for key, items in sorted(groups.items())}


def edge_simulation(rows: List[Dict[str, Any]], probabilities, thresholds: Sequence[float] = EDGE_THRESHOLDS) -> Dict[float, Dict[str, Any]]:
    out: Dict[float, Dict[str, Any]] = {}
    for threshold in thresholds:
        selected = []
        for row, probability in zip(rows, probabilities):
            baseline = _num(row.get("no_vig_probability"))
            if baseline is None:
                continue
            if float(probability) - baseline > threshold:
                selected.append(row)
        stat = summarize_bets(selected)
        stat["by_market"] = _group_summary(selected, lambda row: row.get("market_type") or "?")
        stat["by_year"] = _group_summary(selected, lambda row: _date_key(row)[:4] or "inconnue")
        out[threshold] = stat
    return out


def choose_threshold_on_validation(validation_simulation: Dict[float, Dict[str, Any]]) -> Tuple[Optional[float], str]:
    candidates = [
        (threshold, stat) for threshold, stat in validation_simulation.items()
        if stat.get("picks", 0) >= 300 and stat.get("roi", 0.0) > 0
    ]
    if candidates:
        threshold, _stat = max(candidates, key=lambda item: (item[1].get("roi", 0.0), item[1].get("picks", 0)))
        return threshold, "seuil choisi sur validation avec ROI positif et volume >= 300"
    non_empty = [(threshold, stat) for threshold, stat in validation_simulation.items() if stat.get("picks", 0) > 0]
    if non_empty:
        threshold, _stat = max(non_empty, key=lambda item: (item[1].get("roi", -9999.0), item[1].get("picks", 0)))
        return threshold, "aucun seuil validation robuste; meilleur seuil validation affiche seulement une observation"
    return None, "aucun edge positif sur validation"


def calibration_buckets(rows: List[Dict[str, Any]], probabilities) -> List[Dict[str, Any]]:
    buckets: List[Dict[str, Any]] = []
    for low, high, label in CALIBRATION_BUCKETS:
        selected = [
            (row, float(probability)) for row, probability in zip(rows, probabilities)
            if float(probability) >= low and float(probability) < high
        ]
        selected_rows = [row for row, _probability in selected]
        predicted = [probability for _row, probability in selected]
        stat = summarize_bets(selected_rows)
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


def calibration_gap(buckets: Sequence[Dict[str, Any]]) -> float:
    total = sum(int(bucket.get("n", 0)) for bucket in buckets)
    if total == 0:
        return 0.0
    return sum(float(bucket.get("gap", 0.0)) * int(bucket.get("n", 0)) for bucket in buckets) / total


def edge_signal_note(validation_stat: Dict[str, Any], test_stat: Dict[str, Any]) -> str:
    if test_stat.get("picks", 0) < 300:
        return "echantillon faible"
    if validation_stat.get("roi", 0.0) > 0 and test_stat.get("roi", 0.0) < 0:
        return "signal invalide"
    if test_stat.get("roi", 0.0) > 0 and validation_stat.get("roi", 0.0) <= 0:
        return "signal suspect"
    if 0 < test_stat.get("roi", 0.0) < 1:
        return "observation seulement"
    if validation_stat.get("roi", 0.0) > 0 and test_stat.get("roi", 0.0) > 0:
        return "positif a confirmer, non jouable automatiquement"
    return "negatif ou non confirme"


def model_conclusion(model_metrics: Dict[str, float], market_metrics: Dict[str, float], buckets: Sequence[Dict[str, Any]], selected_test: Dict[str, Any]) -> str:
    if selected_test.get("picks", 0) < 300:
        return "modele inutilisable (echantillon edge test faible)"
    gap = calibration_gap(buckets)
    if gap > 0.03:
        return "modele surconfiant"
    if gap < -0.03:
        return "modele sous-confiant"
    if model_metrics.get("brier", 9.0) >= market_metrics.get("brier", 0.0) and model_metrics.get("log_loss", 9.0) >= market_metrics.get("log_loss", 0.0):
        return "modele inutilisable"
    return "modele prometteur mais non jouable"


def evaluate_model(name: str, model: Any, splits: Dict[str, List[Dict[str, Any]]], matrices: Dict[str, Any], targets: Dict[str, Any]) -> Dict[str, Any]:
    probabilities = {
        split: predict_probability(model, matrices[split])
        for split in ("validation", "test")
    }
    market = {
        split: market_probabilities(splits[split])
        for split in ("validation", "test")
    }
    model_metrics = {
        split: metrics_for(splits[split], targets[split], probabilities[split])
        for split in ("validation", "test")
    }
    market_metrics = {
        split: metrics_for(splits[split], targets[split], market[split])
        for split in ("validation", "test")
    }
    validation_edges = edge_simulation(splits["validation"], probabilities["validation"])
    test_edges = edge_simulation(splits["test"], probabilities["test"])
    threshold, threshold_reason = choose_threshold_on_validation(validation_edges)
    selected_validation = validation_edges.get(threshold, summarize_bets([])) if threshold is not None else summarize_bets([])
    selected_test = test_edges.get(threshold, summarize_bets([])) if threshold is not None else summarize_bets([])
    calibration = calibration_buckets(splits["test"], probabilities["test"])
    return {
        "name": name,
        "model_metrics": model_metrics,
        "market_metrics": market_metrics,
        "validation_edges": validation_edges,
        "test_edges": test_edges,
        "selected_threshold": threshold,
        "threshold_reason": threshold_reason,
        "selected_validation": selected_validation,
        "selected_test": selected_test,
        "calibration": calibration,
        "conclusion": model_conclusion(model_metrics["test"], market_metrics["test"], calibration, selected_test),
    }


def build_training_report(feature_path: str, market: str = "") -> Dict[str, Any]:
    if np is None:
        return {
            "error": "numpy est requis pour model_trainer.py. Installez numpy ou lancez dans l'environnement Codex.",
            "models": [],
        }
    rows = usable_rows(read_feature_rows(feature_path, market))
    splits = temporal_split(rows)
    transformer = fit_feature_transformer(splits["train"]) if splits["train"] else None
    if transformer is None:
        return {
            "error": "Train vide: impossible d'entrainer un modele local.",
            "rows": len(rows),
            "models": [],
        }
    matrices = {}
    targets = {}
    for split in ("train", "validation", "test"):
        matrices[split], targets[split] = transform_rows(splits[split], transformer)
    models, notes = train_models(matrices["train"], targets["train"])
    evaluations = [
        evaluate_model(name, model, splits, matrices, targets)
        for name, model in models
    ]
    return {
        "feature_path": feature_path,
        "market": market or "tous",
        "rows": len(rows),
        "splits": {key: len(value) for key, value in splits.items()},
        "feature_count": len(transformer.feature_names),
        "feature_names": transformer.feature_names,
        "notes": notes,
        "models": evaluations,
    }


def _fmt_pct(value: Any) -> str:
    return f"{(_num(value) or 0.0):.2f}%"


def _fmt_prob(value: Any) -> str:
    return f"{(_num(value) or 0.0):.4f}"


def print_metrics(label: str, model_stat: Dict[str, Any], market_stat: Dict[str, Any]) -> None:
    print(f"- {label}:")
    print(f"  - modele: n={model_stat.get('n', 0)}, Brier={model_stat.get('brier', 0)}, log loss={model_stat.get('log_loss', 0)}, accuracy={_fmt_pct(model_stat.get('accuracy', 0))}")
    print(f"  - marche no-vig: Brier={market_stat.get('brier', 0)}, log loss={market_stat.get('log_loss', 0)}, accuracy={_fmt_pct(market_stat.get('accuracy', 0))}")


def print_edge_table(title: str, simulation: Dict[float, Dict[str, Any]], paired: Optional[Dict[float, Dict[str, Any]]] = None) -> None:
    print(title)
    for threshold in EDGE_THRESHOLDS:
        stat = simulation.get(threshold, summarize_bets([]))
        suffix = ""
        if paired is not None:
            suffix = f", note={edge_signal_note(paired.get(threshold, {}), stat)}"
        print(
            f"- edge > {threshold:.2f}: picks={stat.get('picks', 0)}, WR={_fmt_pct(stat.get('winrate', 0))}, "
            f"ROI={_fmt_pct(stat.get('roi', 0))}, profit={stat.get('profit', 0)}, DD={stat.get('drawdown', 0)}, "
            f"cote moy={stat.get('average_odds', 0)}{suffix}"
        )
        by_market = stat.get("by_market") or {}
        if by_market:
            market_text = ", ".join(f"{key}: n={value.get('picks', 0)}, ROI={_fmt_pct(value.get('roi', 0))}" for key, value in by_market.items())
            print(f"  - par marche: {market_text}")
        by_year = stat.get("by_year") or {}
        if by_year:
            year_text = ", ".join(f"{key}: n={value.get('picks', 0)}, ROI={_fmt_pct(value.get('roi', 0))}" for key, value in by_year.items())
            print(f"  - par annee: {year_text}")


def print_calibration(buckets: Sequence[Dict[str, Any]]) -> None:
    print("Calibration test 2024+")
    for bucket in buckets:
        print(
            f"- {bucket['bucket']}: n={bucket['n']}, proba predite={_fmt_prob(bucket['predicted'])}, "
            f"taux reel={_fmt_prob(bucket['actual'])}, ecart={_fmt_prob(bucket['gap'])}, ROI={_fmt_pct(bucket['roi'])}"
        )


def print_report(report: Dict[str, Any]) -> None:
    print("Rapport ML leger Oracle Bot")
    if report.get("error"):
        print(f"- Erreur: {report['error']}")
        return
    print(f"- Features: {report.get('feature_path')}")
    print(f"- Marche filtre: {report.get('market')}")
    print(f"- Lignes utilisables: {report.get('rows', 0)}")
    splits = report.get("splits", {})
    print(f"- Split temporel: train={splits.get('train', 0)}, validation={splits.get('validation', 0)}, test={splits.get('test', 0)}")
    print(f"- Nombre de variables modele: {report.get('feature_count', 0)}")
    for note in report.get("notes") or []:
        print(f"- Note: {note}")
    if not report.get("models"):
        print("- Aucun modele entraine.")
        return
    print("- Rappel: le modele mesure une probabilite; il ne cree aucun pick automatique.")
    for model in report["models"]:
        print(f"\nModele: {model['name']}")
        print_metrics("Validation 2023", model["model_metrics"]["validation"], model["market_metrics"]["validation"])
        print_metrics("Test 2024+", model["model_metrics"]["test"], model["market_metrics"]["test"])
        print_calibration(model["calibration"])
        print_edge_table("Simulation edges validation", model["validation_edges"])
        print_edge_table("Simulation edges test", model["test_edges"], paired=model["validation_edges"])
        threshold = model.get("selected_threshold")
        if threshold is None:
            print(f"- Seuil validation retenu: aucun ({model.get('threshold_reason')})")
        else:
            print(f"- Seuil validation retenu: edge > {threshold:.2f} ({model.get('threshold_reason')})")
            print(f"  - validation: picks={model['selected_validation'].get('picks', 0)}, ROI={_fmt_pct(model['selected_validation'].get('roi', 0))}")
            print(f"  - test: picks={model['selected_test'].get('picks', 0)}, ROI={_fmt_pct(model['selected_test'].get('roi', 0))}, note={edge_signal_note(model['selected_validation'], model['selected_test'])}")
        print(f"- Conclusion prudente: {model['conclusion']}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Entraine un modele ML leger local sur la feature matrix, sans API ni Telegram.")
    parser.add_argument("--features", required=True, help="Chemin du CSV de features")
    parser.add_argument("--market", choices=["h2h", "total"], default="", help="Filtre optionnel de marche")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    report = build_training_report(args.features, args.market)
    print_report(report)


if __name__ == "__main__":
    main()
