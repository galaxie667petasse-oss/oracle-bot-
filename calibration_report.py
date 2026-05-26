import argparse
import csv
import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_BINS = 20
EPS = 1e-15


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


def parse_probability(value: Any) -> Optional[float]:
    number = parse_float(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        return number
    if 1.0 < number <= 100.0:
        return number / 100.0
    return None


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


def bin_label(index: int, n_bins: int = DEFAULT_BINS) -> str:
    low = index / n_bins
    high = (index + 1) / n_bins
    return f"{low:.2f}-{high:.2f}"


def bin_index(probability: float, n_bins: int = DEFAULT_BINS) -> int:
    return min(n_bins - 1, max(0, int(probability * n_bins)))


def empty_bin(index: int, n_bins: int = DEFAULT_BINS) -> Dict[str, Any]:
    return {
        "bin": bin_label(index, n_bins),
        "n": 0,
        "predicted_mean": None,
        "observed_win_rate": None,
        "gap": None,
        "roi": None,
    }


def unit_profit(row: Dict[str, Any], target: int) -> Optional[float]:
    odds = parse_float(row.get("odds"))
    if odds is None or odds <= 1.0:
        return None
    return odds - 1.0 if target == 1 else -1.0


def build_calibration_report(features_path: str, prob_column: str = "no_vig_probability", n_bins: int = DEFAULT_BINS) -> Dict[str, Any]:
    path = Path(features_path)
    if not path.exists():
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "probability_column": prob_column,
            "status": "indisponible",
            "message": f"Fichier introuvable: {features_path}",
            "verdict": "indisponible",
            "warnings": [],
        }
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        if prob_column not in fieldnames:
            return {
                "generated_at": now_iso(),
                "features_path": str(path),
                "probability_column": prob_column,
                "status": "indisponible",
                "message": f"Colonne probabilite absente: {prob_column}",
                "verdict": "indisponible",
                "warnings": [],
            }
        if not any(name in fieldnames for name in ("target_win", "is_win", "won", "result")):
            return {
                "generated_at": now_iso(),
                "features_path": str(path),
                "probability_column": prob_column,
                "status": "indisponible",
                "message": "Target win/loss absente: utiliser target_win, won, is_win ou result.",
                "verdict": "indisponible",
                "warnings": [],
            }
        bins = [{"n": 0, "pred_sum": 0.0, "obs_sum": 0.0, "profit_sum": 0.0, "profit_n": 0} for _ in range(n_bins)]
        n = 0
        brier_sum = 0.0
        log_loss_sum = 0.0
        skipped = 0
        for row in reader:
            p = parse_probability(row.get(prob_column))
            target = parse_target(row)
            if p is None or target is None:
                skipped += 1
                continue
            n += 1
            brier_sum += (p - target) ** 2
            p_clamped = min(1.0 - EPS, max(EPS, p))
            log_loss_sum += -(target * math.log(p_clamped) + (1 - target) * math.log(1.0 - p_clamped))
            idx = bin_index(p, n_bins)
            bucket = bins[idx]
            bucket["n"] += 1
            bucket["pred_sum"] += p
            bucket["obs_sum"] += target
            profit = unit_profit(row, target)
            if profit is not None:
                bucket["profit_sum"] += profit
                bucket["profit_n"] += 1
    if n <= 0:
        return {
            "generated_at": now_iso(),
            "features_path": str(path),
            "probability_column": prob_column,
            "status": "indisponible",
            "message": "Aucune ligne exploitable pour la calibration.",
            "verdict": "indisponible",
            "warnings": [],
        }
    calibration_bins: List[Dict[str, Any]] = []
    ece = 0.0
    mce = 0.0
    for index, bucket in enumerate(bins):
        if bucket["n"] <= 0:
            calibration_bins.append(empty_bin(index, n_bins))
            continue
        predicted = bucket["pred_sum"] / bucket["n"]
        observed = bucket["obs_sum"] / bucket["n"]
        gap = observed - predicted
        abs_gap = abs(gap)
        ece += bucket["n"] / n * abs_gap
        mce = max(mce, abs_gap)
        roi = None
        if bucket["profit_n"]:
            roi = bucket["profit_sum"] / bucket["profit_n"] * 100.0
        calibration_bins.append({
            "bin": bin_label(index, n_bins),
            "n": bucket["n"],
            "predicted_mean": round(predicted, 6),
            "observed_win_rate": round(observed, 6),
            "gap": round(gap, 6),
            "roi": round(roi, 4) if roi is not None else None,
        })
    brier = brier_sum / n
    log_loss = log_loss_sum / n
    if ece <= 0.02 and mce <= 0.08:
        verdict = "calibration solide"
    elif ece <= 0.05:
        verdict = "calibration acceptable mais a surveiller"
    else:
        verdict = "calibration fragile"
    return {
        "generated_at": now_iso(),
        "features_path": str(path),
        "probability_column": prob_column,
        "status": "disponible",
        "message": "Rapport de calibration descriptif genere. Aucun modele n'est entraine ici.",
        "rows_used": n,
        "rows_skipped": skipped,
        "brier": round(brier, 6),
        "log_loss": round(log_loss, 6),
        "ece": round(ece, 6),
        "mce": round(mce, 6),
        "bins": calibration_bins,
        "verdict": verdict,
        "warnings": ["Une reliability curve ne valide pas un edge sans CLV positive, test temporel et correction de multiple testing."],
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in report.get("bins") or []:
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('bin')))}</td>"
            f"<td>{item.get('n')}</td>"
            f"<td>{item.get('predicted_mean')}</td>"
            f"<td>{item.get('observed_win_rate')}</td>"
            f"<td>{item.get('gap')}</td>"
            f"<td>{item.get('roi')}</td>"
            "</tr>"
        )
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Calibration Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}</style>",
        "</head><body>",
        "<h1>Calibration probabiliste</h1>",
        f"<p>Statut: {html.escape(str(report.get('status')))}. Verdict: {html.escape(str(report.get('verdict')))}.</p>",
        f"<p>Brier: {report.get('brier')} | Log loss: {report.get('log_loss')} | ECE: {report.get('ece')} | MCE: {report.get('mce')}</p>",
        "<table><thead><tr><th>Bin</th><th>n</th><th>Predicted mean</th><th>Observed win rate</th><th>Gap</th><th>ROI</th></tr></thead><tbody>",
        *rows,
        "</tbody></table>",
        "<p>Rapport descriptif seulement: aucun entrainement, aucun pick Telegram.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Rapport calibration Oracle Bot")
    print(f"- Statut: {report.get('status')}")
    print(f"- Message: {report.get('message')}")
    print(f"- Lignes exploitees: {report.get('rows_used')}")
    print(f"- Brier: {report.get('brier')}")
    print(f"- Log loss: {report.get('log_loss')}")
    print(f"- ECE: {report.get('ece')}")
    print(f"- MCE: {report.get('mce')}")
    print(f"- Verdict: {report.get('verdict')}")
    print("- Aucun modele entraine et aucune modification DB.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Reliability curves locales et descriptives.")
    parser.add_argument("--features", required=True, help="CSV de features")
    parser.add_argument("--prob-column", default="no_vig_probability", help="Colonne de probabilite a evaluer")
    parser.add_argument("--output", default="", help="Rapport JSON a ecrire")
    parser.add_argument("--html", default="", help="Rapport HTML a ecrire")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_calibration_report(args.features, prob_column=args.prob_column)
    if args.output:
        path = write_json(report, args.output)
        print(f"- Rapport JSON calibration ecrit: {path}")
    if args.html:
        path = write_html(report, args.html)
        print(f"- Rapport HTML calibration ecrit: {path}")
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
