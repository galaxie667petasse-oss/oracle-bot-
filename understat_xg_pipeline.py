import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

import benchmark_governance
import external_xg_features
import external_xg_lab
import join_diagnostics
import xg_dataset_quality
import xg_model_lab


DEFAULT_EXTERNAL = "external_data/understat_probe/epl_2020_2025_matches.csv"
DEFAULT_XGABORA = "data/features_modern.csv"
DEFAULT_PREFIX = "understat_epl_2020_2025"
DEFAULT_EXPECTED_SEASONS = "2020-2021,2021-2022,2022-2023,2023-2024,2024-2025"


def infer_league(external: str, league: str = "") -> str:
    if league and str(league).strip().lower() != "epl":
        return league
    text = str(external or "").replace("\\", "/").lower()
    if "bundesliga" in text:
        return "Bundesliga"
    if "laliga" in text or "la-liga" in text or "la_liga" in text:
        return "La-Liga"
    if "seriea" in text or "serie-a" in text or "serie_a" in text:
        return "Serie A"
    if "ligue1" in text or "ligue-1" in text or "ligue_1" in text:
        return "Ligue 1"
    return league or "EPL"


def report_path(prefix: str, suffix: str) -> Path:
    target = Path("reports") / f"{prefix}_{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def status_block(ok: bool, warning: str = "", data: Any = None) -> Dict[str, Any]:
    return {"ok": ok, "warning": warning, "data": data}


def extract_xg_model_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    comparison = report.get("comparison") or {}
    verdict = report.get("verdict") or {}
    selected = verdict.get("selected_test") or {}
    return {
        "market_brier_test": ((report.get("market_baseline") or {}).get("test") or {}).get("brier"),
        "market_log_loss_test": ((report.get("market_baseline") or {}).get("test") or {}).get("log_loss"),
        "base_brier_test": (comparison.get("without_xg") or {}).get("brier"),
        "base_log_loss_test": (comparison.get("without_xg") or {}).get("log_loss"),
        "xg_brier_test": (comparison.get("with_xg") or {}).get("brier"),
        "xg_log_loss_test": (comparison.get("with_xg") or {}).get("log_loss"),
        "roi_edge_test": selected.get("roi"),
        "sample_edge_test": selected.get("picks"),
        "promotion_allowed": verdict.get("promotion_allowed"),
        "governance_note": verdict.get("governance_note"),
        "rejection_reasons": verdict.get("rejection_reasons") or [],
    }


def write_json(payload: Dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_html(summary: Dict[str, Any], path: Path) -> Path:
    quality = ((summary.get("quality") or {}).get("data") or {})
    rolling = ((summary.get("rolling_features") or {}).get("data") or {})
    model = ((summary.get("xg_model") or {}).get("summary") or {})
    benchmark = ((summary.get("benchmark") or {}).get("data") or {}).get("summary") or {}
    rows = [
        ("Quality verdict", quality.get("verdict")),
        ("Join rate avant alias", summary.get("join_rate_before_alias")),
        ("Join rate apres alias", summary.get("join_rate_after_alias")),
        ("Join quality", summary.get("join_quality")),
        ("Rolling avg3", rolling.get("avg3_rows")),
        ("Rolling avg5", rolling.get("avg5_rows")),
        ("Brier marche", model.get("market_brier_test")),
        ("Brier xG", model.get("xg_brier_test")),
        ("ROI edge test", model.get("roi_edge_test")),
        ("Promotion allowed", model.get("promotion_allowed")),
        ("Candidats robustes", benchmark.get("robust_candidates")),
    ]
    path.write_text("\n".join([
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<title>Pipeline Understat xG</title>",
        "<style>body{font-family:Arial,sans-serif;margin:32px;color:#1f2933}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f3f4f6}</style>",
        "</head><body>",
        "<h1>Understat xG Multi-Season Lab</h1>",
        "<table><thead><tr><th>Mesure</th><th>Valeur</th></tr></thead><tbody>",
        *[f"<tr><td>{html.escape(str(key))}</td><td>{html.escape(str(value))}</td></tr>" for key, value in rows],
        "</tbody></table>",
        f"<p>{html.escape(str(summary.get('conclusion')))}</p>",
        "<p>Rapport local descriptif: aucun pick automatique, aucun Telegram, aucun Railway.</p>",
        "</body></html>",
    ]), encoding="utf-8")
    return path


def build_pipeline(
    external: str,
    xgabora: str,
    out_prefix: str = DEFAULT_PREFIX,
    league: str = "EPL",
    expected_seasons: str = DEFAULT_EXPECTED_SEASONS,
    skip_model: bool = False,
    skip_benchmark: bool = False,
    dry_run: bool = False,
    strict_join: bool = False,
) -> Dict[str, Any]:
    external_path = Path(external)
    xgabora_path = Path(xgabora)
    league = infer_league(external, league)
    if not external_path.exists():
        raise FileNotFoundError(f"Fichier externe introuvable: {external}")
    if not xgabora_path.exists():
        raise FileNotFoundError(f"Feature matrix introuvable: {xgabora}")

    quality_json = report_path(out_prefix, "quality.json")
    quality_html = report_path(out_prefix, "quality.html")
    join_json = report_path(out_prefix, "join_diagnostics.json")
    join_html = report_path(out_prefix, "join_diagnostics.html")
    rolling_csv = report_path(out_prefix, "rolling_features.csv")
    model_json = report_path(out_prefix, "xg_model.json")
    model_html = report_path(out_prefix, "xg_model.html")
    summary_json = report_path(out_prefix, "pipeline_summary.json")
    summary_html = report_path(out_prefix, "pipeline.html")
    benchmark_summary = report_path(out_prefix, "benchmark_summary.json")
    benchmark_html = report_path(out_prefix, "benchmark_governance.html")
    benchmark_registry = report_path(out_prefix, "model_registry.json")

    planned_steps = [
        f"Quality gate -> {quality_json}",
        f"Diagnostic jointure -> {join_json}",
        f"Rolling features -> {rolling_csv}",
        f"xG model lab -> {model_json}" if not skip_model else "xG model lab ignore (--skip-model)",
        f"Benchmark governance -> {benchmark_summary}" if not skip_benchmark else "Benchmark ignore (--skip-benchmark)",
    ]
    if dry_run:
        return {
            "external": str(external_path),
            "xgabora": str(xgabora_path),
            "out_prefix": out_prefix,
            "dry_run": True,
            "planned_steps": planned_steps,
            "conclusion": "Dry-run: aucune etape lancee, aucun fichier cree.",
        }

    summary: Dict[str, Any] = {
        "external": str(external_path),
        "xgabora": str(xgabora_path),
        "out_prefix": out_prefix,
        "dry_run": False,
        "warnings": [],
        "planned_steps": planned_steps,
    }

    try:
        quality = xg_dataset_quality.build_quality_report(str(external_path), league=league, expected_seasons=expected_seasons)
        xg_dataset_quality.write_json(quality, str(quality_json))
        xg_dataset_quality.write_html(quality, str(quality_html))
        summary["quality"] = status_block(True, data=quality)
    except Exception as exc:
        summary["quality"] = status_block(False, warning=str(exc))
        summary["warnings"].append(f"Quality gate indisponible: {exc}")

    try:
        diagnostics = join_diagnostics.build_join_diagnostics(str(xgabora_path), str(external_path), league=league)
        join_diagnostics.write_json(diagnostics, str(join_json))
        join_diagnostics.write_html(diagnostics, str(join_html))
        summary["join_diagnostics"] = status_block(True, data=diagnostics)
        summary["join_rate_before_alias"] = diagnostics.get("join_rate_before_alias")
        summary["join_rate_after_alias"] = diagnostics.get("join_rate_after_alias")
        summary["join_quality"] = diagnostics.get("join_quality")
        summary["modeling_allowed_by_join_quality"] = diagnostics.get("modeling_allowed_by_join_quality")
        summary["unmatched_examples"] = diagnostics.get("unmatched_external_examples", [])[:10]
        summary["alias_matches_gained"] = diagnostics.get("alias_matches_gained")
        if not diagnostics.get("modeling_allowed_by_join_quality"):
            summary["warnings"].append("Avertissement fort: taux de jointure inferieur a 50%, modele xG bloque.")
        if strict_join and float(diagnostics.get("join_rate_after_alias") or 0.0) < 75.0:
            summary["rolling_features"] = status_block(False, warning="Pipeline stoppe par --strict-join")
            summary["xg_model"] = status_block(False, warning="Modele bloque par --strict-join")
            summary["benchmark"] = status_block(False, warning="Benchmark non lance apres --strict-join")
            summary["final_status"] = {
                "quality_verdict": ((summary.get("quality") or {}).get("data") or {}).get("verdict"),
                "join_rate": diagnostics.get("join_rate_after_alias"),
                "join_quality": diagnostics.get("join_quality"),
                "modeling_allowed_by_join_quality": diagnostics.get("modeling_allowed_by_join_quality"),
                "unmatched_examples": summary["unmatched_examples"],
            }
            summary["conclusion"] = "Pipeline stoppe: jointure externe insuffisante pour --strict-join."
            write_json(summary, summary_json)
            write_html(summary, summary_html)
            raise ValueError("Jointure externe insuffisante pour --strict-join: seuil minimum 75%.")
    except ValueError:
        raise
    except Exception as exc:
        summary["join_diagnostics"] = status_block(False, warning=str(exc))
        summary["warnings"].append(f"Diagnostic jointure indisponible: {exc}")

    try:
        join = external_xg_lab.evaluate_join(str(xgabora_path), str(external_path))
        summary["join"] = status_block(True, data={
            "join_rate": (join.get("plan") or {}).get("match_rate"),
            "matches_with_xg": join.get("matches_with_xg"),
            "matches_with_xg_and_xgabora_odds": join.get("matches_with_xg_and_xgabora_odds"),
            "verdict": join.get("verdict"),
            "notes": join.get("notes") or [],
        })
    except Exception as exc:
        summary["join"] = status_block(False, warning=str(exc))
        summary["warnings"].append(f"Evaluation jointure indisponible: {exc}")

    try:
        rolling = external_xg_features.build_external_xg_features(str(external_path), str(xgabora_path), str(rolling_csv), alias_report=str(join_json))
        summary["rolling_features"] = status_block(True, data=rolling)
    except Exception as exc:
        summary["rolling_features"] = status_block(False, warning=str(exc))
        summary["warnings"].append(f"Rolling features indisponibles: {exc}")

    modeling_allowed = bool(summary.get("modeling_allowed_by_join_quality", True))
    if skip_model:
        summary["xg_model"] = status_block(False, warning="Modele ignore par --skip-model")
    elif not modeling_allowed:
        summary["xg_model"] = status_block(False, warning="Modele bloque par qualite de jointure insuffisante")
    elif summary.get("rolling_features", {}).get("ok"):
        try:
            model_report = xg_model_lab.build_xg_model_report(str(rolling_csv))
            model_report["join_quality_context"] = {
                "join_rate": summary.get("join_rate_after_alias"),
                "join_rate_before_alias": summary.get("join_rate_before_alias"),
                "join_quality": summary.get("join_quality"),
                "modeling_allowed_by_join_quality": summary.get("modeling_allowed_by_join_quality"),
                "alias_applied": ((summary.get("join_diagnostics") or {}).get("data") or {}).get("alias_applied"),
                "unmatched_count": ((summary.get("join_diagnostics") or {}).get("data") or {}).get("unmatched_count"),
                "join_blocks_promotion": not bool(summary.get("modeling_allowed_by_join_quality", True)),
            }
            xg_model_lab.write_json(model_report, str(model_json))
            xg_model_lab.write_html(model_report, str(model_html))
            summary["xg_model"] = status_block(True, data=model_report)
            summary["xg_model"]["summary"] = extract_xg_model_summary(model_report)
        except Exception as exc:
            summary["xg_model"] = status_block(False, warning=str(exc))
            summary["warnings"].append(f"xG model lab indisponible: {exc}")
    else:
        summary["xg_model"] = status_block(False, warning="Rolling features absentes.")

    if skip_benchmark:
        summary["benchmark"] = status_block(False, warning="Benchmark ignore par --skip-benchmark")
    else:
        try:
            print("- Benchmark governance: cette etape peut prendre du temps sur la memoire locale.")
            benchmark = benchmark_governance.build_benchmark(
                str(xgabora_path),
                xg_lab_path=str(rolling_csv) if rolling_csv.exists() else "",
                xg_quality_path=str(quality_json) if quality_json.exists() else "",
                xg_model_path=str(model_json) if model_json.exists() else "",
            )
            benchmark_governance.write_summary(benchmark, str(benchmark_summary))
            benchmark_governance.write_html(benchmark, str(benchmark_html))
            benchmark_governance.write_registry(benchmark["registry"], str(benchmark_registry))
            summary["benchmark"] = status_block(True, data={"summary": benchmark.get("summary")})
        except Exception as exc:
            summary["benchmark"] = status_block(False, warning=str(exc))
            summary["warnings"].append(f"Benchmark indisponible: {exc}")

    quality_verdict = ((summary.get("quality") or {}).get("data") or {}).get("verdict")
    rolling_data = ((summary.get("rolling_features") or {}).get("data") or {})
    model_summary = ((summary.get("xg_model") or {}).get("summary") or {})
    summary["final_status"] = {
        "quality_verdict": quality_verdict,
        "join_rate": summary.get("join_rate_after_alias") or rolling_data.get("join_rate") or ((summary.get("join") or {}).get("data") or {}).get("join_rate"),
        "join_rate_before_alias": summary.get("join_rate_before_alias"),
        "join_rate_after_alias": summary.get("join_rate_after_alias"),
        "join_quality": summary.get("join_quality"),
        "modeling_allowed_by_join_quality": summary.get("modeling_allowed_by_join_quality"),
        "unmatched_examples": summary.get("unmatched_examples", []),
        "rolling_avg3_rows": rolling_data.get("avg3_rows"),
        "rolling_avg5_rows": rolling_data.get("avg5_rows"),
        "unique_matches_rolling": rolling_data.get("matched_external_matches"),
        "xg_model": model_summary,
        "governance_status": (((summary.get("benchmark") or {}).get("data") or {}).get("summary") or {}).get("conclusion"),
    }
    summary["conclusion"] = "Pipeline xG termine en mode laboratoire. Aucun pick automatique; promotion bloquee sans CLV positive et ROI test robuste."
    write_json(summary, summary_json)
    write_html(summary, summary_html)
    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    print("Understat xG Full Pipeline Quality Gate")
    print(f"- Externe: {summary.get('external')}")
    print(f"- Xgabora/features: {summary.get('xgabora')}")
    if summary.get("dry_run"):
        for step in summary.get("planned_steps") or []:
            print(f"- Etape prevue: {step}")
        print("- Dry-run: aucune recuperation reseau, aucun fichier cree.")
        return
    final = summary.get("final_status") or {}
    model = final.get("xg_model") or {}
    print(f"- Quality verdict: {final.get('quality_verdict')}")
    print(f"- Join rate avant alias: {final.get('join_rate_before_alias')}%")
    print(f"- Join rate apres alias: {final.get('join_rate_after_alias')}%")
    print(f"- Join quality: {final.get('join_quality')}")
    print(f"- Modeling allowed par jointure: {final.get('modeling_allowed_by_join_quality')}")
    print(f"- Rolling avg3/avg5: {final.get('rolling_avg3_rows')} / {final.get('rolling_avg5_rows')}")
    print(f"- Matchs uniques rolling: {final.get('unique_matches_rolling')}")
    print(f"- Brier marche/xG: {model.get('market_brier_test')} / {model.get('xg_brier_test')}")
    print(f"- Log loss marche/xG: {model.get('market_log_loss_test')} / {model.get('xg_log_loss_test')}")
    print(f"- ROI edge test: {model.get('roi_edge_test')}")
    print(f"- Promotion allowed: {model.get('promotion_allowed')}")
    for warning in summary.get("warnings") or []:
        print(f"- Avertissement: {warning}")
    print(f"- Conclusion: {summary.get('conclusion')}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Pipeline local Understat xG sans recuperation reseau.")
    parser.add_argument("--external", default=DEFAULT_EXTERNAL, help="CSV Understat deja exporte")
    parser.add_argument("--xgabora", default=DEFAULT_XGABORA, help="CSV features_modern.csv local")
    parser.add_argument("--out-prefix", default=DEFAULT_PREFIX, help="Prefixe des fichiers reports/")
    parser.add_argument("--league", default="EPL", help="Ligue attendue pour le quality gate")
    parser.add_argument("--expected-seasons", default=DEFAULT_EXPECTED_SEASONS, help="Saisons attendues")
    parser.add_argument("--skip-benchmark", action="store_true", help="Ignore benchmark_governance")
    parser.add_argument("--skip-model", action="store_true", help="Ignore xg_model_lab")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les etapes sans les lancer")
    parser.add_argument("--strict-join", action="store_true", help="Stoppe si la jointure apres alias est inferieure a 75%%")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = build_pipeline(
            args.external,
            args.xgabora,
            out_prefix=args.out_prefix,
            league=args.league,
            expected_seasons=args.expected_seasons,
            skip_model=args.skip_model,
            skip_benchmark=args.skip_benchmark,
            dry_run=args.dry_run,
            strict_join=args.strict_join,
        )
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
