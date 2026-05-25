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
    ReportCommand(
        "Benchmark governance",
        "benchmark_governance.txt",
        [
            "benchmark_governance.py",
            "--features",
            "data/features_modern.csv",
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
        return QUICK_COMMANDS + FULL_EXTRA_COMMANDS
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
    parser.add_argument("--output", default=None, help="Prefixe du dossier de sortie, ex: reports/oracle_report")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    mode = "full" if args.full else "quick"
    report_dir = resolve_report_dir(args.output)
    report_dir.mkdir(parents=True, exist_ok=True)
    print("Rapport central local Oracle Bot")
    print(f"- Mode: {mode}")
    print(f"- Dossier: {report_dir}")
    print("- Note: DATABASE_URL est vide pour ce processus; aucune memoire distante n'est utilisee.")
    manifest = run_report(command_set(mode), report_dir, Path.cwd())
    print("")
    print("Resume final")
    print(f"- Rapports OK: {manifest['ok']}")
    print(f"- Rapports en erreur: {manifest['failed']}")
    print(f"- Dossier genere: {report_dir}")
    print("- Aucune sortie ne declenche de pick automatique.")


if __name__ == "__main__":
    main()
