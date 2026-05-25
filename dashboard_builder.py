import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REPORT_FILES = {
    "backtest_modern": "backtest_modern.txt",
    "backtest_recent": "backtest_recent.txt",
    "period": "period_report.txt",
    "favorite": "favorite_report.txt",
    "stability": "stability_report.txt",
    "pricing": "pricing_report.txt",
    "ml_global": "ml_global.txt",
    "ml_h2h": "ml_h2h.txt",
    "ml_total": "ml_total.txt",
    "external_profile": "external_profile.txt",
    "external_recommend": "external_recommend.txt",
}


def latest_report_dir(root: str = "reports") -> Optional[Path]:
    base = Path(root)
    if not base.exists():
        return None
    dirs = [path for path in base.iterdir() if path.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda path: path.stat().st_mtime)


def read_text(report_dir: Path, filename: str) -> str:
    path = report_dir / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _first(pattern: str, text: str, flags: int = re.MULTILINE) -> Optional[str]:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _first_float(pattern: str, text: str) -> Optional[float]:
    value = _first(pattern, text)
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _section(text: str, title: str, max_chars: int = 1800) -> str:
    if not text:
        return "Rapport indisponible."
    idx = text.find(title)
    if idx < 0:
        return text[:max_chars]
    return text[idx: idx + max_chars]


def _lines_matching(text: str, patterns: List[str], limit: int = 12) -> List[str]:
    lines = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(pattern.lower() in lowered for pattern in patterns):
            lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def build_summary(report_dir: Path) -> Dict[str, Any]:
    texts = {key: read_text(report_dir, filename) for key, filename in REPORT_FILES.items()}
    pricing = texts["pricing"]
    modern = texts["backtest_modern"]
    favorite = texts["favorite"]
    ml_global = texts["ml_global"]

    records_count = _first_float(r"- Records regles: ([0-9]+)", pricing)
    if records_count is None:
        records_count = _first_float(r"- Records test: ([0-9]+)", modern)
    date_min = _first(r"- Train: (\d{4}-\d{2}-\d{2}) ->", modern) or _first(r"- Records train: [0-9]+ \((\d{4}-\d{2}-\d{2}) ->", modern)
    date_max = _first(r"- Records test: [0-9]+ \([^)]* -> ([0-9-]+)\)", modern)
    baseline_roi = _first_float(r"Baseline march.*?\n(?:.*\n){0,5}- ROI: (-?[0-9.]+)%", modern)
    pricing_low_roi = _first_float(r"Marge faible .*?ROI=(-?[0-9.]+)%", pricing)
    pricing_high_roi = _first_float(r"Marge elevee .*?ROI=(-?[0-9.]+)%", pricing)
    ml_brier = _first_float(r"Test 2024\+:\n\s+- modele: n=\d+, Brier=([0-9.]+)", ml_global)
    ml_market_brier = _first_float(r"Test 2024\+:\n\s+- modele:.*\n\s+- marche no-vig: Brier=([0-9.]+)", ml_global)
    favorites_roi = _first_float(r"test n=\d+, ROI=(-?[0-9.]+)%", favorite)
    totals_roi = _first_float(r"Totals seulement.*?\n(?:.*\n){0,5}- ROI: (-?[0-9.]+)%", modern)

    warnings = []
    joined = "\n".join(texts.values()).lower()
    if "aucune strategie positive robuste" in joined or "aucune regle jouable" in joined:
        warnings.append("Aucune strategie robuste positive detectee.")
    if "signal invalide" in joined:
        warnings.append("Des signaux validation sont invalides sur test.")
    if "sklearn indisponible" in joined:
        warnings.append("sklearn indisponible: modeles RF/GB ignores.")

    conclusion = "Aucune strategie jouable robuste a ce stade; conserver une posture prudente et descriptive."
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "records_count": int(records_count) if records_count is not None else None,
        "date_min": date_min,
        "date_max": date_max,
        "baseline_roi_test": baseline_roi,
        "favorites_roi_test": favorites_roi,
        "totals_roi_test": totals_roi,
        "pricing_low_margin_roi": pricing_low_roi,
        "pricing_high_margin_roi": pricing_high_roi,
        "ml_global_brier_test": ml_brier,
        "ml_market_brier_test": ml_market_brier,
        "conclusion": conclusion,
        "warnings": warnings,
    }


def _card(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2><pre>{html.escape(body.strip() or 'Information indisponible.')}</pre></section>"


def build_dashboard(report_dir: Path) -> Dict[str, Any]:
    texts = {key: read_text(report_dir, filename) for key, filename in REPORT_FILES.items()}
    summary = build_summary(report_dir)
    parts = [
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Rapport Oracle Bot</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;line-height:1.45;color:#1f2933}section{border:1px solid #ddd;padding:16px;margin:16px 0;border-radius:6px}pre{white-space:pre-wrap;background:#f7f7f7;padding:12px;border-radius:4px}h1,h2{color:#111827}.warn{background:#fff7ed;border-color:#fed7aa}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.metric{background:#f3f4f6;padding:12px;border-radius:6px}</style>",
        "</head><body>",
        "<h1>Rapport central Oracle Football Bot</h1>",
        f"<p>Genere le {html.escape(summary['generated_at'])}. Rapport local descriptif: aucun pick automatique.</p>",
        "<div class='grid'>",
    ]
    for key, label in [
        ("records_count", "Records"),
        ("date_min", "Date min"),
        ("date_max", "Date max"),
        ("baseline_roi_test", "ROI baseline test"),
        ("pricing_low_margin_roi", "ROI marge faible"),
        ("ml_global_brier_test", "Brier ML global"),
    ]:
        value = summary.get(key)
        parts.append(f"<div class='metric'><strong>{html.escape(label)}</strong><br>{html.escape(str(value) if value is not None else 'n/a')}</div>")
    parts.append("</div>")
    if summary["warnings"]:
        parts.append("<section class='warn'><h2>Alertes</h2><ul>")
        parts.extend(f"<li>{html.escape(warning)}</li>" for warning in summary["warnings"])
        parts.append("</ul></section>")

    memory = "\n".join([
        f"records_count: {summary.get('records_count')}",
        f"date_min: {summary.get('date_min')}",
        f"date_max: {summary.get('date_max')}",
        "split attendu: train 2015-2022, validation 2023, test 2024+",
    ])
    parts.append(_card("Resume memoire", memory))
    parts.append(_card("Backtest", "\n".join(_lines_matching(texts["backtest_modern"], ["Baseline", "Oracle", "Conclusion", "Aucune", "Records train", "Records test"], 20))))
    parts.append(_card("Pricing", "\n".join(_lines_matching(texts["pricing"], ["Marge moyenne", "Marge faible", "Marge elevee", "EV baseline", "trop elevee"], 20))))
    parts.append(_card("Favorite Report", "\n".join(_lines_matching(texts["favorite"], ["Favoris H2H", "1.60", "exterieur", "elo_diff", "Conclusion", "Aucun"], 24))))
    parts.append(_card("Stability", "\n".join(_lines_matching(texts["stability"], ["stable", "instable", "degradation", "negatif", "Conclusion", "Aucun"], 24))))
    ml_lines = []
    for key in ("ml_global", "ml_h2h", "ml_total"):
        if texts[key]:
            ml_lines.append(f"--- {key} ---")
            ml_lines.extend(_lines_matching(texts[key], ["Brier", "log loss", "edge >", "signal invalide", "Conclusion prudente", "Jeu de features"], 28))
    parts.append(_card("ML", "\n".join(ml_lines)))
    external_lines = _lines_matching(texts["external_profile"] + "\n" + texts["external_recommend"], ["Score utilite", "xg:", "odds:", "leak_risk", "verdict", "Recommandation"], 20)
    parts.append(_card("External Dataset Lab", "\n".join(external_lines)))
    conclusion = "\n".join([
        summary["conclusion"],
        "Observations seulement: aucune sortie de ce rapport ne modifie Telegram, Railway ou la DB.",
        "Prochaines etapes: profiler un dataset externe xG/FBref/Kaggle local, puis tester toute jointure en train/validation/test.",
    ])
    parts.append(_card("Conclusion prudente", conclusion))
    parts.append("</body></html>")

    (report_dir / "index.html").write_text("\n".join(parts), encoding="utf-8")
    (report_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Construit un dashboard HTML local depuis les sorties de report_runner.")
    parser.add_argument("--latest", action="store_true", help="Utilise le dernier dossier reports/")
    parser.add_argument("--input", default="", help="Dossier de rapport a lire")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    report_dir = latest_report_dir() if args.latest or not args.input else Path(args.input)
    if report_dir is None:
        raise SystemExit("Aucun dossier de rapport trouve.")
    summary = build_dashboard(report_dir)
    print("Dashboard central Oracle Bot")
    print(f"- Dossier: {report_dir}")
    print(f"- HTML: {report_dir / 'index.html'}")
    print(f"- JSON: {report_dir / 'summary.json'}")
    print(f"- Conclusion: {summary.get('conclusion')}")


if __name__ == "__main__":
    main()
