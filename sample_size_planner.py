import argparse
import html
import json
import math
from pathlib import Path
from typing import Any, Dict


DEFAULT_EDGES = [0.005, 0.01, 0.02, 0.03]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le sample size planner ne doit pas ecrire dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: str) -> Dict[str, Any]:
    if not path or not Path(path).exists():
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def sample_size_for_edge(edge: float, sigma: float = 1.0, confidence_z: float = 1.96) -> int:
    edge = abs(float(edge))
    if edge <= 0:
        return 0
    return int(math.ceil((confidence_z * sigma / edge) ** 2))


def build_sample_size_plan(
    target_edge: float = 0.01,
    clv_mean: float = 0.0,
    clv_std: float = 0.05,
    shadow_report_path: str = "",
) -> Dict[str, Any]:
    shadow = read_json(shadow_report_path)
    current_sample = int(shadow.get("sample_size") or shadow.get("signals_total") or 0)
    current_clv_mean = shadow.get("clv_mean")
    current_clv_coverage = shadow.get("clv_coverage")
    edge_table = {
        f"{edge * 100:.1f}%": sample_size_for_edge(edge)
        for edge in DEFAULT_EDGES
    }
    target_required = sample_size_for_edge(target_edge)
    clv_required = sample_size_for_edge(clv_mean, sigma=clv_std) if clv_mean and clv_mean > 0 else None
    standard_error = round(clv_std / math.sqrt(current_sample), 6) if current_sample > 0 else None
    ci_low = None
    ci_high = None
    if standard_error is not None and current_clv_mean is not None:
        mean = float(current_clv_mean)
        ci_low = round(mean - 1.96 * standard_error, 6)
        ci_high = round(mean + 1.96 * standard_error, 6)
    warnings = [
        "<100: bruit extreme" if current_sample < 100 else "",
        "<500: insuffisant" if current_sample < 500 else "",
        "<1000: non valide" if current_sample < 1000 else "",
    ]
    warnings = [item for item in warnings if item]
    if current_sample < 3000:
        warnings.append(">3000 commence seulement a devenir plus parlant")
    return {
        "current_sample": current_sample,
        "target_edge": target_edge,
        "target_edge_required_sample": target_required,
        "edge_sample_requirements": edge_table,
        "clv_mean_input": clv_mean,
        "clv_std_input": clv_std,
        "clv_required_sample": clv_required,
        "current_clv_mean": current_clv_mean,
        "current_clv_coverage": current_clv_coverage,
        "standard_error_estimate": standard_error,
        "confidence_interval_approx": {"low": ci_low, "high": ci_high},
        "prudence_thresholds": {
            "<100": "bruit extreme",
            "<500": "insuffisant",
            "<1000": "non valide",
            ">3000": "commence a parler",
            ">10000": "meilleur pour edges faibles",
        },
        "warnings": warnings,
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Planification prudente: aucune promesse de rentabilite.",
    }


def write_json(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], path: str) -> Path:
    target = ensure_reports_path(path)
    rows = "".join(
        f"<tr><td>{html.escape(str(edge))}</td><td>{sample}</td></tr>"
        for edge, sample in (report.get("edge_sample_requirements") or {}).items()
    )
    warnings = "".join(f"<li>{html.escape(str(item))}</li>" for item in report.get("warnings") or [])
    target.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'><title>Sample Size Plan</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>",
        "</head><body><h1>Sample Size Plan</h1>",
        f"<p>{html.escape(str(report.get('message')))}</p>",
        f"<p>Sample actuel: {report.get('current_sample')}</p>",
        "<table><thead><tr><th>Edge</th><th>Sample requis approx.</th></tr></thead><tbody>",
        rows,
        "</tbody></table>",
        f"<h2>Warnings</h2><ul>{warnings}</ul>",
        "</body></html>",
    ]), encoding="utf-8")
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Sample Size Planner Oracle Bot")
    print(f"- Sample actuel: {report.get('current_sample')}")
    print(f"- Sample requis target edge {report.get('target_edge')}: {report.get('target_edge_required_sample')}")
    print(f"- Sample requis CLV: {report.get('clv_required_sample')}")
    for edge, sample in (report.get("edge_sample_requirements") or {}).items():
        print(f"- Edge {edge}: sample approx {sample}")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")
    print("- Aucun seuil ne prouve une rentabilite a lui seul.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Planifie le sample shadow necessaire avant interpretation.")
    parser.add_argument("--target-edge", type=float, default=0.01)
    parser.add_argument("--clv-mean", type=float, default=0.0)
    parser.add_argument("--clv-std", type=float, default=0.05)
    parser.add_argument("--shadow-report", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_sample_size_plan(
            target_edge=args.target_edge,
            clv_mean=args.clv_mean,
            clv_std=args.clv_std,
            shadow_report_path=args.shadow_report,
        )
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
