import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional


@dataclass
class ReportCommand:
    name: str
    filename: str
    args: List[str]
    timeout: int = 900


QUICK_COMMANDS = [
    ReportCommand("Pricing report", "pricing_report.txt", ["backtest_evaluator.py", "--pricing-report"]),
    ReportCommand("Backtest modern", "backtest_modern.txt", ["backtest_evaluator.py", "--preset", "modern"]),
    ReportCommand("Favorite report", "favorite_report.txt", ["backtest_evaluator.py", "--favorite-report"]),
    ReportCommand("Stability report", "stability_report.txt", ["backtest_evaluator.py", "--stability-report"]),
]

FULL_EXTRA_COMMANDS = [
    ReportCommand("Backtest recent", "backtest_recent.txt", ["backtest_evaluator.py", "--preset", "recent"]),
    ReportCommand("Period report", "period_report.txt", ["backtest_evaluator.py", "--period-report"]),
    ReportCommand("ML global", "ml_global.txt", ["model_trainer.py", "--features", "data/features_modern.csv"], timeout=1200),
    ReportCommand("ML H2H", "ml_h2h.txt", ["model_trainer.py", "--features", "data/features_modern.csv", "--market", "h2h"], timeout=1200),
    ReportCommand("ML total", "ml_total.txt", ["model_trainer.py", "--features", "data/features_modern.csv", "--market", "total"], timeout=1200),
    ReportCommand("External dataset profile", "external_profile.txt", ["external_dataset_probe.py", "--profile-csv", "data/features_modern.csv"]),
    ReportCommand("External dataset recommendation", "external_recommend.txt", ["external_dataset_probe.py", "--recommend", "data/features_modern.csv"]),
    ReportCommand("External xG rolling lab", "xg_model_lab.txt", ["xg_model_lab.py", "--features", "reports/epl_xg_rolling_features.csv"], timeout=1200),
]

STATISTICAL_COMMANDS = [
    ReportCommand(
        "CLV analysis",
        "clv_report.txt",
        [
            "clv_analysis.py",
            "--features",
            "data/features_modern.csv",
            "--output",
            "{report_dir}/clv_report.json",
            "--html",
            "{report_dir}/clv_report.html",
        ],
        timeout=900,
    ),
    ReportCommand(
        "Calibration report",
        "calibration_report.txt",
        [
            "calibration_report.py",
            "--features",
            "data/features_modern.csv",
            "--prob-column",
            "no_vig_probability",
            "--output",
            "{report_dir}/calibration_report.json",
            "--html",
            "{report_dir}/calibration_report.html",
        ],
        timeout=900,
    ),
    ReportCommand(
        "Statistical validation",
        "statistical_validation.txt",
        [
            "statistical_validation.py",
            "--features",
            "data/features_modern.csv",
            "--output",
            "{report_dir}/statistical_validation.json",
            "--html",
            "{report_dir}/statistical_validation.html",
        ],
        timeout=1200,
    ),
    ReportCommand(
        "Benchmark governance",
        "benchmark_governance.txt",
        [
            "benchmark_governance.py",
            "--features",
            "data/features_modern.csv",
            "--xg-lab",
            "reports/epl_xg_rolling_features.csv",
            "--clv-report",
            "{report_dir}/clv_report.json",
            "--calibration-report",
            "{report_dir}/calibration_report.json",
            "--statistical-report",
            "{report_dir}/statistical_validation.json",
            "--summary-json",
            "{report_dir}/benchmark_summary.json",
            "--html",
            "{report_dir}/benchmark_governance.html",
            "--registry",
            "{report_dir}/model_registry.json",
        ],
        timeout=1800,
    ),
]

DEFAULT_UNDERSTAT_XG = "external_data/understat_probe/epl_2020_2025_matches.csv"
DEFAULT_UNDERSTAT_PREFIX = "understat_epl_2020_2025"


def xg_understat_commands(
    external_xg: str = DEFAULT_UNDERSTAT_XG,
    xgabora: str = "data/features_modern.csv",
    out_prefix: str = DEFAULT_UNDERSTAT_PREFIX,
    skip_benchmark: bool = False,
    skip_model: bool = False,
    dry_run: bool = False,
) -> List[ReportCommand]:
    args = [
        "understat_xg_pipeline.py",
        "--external",
        external_xg,
        "--xgabora",
        xgabora,
        "--out-prefix",
        out_prefix,
    ]
    if skip_benchmark:
        args.append("--skip-benchmark")
    if skip_model:
        args.append("--skip-model")
    if dry_run:
        args.append("--dry-run")
    return [ReportCommand("Understat xG Full Pipeline Quality Gate", "understat_xg_pipeline.txt", args, timeout=2400)]


def big5_xg_commands(
    features: str = "data/features_modern.csv",
    skip_benchmark: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Big 5 xG aggregator",
            "big5_xg_summary.txt",
            [
                "multi_league_xg_aggregator.py",
                "--reports-dir",
                "reports",
                "--output",
                "{report_dir}/big5_xg_summary.json",
                "--html",
                "{report_dir}/big5_xg_summary.html",
            ],
            timeout=900,
        ),
        ReportCommand(
            "CLV readiness",
            "clv_readiness.txt",
            [
                "clv_readiness_report.py",
                "--features",
                features,
                "--output",
                "{report_dir}/clv_readiness.json",
                "--html",
                "{report_dir}/clv_readiness.html",
            ],
            timeout=900,
        ),
    ]
    if not skip_benchmark:
        commands.append(
            ReportCommand(
                "Benchmark governance Big 5",
                "benchmark_governance_big5.txt",
                [
                    "benchmark_governance.py",
                    "--features",
                    features,
                    "--big5-xg-summary",
                    "{report_dir}/big5_xg_summary.json",
                    "--clv-readiness",
                    "{report_dir}/clv_readiness.json",
                    "--summary-json",
                    "{report_dir}/benchmark_summary.json",
                    "--html",
                    "{report_dir}/benchmark_governance.html",
                    "--registry",
                    "{report_dir}/model_registry.json",
                ],
                timeout=1800,
            )
        )
    return commands


def closing_readiness_commands(
    features: str = "data/features_modern.csv",
    source_csv: str = "data/MATCHES.csv",
    skip_benchmark: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Closing odds probe",
            "closing_odds_probe.txt",
            [
                "closing_odds_probe.py",
                "--csv",
                source_csv,
                "--output",
                "{report_dir}/closing_odds_probe.json",
                "--html",
                "{report_dir}/closing_odds_probe.html",
            ],
            timeout=900,
        ),
        ReportCommand(
            "CLV readiness enrichi",
            "clv_readiness.txt",
            [
                "clv_readiness_report.py",
                "--features",
                features,
                "--closing-probe",
                "{report_dir}/closing_odds_probe.json",
                "--output",
                "{report_dir}/clv_readiness.json",
                "--html",
                "{report_dir}/clv_readiness.html",
            ],
            timeout=900,
        ),
    ]
    if not skip_benchmark:
        commands.append(
            ReportCommand(
                "Benchmark governance closing readiness",
                "benchmark_governance_closing.txt",
                [
                    "benchmark_governance.py",
                    "--features",
                    features,
                    "--clv-readiness",
                    "{report_dir}/clv_readiness.json",
                    "--closing-probe",
                    "{report_dir}/closing_odds_probe.json",
                    "--summary-json",
                    "{report_dir}/benchmark_summary.json",
                    "--html",
                    "{report_dir}/benchmark_governance.html",
                    "--registry",
                    "{report_dir}/model_registry.json",
                ],
                timeout=1800,
            )
        )
    return commands


def closing_preview_commands(
    features: str = "data/features_modern.csv",
    source_csv: str = "data/MATCHES.csv",
    preview_output: str = "reports/features_with_closing_preview.csv",
    skip_benchmark: bool = False,
) -> List[ReportCommand]:
    if "data" in [part.lower() for part in Path(preview_output).parts]:
        raise ValueError("La preview closing ne doit pas etre ecrite dans data/.")
    commands = [
        ReportCommand(
            "Closing odds probe",
            "closing_odds_probe.txt",
            [
                "closing_odds_probe.py",
                "--csv",
                source_csv,
                "--output",
                "{report_dir}/closing_odds_probe.json",
                "--html",
                "{report_dir}/closing_odds_probe.html",
            ],
            timeout=900,
        ),
        ReportCommand(
            "Features closing preview",
            "features_closing_enricher.txt",
            [
                "features_closing_enricher.py",
                "--features",
                features,
                "--source",
                source_csv,
                "--output",
                preview_output,
            ],
            timeout=1800,
        ),
        ReportCommand(
            "CLV partial analysis",
            "clv_partial_report.txt",
            [
                "clv_analysis.py",
                "--features",
                preview_output,
                "--output",
                "{report_dir}/clv_partial_report.json",
                "--html",
                "{report_dir}/clv_partial_report.html",
            ],
            timeout=1200,
        ),
        ReportCommand(
            "CLV readiness preview",
            "clv_readiness.txt",
            [
                "clv_readiness_report.py",
                "--features",
                features,
                "--closing-probe",
                "{report_dir}/closing_odds_probe.json",
                "--preview",
                preview_output,
                "--output",
                "{report_dir}/clv_readiness.json",
                "--html",
                "{report_dir}/clv_readiness.html",
            ],
            timeout=900,
        ),
    ]
    if not skip_benchmark:
        commands.append(
            ReportCommand(
                "Benchmark governance CLV partielle",
                "benchmark_governance_closing_preview.txt",
                [
                    "benchmark_governance.py",
                    "--features",
                    features,
                    "--clv-report",
                    "{report_dir}/clv_partial_report.json",
                    "--clv-readiness",
                    "{report_dir}/clv_readiness.json",
                    "--closing-probe",
                    "{report_dir}/closing_odds_probe.json",
                    "--summary-json",
                    "{report_dir}/benchmark_summary.json",
                    "--html",
                    "{report_dir}/benchmark_governance.html",
                    "--registry",
                    "{report_dir}/model_registry.json",
                ],
                timeout=1800,
            )
        )
    return commands


def timestamp() -> str:
    return datetime.now().strftime("%Y_%m_%d_%H%M%S")


def resolve_report_dir(output: Optional[str] = None) -> Path:
    stamp = timestamp()
    if not output:
        base = Path("reports")
        base.mkdir(parents=True, exist_ok=True)
        return base / f"oracle_{stamp}"
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.parent / f"{target.name}_{stamp}"


def command_set(mode: str) -> List[ReportCommand]:
    if mode == "full":
        return QUICK_COMMANDS + FULL_EXTRA_COMMANDS + STATISTICAL_COMMANDS
    if mode == "statistical":
        return list(STATISTICAL_COMMANDS)
    if mode == "xg-understat":
        return xg_understat_commands()
    if mode == "big5-xg":
        return big5_xg_commands()
    if mode == "closing-readiness":
        return closing_readiness_commands()
    if mode == "closing-preview":
        return closing_preview_commands()
    return list(QUICK_COMMANDS)


def local_env() -> Dict[str, str]:
    env = dict(os.environ)
    env["DATABASE_URL"] = ""
    env["PYTHONUTF8"] = "1"
    return env


def run_one(command: ReportCommand, report_dir: Path, cwd: Path, env: Dict[str, str]) -> Dict[str, object]:
    started = datetime.now().isoformat(timespec="seconds")
    expanded_args = [arg.replace("{report_dir}", str(report_dir)) for arg in command.args]
    full_command = [sys.executable, *expanded_args]
    output_path = report_dir / command.filename
    start_time = time.time()
    status = {
        "name": command.name,
        "filename": command.filename,
        "command": " ".join(full_command),
        "started_at": started,
        "returncode": None,
        "duration_seconds": None,
        "ok": False,
        "error": "",
    }
    try:
        completed = subprocess.run(
            full_command,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=command.timeout,
        )
        duration = round(time.time() - start_time, 2)
        status.update({
            "returncode": completed.returncode,
            "duration_seconds": duration,
            "ok": completed.returncode == 0,
        })
        output_path.write_text(
            "\n".join([
                f"Rapport: {command.name}",
                f"Commande: {' '.join(full_command)}",
                f"Debut: {started}",
                f"Duree secondes: {duration}",
                f"Code retour: {completed.returncode}",
                "",
                "=== STDOUT ===",
                completed.stdout,
                "",
                "=== STDERR ===",
                completed.stderr,
            ]),
            encoding="utf-8",
        )
        if completed.returncode != 0:
            status["error"] = completed.stderr.strip() or completed.stdout.strip()
    except Exception as exc:
        duration = round(time.time() - start_time, 2)
        status.update({"duration_seconds": duration, "ok": False, "error": str(exc)})
        output_path.write_text(
            "\n".join([
                f"Rapport: {command.name}",
                f"Commande: {' '.join(full_command)}",
                f"Debut: {started}",
                f"Duree secondes: {duration}",
                "Code retour: erreur",
                "",
                "=== ERREUR ===",
                str(exc),
            ]),
            encoding="utf-8",
        )
    return status


def run_report(commands: Iterable[ReportCommand], report_dir: Path, cwd: Optional[Path] = None) -> Dict[str, object]:
    cwd = cwd or Path.cwd()
    report_dir.mkdir(parents=True, exist_ok=True)
    env = local_env()
    results = []
    for command in commands:
        print(f"- Lancement: {command.name}")
        result = run_one(command, report_dir, cwd, env)
        results.append(result)
        if result["ok"]:
            print(f"  OK ({result['duration_seconds']}s) -> {result['filename']}")
        else:
            print(f"  Erreur enregistree, poursuite du rapport -> {result['filename']}")
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_dir": str(report_dir),
        "results": results,
        "ok": sum(1 for result in results if result.get("ok")),
        "failed": sum(1 for result in results if not result.get("ok")),
    }
    (report_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Lance les rapports locaux Oracle Bot sans modifier la memoire.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true", help="Lance le rapport rapide")
    mode.add_argument("--full", action="store_true", help="Lance tous les rapports locaux")
    mode.add_argument("--statistical", action="store_true", help="Lance CLV, calibration, validation statistique et gouvernance")
    mode.add_argument("--xg-understat", action="store_true", help="Lance le pipeline local Understat xG multi-saisons")
    mode.add_argument("--big5-xg", action="store_true", help="Lance l'agregateur Big 5 xG et CLV readiness sans reseau")
    mode.add_argument("--closing-readiness", action="store_true", help="Inspecte les closing odds source et met a jour la readiness CLV")
    mode.add_argument("--closing-preview", action="store_true", help="Construit la preview CLV partielle dans reports/ et l'analyse")
    parser.add_argument("--output", default=None, help="Prefixe du dossier de sortie, ex: reports/oracle_report")
    parser.add_argument("--external-xg", default=DEFAULT_UNDERSTAT_XG, help="CSV Understat local deja exporte")
    parser.add_argument("--xgabora", default="data/features_modern.csv", help="CSV xgabora/features local")
    parser.add_argument("--closing-source", default="data/MATCHES.csv", help="CSV source closing odds pour --closing-readiness")
    parser.add_argument("--source-csv", default="", help="Alias de --closing-source pour --closing-preview")
    parser.add_argument("--features", default="", help="Alias explicite du CSV features pour --closing-preview")
    parser.add_argument("--preview-output", default="reports/features_with_closing_preview.csv", help="Sortie preview CLV partielle dans reports/")
    parser.add_argument("--out-prefix", default=DEFAULT_UNDERSTAT_PREFIX, help="Prefixe des sorties reports/ du pipeline xG")
    parser.add_argument("--skip-benchmark", action="store_true", help="Pour --xg-understat/--big5-xg: ignore benchmark_governance")
    parser.add_argument("--skip-model", action="store_true", help="Pour --xg-understat: ignore xg_model_lab")
    parser.add_argument("--dry-run", action="store_true", help="Pour --xg-understat: affiche les etapes sans lancer le pipeline")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    mode = (
        "closing-readiness" if args.closing_readiness
        else "closing-preview" if args.closing_preview
        else "big5-xg" if args.big5_xg
        else "xg-understat" if args.xg_understat
        else "full" if args.full
        else "statistical" if args.statistical
        else "quick"
    )
    report_dir = resolve_report_dir(args.output)
    report_dir.mkdir(parents=True, exist_ok=True)
    print("Rapport central local Oracle Bot")
    print(f"- Mode: {mode}")
    print(f"- Dossier: {report_dir}")
    print("- Note: DATABASE_URL est vide pour ce processus; aucune memoire distante n'est utilisee.")
    if mode == "xg-understat":
        commands = xg_understat_commands(
            external_xg=args.external_xg,
            xgabora=args.xgabora,
            out_prefix=args.out_prefix,
            skip_benchmark=args.skip_benchmark,
            skip_model=args.skip_model,
            dry_run=args.dry_run,
        )
    elif mode == "big5-xg":
        commands = big5_xg_commands(features=args.xgabora, skip_benchmark=args.skip_benchmark)
    elif mode == "closing-readiness":
        commands = closing_readiness_commands(
            features=args.features or args.xgabora,
            source_csv=args.source_csv or args.closing_source,
            skip_benchmark=args.skip_benchmark,
        )
    elif mode == "closing-preview":
        commands = closing_preview_commands(
            features=args.features or args.xgabora,
            source_csv=args.source_csv or args.closing_source,
            preview_output=args.preview_output,
            skip_benchmark=args.skip_benchmark,
        )
    else:
        commands = command_set(mode)
    manifest = run_report(commands, report_dir, Path.cwd())
    print("")
    print("Resume final")
    print(f"- Rapports OK: {manifest['ok']}")
    print(f"- Rapports en erreur: {manifest['failed']}")
    print(f"- Dossier genere: {report_dir}")
    print("- Aucune sortie ne declenche de pick automatique.")


if __name__ == "__main__":
    main()
