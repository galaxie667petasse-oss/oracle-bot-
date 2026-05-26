import argparse
import csv
import html
import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


RANDOM_SEED = 42


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text or text.lower() in {"na", "n/a", "nan", "none", "null", "-"}:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def parse_target(row: Dict[str, Any]) -> Optional[int]:
    for key in ("target_win", "is_win", "won"):
        if key in row:
            value = parse_float(row.get(key))
            if value is not None:
                return 1 if value >= 0.5 else 0
    result = str(row.get("result") or "").strip().lower()
    if result in {"win", "won", "w", "1", "true", "yes", "oui"}:
        return 1
    if result in {"loss", "lost", "lose", "l", "0", "false", "no", "non"}:
        return 0
    return None


def profit_from_pick(pick: Any) -> Optional[float]:
    if isinstance(pick, (int, float)):
        number = float(pick)
        return number if math.isfinite(number) else None
    if not isinstance(pick, dict):
        return None
    direct = parse_float(pick.get("profit"))
    if direct is not None:
        return direct
    target = parse_target(pick)
    odds = parse_float(pick.get("odds"))
    if target is None or odds is None or odds <= 1.0:
        return None
    return odds - 1.0 if target == 1 else -1.0


def profits_from_picks(picks: Iterable[Any]) -> List[float]:
    profits = []
    for pick in picks:
        profit = profit_from_pick(pick)
        if profit is not None:
            profits.append(profit)
    return profits


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sample_std(values: Sequence[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (n - 1))


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    weight = pos - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def estimate_roi_confidence_interval(picks: Iterable[Any]) -> Dict[str, Any]:
    profits = profits_from_picks(picks)
    n = len(profits)
    if n <= 0:
        return {"n": 0, "roi": None, "std": None, "ci_low": None, "ci_high": None}
    avg = mean(profits)
    std = sample_std(profits)
    se = std / math.sqrt(n) if n else 0.0
    low = avg - 1.96 * se
    high = avg + 1.96 * se
    return {
        "n": n,
        "roi": round(avg * 100.0, 6),
        "std": round(std, 6),
        "ci_low": round(low * 100.0, 6),
        "ci_high": round(high * 100.0, 6),
    }


def bootstrap_roi(picks: Iterable[Any], n_boot: int = 1000) -> Dict[str, Any]:
    profits = profits_from_picks(picks)
    n = len(profits)
    if n <= 0:
        return {"n": 0, "p05": None, "p50": None, "p95": None, "method": "indisponible"}
    rng = random.Random(RANDOM_SEED)
    roi_values: List[float] = []
    if n > 10000:
        avg = mean(profits)
        std = sample_std(profits)
        se = std / math.sqrt(n)
        roi_values = [rng.gauss(avg, se) * 100.0 for _ in range(n_boot)]
        method = "approximation normale grand echantillon"
    else:
        for _ in range(n_boot):
            sample_sum = 0.0
            for _idx in range(n):
                sample_sum += profits[rng.randrange(n)]
            roi_values.append(sample_sum / n * 100.0)
        method = "bootstrap non parametrique"
    return {
        "n": n,
        "p05": round(percentile(roi_values, 0.05) or 0.0, 6),
        "p50": round(percentile(roi_values, 0.50) or 0.0, 6),
        "p95": round(percentile(roi_values, 0.95) or 0.0, 6),
        "method": method,
    }


def monte_carlo_roi(edge: float, odds_mean: float, n_picks: int, n_sims: int = 1000) -> Dict[str, Any]:
    if n_picks <= 0 or odds_mean <= 1.0:
        return {"p05": None, "p50": None, "p95": None}
    edge_decimal = edge / 100.0 if abs(edge) > 0.5 else edge
    win_probability = min(1.0, max(0.0, (1.0 + edge_decimal) / odds_mean))
    rng = random.Random(RANDOM_SEED)
    roi_values = []
    for _ in range(n_sims):
        profit = 0.0
        for _idx in range(n_picks):
            profit += odds_mean - 1.0 if rng.random() < win_probability else -1.0
        roi_values.append(profit / n_picks * 100.0)
    return {
        "p05": round(percentile(roi_values, 0.05) or 0.0, 6),
        "p50": round(percentile(roi_values, 0.50) or 0.0, 6),
        "p95": round(percentile(roi_values, 0.95) or 0.0, 6),
        "win_probability": round(win_probability, 6),
    }


def randomization_test(picks: Iterable[Any], n_sims: int = 1000) -> Dict[str, Any]:
    profits = profits_from_picks(picks)
    n = len(profits)
    if n <= 1:
        return {"p_value": None, "method": "indisponible"}
    observed = mean(profits)
    std = sample_std(profits)
    if std <= 0:
        p_value = 0.0 if observed != 0 else 1.0
        return {"p_value": p_value, "observed_roi": round(observed * 100.0, 6), "method": "variance nulle"}
    if n > 10000:
        z = observed / (std / math.sqrt(n))
        p_value = math.erfc(abs(z) / math.sqrt(2.0))
        return {"p_value": round(min(1.0, max(0.0, p_value)), 6), "observed_roi": round(observed * 100.0, 6), "method": "approximation normale"}
    rng = random.Random(RANDOM_SEED)
    magnitudes = [abs(value) for value in profits]
    extreme = 0
    for _ in range(n_sims):
        simulated = sum(value if rng.random() < 0.5 else -value for value in magnitudes) / n
        if abs(simulated) >= abs(observed):
            extreme += 1
    p_value = (extreme + 1) / (n_sims + 1)
    return {"p_value": round(p_value, 6), "observed_roi": round(observed * 100.0, 6), "method": "randomisation signe"}


def max_drawdown(profits: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def max_drawdown_simulation(picks: Iterable[Any], n_sims: int = 1000) -> Dict[str, Any]:
    profits = profits_from_picks(picks)
    n = len(profits)
    if n <= 0:
        return {"observed": None, "simulated_p50": None, "simulated_p95": None}
    observed = max_drawdown(profits)
    rng = random.Random(RANDOM_SEED)
    base = list(profits)
    if n > 5000:
        base = rng.sample(base, 5000)
        n_sims = min(n_sims, 200)
    draws = []
    for _ in range(n_sims):
        shuffled = list(base)
        rng.shuffle(shuffled)
        draws.append(max_drawdown(shuffled))
    return {
        "observed": round(observed, 6),
        "simulated_p50": round(percentile(draws, 0.50) or 0.0, 6),
        "simulated_p95": round(percentile(draws, 0.95) or 0.0, 6),
    }


def z_value(confidence: float) -> float:
    if confidence >= 0.99:
        return 2.576
    if confidence >= 0.95:
        return 1.96
    if confidence >= 0.90:
        return 1.645
    return 1.96


def sample_size_needed(edge: float, sigma: float = 1.0, confidence: float = 0.95) -> Optional[int]:
    edge_decimal = edge / 100.0 if abs(edge) > 0.5 else edge
    if edge_decimal <= 0 or sigma <= 0:
        return None
    return int(math.ceil((z_value(confidence) * sigma / edge_decimal) ** 2))


def multiple_testing_adjustment(p_values: Sequence[Optional[float]], method: str = "benjamini_hochberg") -> List[Optional[float]]:
    if method != "benjamini_hochberg":
        raise ValueError("Methode supportee: benjamini_hochberg")
    indexed = [(idx, p) for idx, p in enumerate(p_values) if p is not None and math.isfinite(float(p))]
    m = len(indexed)
    adjusted: List[Optional[float]] = [None for _ in p_values]
    if m == 0:
        return adjusted
    sorted_values = sorted(indexed, key=lambda item: item[1], reverse=True)
    running = 1.0
    for rank_from_end, (idx, p_value) in enumerate(sorted_values, start=1):
        rank = m - rank_from_end + 1
        candidate = min(running, float(p_value) * m / rank)
        running = candidate
        adjusted[idx] = round(min(1.0, max(0.0, candidate)), 6)
    return adjusted


def verdict_for(summary: Dict[str, Any]) -> str:
    n = summary.get("n_picks") or 0
    roi = summary.get("roi_observed")
    ci_low = summary.get("roi_ci_low")
    boot = summary.get("bootstrap_roi") or {}
    p_adjusted = summary.get("p_value_adjusted")
    if n < 300:
        return "preuve insuffisante"
    if roi is None or roi <= 0:
        return "preuve insuffisante"
    if n < 1000:
        return "observation"
    if ci_low is None or ci_low <= 0:
        return "observation"
    if (boot.get("p05") or 0.0) <= 0:
        return "observation"
    if p_adjusted is not None and p_adjusted >= 0.05:
        return "observation"
    if n >= 3000 and p_adjusted is not None and p_adjusted < 0.01:
        return "signal robuste rare"
    return "signal statistiquement interessant"


def summarize_profits(profits: List[float], odds_values: List[float], p_value_adjusted: Optional[float] = None) -> Dict[str, Any]:
    ci = estimate_roi_confidence_interval(profits)
    boot = bootstrap_roi(profits)
    rand = randomization_test(profits)
    drawdown = max_drawdown_simulation(profits)
    n = ci["n"]
    profit = sum(profits)
    average_odds = mean(odds_values) if odds_values else None
    summary = {
        "n_picks": n,
        "profit": round(profit, 6),
        "roi_observed": ci["roi"],
        "odds_mean": round(average_odds, 6) if average_odds is not None else None,
        "std_approx": ci["std"],
        "roi_ci_low": ci["ci_low"],
        "roi_ci_high": ci["ci_high"],
        "bootstrap_roi": boot,
        "drawdown": drawdown.get("observed"),
        "drawdown_simulated_p50": drawdown.get("simulated_p50"),
        "drawdown_simulated_p95": drawdown.get("simulated_p95"),
        "p_value": rand.get("p_value"),
        "p_value_adjusted": p_value_adjusted,
    }
    summary["verdict"] = verdict_for(summary)
    return summary


def sample_size_table() -> Dict[str, Optional[int]]:
    return {
        "edge_0_5_pct": sample_size_needed(0.005),
        "edge_1_pct": sample_size_needed(0.01),
        "edge_2_pct": sample_size_needed(0.02),
        "edge_3_pct": sample_size_needed(0.03),
    }


def build_statistical_report(features_path: str, strategy_column: str = "") -> Dict[str, Any]:
    path = Path(features_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "status": "indisponible",
            "message": f"Fichier introuvable: {features_path}",
            "verdict": "preuve insuffisante",
            "warnings": [],
        }
    profits: List[float] = []
    odds_values: List[float] = []
    by_strategy: Dict[str, Dict[str, List[float]]] = {}
    skipped = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        if not any(name in fieldnames for name in ("target_win", "is_win", "won", "result")):
            return {
                "generated_at": now_iso(),
                "features_path": str(path),
                "status": "indisponible",
                "message": "Target win/loss absente: impossible de calculer le ROI.",
                "verdict": "preuve insuffisante",
                "warnings": [],
            }
        if not strategy_column and "strategy_name" in fieldnames:
            strategy_column = "strategy_name"
        for row in reader:
            profit = profit_from_pick(row)
            if profit is None:
                skipped += 1
                continue
            profits.append(profit)
            odds = parse_float(row.get("odds"))
            if odds is not None:
                odds_values.append(odds)
            if strategy_column and strategy_column in row:
                key = str(row.get(strategy_column) or "strategie inconnue")
                by_strategy.setdefault(key, {"profits": [], "odds": []})
                by_strategy[key]["profits"].append(profit)
                if odds is not None:
                    by_strategy[key]["odds"].append(odds)
    if not profits:
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "status": "indisponible",
            "message": "Aucun pick exploitable pour la validation statistique.",
            "verdict": "preuve insuffisante",
            "warnings": [],
        }
    global_randomization = randomization_test(profits)
    adjusted_global = multiple_testing_adjustment([global_randomization.get("p_value")])[0]
    global_summary = summarize_profits(profits, odds_values, p_value_adjusted=adjusted_global)
    group_reports: Dict[str, Dict[str, Any]] = {}
    if by_strategy:
        p_values = []
        names = []
        precomputed = {}
        for name, values in by_strategy.items():
            rand = randomization_test(values["profits"])
            precomputed[name] = rand
            p_values.append(rand.get("p_value"))
            names.append(name)
        adjusted = multiple_testing_adjustment(p_values)
        for name, p_adj in zip(names, adjusted):
            group_reports[name] = summarize_profits(by_strategy[name]["profits"], by_strategy[name]["odds"], p_value_adjusted=p_adj)
            group_reports[name]["p_value"] = precomputed[name].get("p_value")
            group_reports[name]["verdict"] = verdict_for(group_reports[name])
    return {
        "generated_at": now_iso(),
        "features_path": str(path),
        "status": "disponible",
        "message": "Validation statistique descriptive generee. Elle ne conclut jamais a une rentabilite automatique.",
        "rows_skipped": skipped,
        "summary": global_summary,
        "by_strategy": group_reports,
        "sample_size_needed": sample_size_table(),
        "multiple_testing_method": "benjamini_hochberg",
        "verdict": global_summary["verdict"],
        "warnings": [
            "ROI positif court terme ne prouve pas un edge durable.",
            "Kelly et bankroll management ne creent pas d'edge; ils restent limites a la simulation.",
        ],
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary") or {}
    group_rows = []
    for name, stat in (report.get("by_strategy") or {}).items():
        group_rows.append(
            "<tr>"
            f"<td>{html.escape(str(name))}</td>"
            f"<td>{stat.get('n_picks')}</td>"
            f"<td>{stat.get('roi_observed')}</td>"
            f"<td>{stat.get('roi_ci_low')} / {stat.get('roi_ci_high')}</td>"
            f"<td>{stat.get('p_value_adjusted')}</td>"
            f"<td>{html.escape(str(stat.get('verdict')))}</td>"
            "</tr>"
        )
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Validation statistique Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}.warn{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Validation statistique</h1>",
        f"<p>Statut: {html.escape(str(report.get('status')))}. Verdict: {html.escape(str(report.get('verdict')))}.</p>",
        "<ul>",
        f"<li>Picks: {summary.get('n_picks')}</li>",
        f"<li>ROI observe: {summary.get('roi_observed')}%</li>",
        f"<li>IC ROI 95%: {summary.get('roi_ci_low')}% / {summary.get('roi_ci_high')}%</li>",
        f"<li>Bootstrap p05/p50/p95: {(summary.get('bootstrap_roi') or {}).get('p05')} / {(summary.get('bootstrap_roi') or {}).get('p50')} / {(summary.get('bootstrap_roi') or {}).get('p95')}</li>",
        f"<li>p-value ajustee: {summary.get('p_value_adjusted')}</li>",
        "</ul>",
        "<h2>Strategies</h2><table><thead><tr><th>Strategie</th><th>n</th><th>ROI</th><th>IC 95%</th><th>p ajustee</th><th>Verdict</th></tr></thead><tbody>",
        *group_rows,
        "</tbody></table>",
        "<section class='warn'><h2>Rappel</h2><p>Aucun resultat positif ne devient pick conseille sans CLV positive, calibration, test temporel et revue humaine.</p></section>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    summary = report.get("summary") or {}
    print("Validation statistique Oracle Bot")
    print(f"- Statut: {report.get('status')}")
    print(f"- Message: {report.get('message')}")
    print(f"- Picks: {summary.get('n_picks')}")
    print(f"- ROI observe: {summary.get('roi_observed')}%")
    print(f"- IC ROI 95%: {summary.get('roi_ci_low')}% -> {summary.get('roi_ci_high')}%")
    boot = summary.get("bootstrap_roi") or {}
    print(f"- Bootstrap ROI p05/p50/p95: {boot.get('p05')} / {boot.get('p50')} / {boot.get('p95')}")
    print(f"- p-value ajustee: {summary.get('p_value_adjusted')}")
    print(f"- Verdict: {report.get('verdict')}")
    print("- Aucun staking, aucun pick Telegram et aucune modification DB.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Validation statistique prudente des resultats observes.")
    parser.add_argument("--features", required=True, help="CSV de features")
    parser.add_argument("--strategy-column", default="", help="Colonne de strategie si disponible")
    parser.add_argument("--output", default="", help="Rapport JSON a ecrire")
    parser.add_argument("--html", default="", help="Rapport HTML a ecrire")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_statistical_report(args.features, strategy_column=args.strategy_column)
    if args.output:
        path = write_json(report, args.output)
        print(f"- Rapport JSON validation statistique ecrit: {path}")
    if args.html:
        path = write_html(report, args.html)
        print(f"- Rapport HTML validation statistique ecrit: {path}")
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
