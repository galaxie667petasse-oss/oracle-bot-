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


def shadow_commands(
    ledger: str = "reports/shadow_ledger.csv",
    features: str = "data/features_modern.csv",
    skip_benchmark: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Shadow CLV report",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
            ],
            timeout=600,
        )
    ]
    if not skip_benchmark:
        commands.append(
            ReportCommand(
                "Benchmark governance shadow",
                "benchmark_governance_shadow.txt",
                [
                    "benchmark_governance.py",
                    "--features",
                    features,
                    "--shadow-report",
                    "{report_dir}/shadow_clv_report.json",
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
    commands.append(
        ReportCommand(
            "Dashboard shadow",
            "dashboard_builder.txt",
            ["dashboard_builder.py", "--input", "{report_dir}"],
            timeout=300,
        )
    )
    return commands


def daily_shadow_commands(
    ledger: str = "reports/shadow_ledger.csv",
    features: str = "data/features_modern.csv",
    skip_benchmark: bool = False,
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Shadow workflow init",
            "shadow_workflow_init.txt",
            ["shadow_workflow.py", "--ledger", ledger, "--init"],
            timeout=300,
        ),
        ReportCommand(
            "Shadow workflow closing template",
            "shadow_workflow_template.txt",
            ["shadow_workflow.py", "--ledger", ledger, "--make-closing-template"],
            timeout=300,
        ),
        ReportCommand(
            "Shadow CLV report",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
                "--summary-csv",
                "{report_dir}/shadow_clv_summary.csv",
            ],
            timeout=600,
        ),
    ]
    if not skip_benchmark:
        commands.append(
            ReportCommand(
                "Benchmark governance daily shadow",
                "benchmark_governance_shadow.txt",
                [
                    "benchmark_governance.py",
                    "--features",
                    features,
                    "--shadow-report",
                    "{report_dir}/shadow_clv_report.json",
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
    if not skip_dashboard:
        commands.append(
            ReportCommand(
                "Dashboard daily shadow",
                "dashboard_builder.txt",
                ["dashboard_builder.py", "--input", "{report_dir}"],
                timeout=300,
            )
        )
    return commands


def ops_commands(
    ledger: str = "reports/shadow_ledger.csv",
    skip_evidence: bool = False,
    skip_quality: bool = False,
    skip_sample_plan: bool = False,
    skip_dashboard: bool = False,
    simulated_ledger: str = "",
) -> List[ReportCommand]:
    active_ledger = simulated_ledger or ledger
    commands = [
        ReportCommand(
            "Oracle ops health",
            "oracle_ops_health.txt",
            ["oracle_ops.py", "--health", "--ledger", active_ledger],
            timeout=300,
        )
    ]
    if not skip_quality:
        commands.append(
            ReportCommand(
                "Shadow quality audit",
                "shadow_quality_audit.txt",
                [
                    "shadow_quality_audit.py",
                    "--ledger",
                    active_ledger,
                    "--output",
                    "{report_dir}/shadow_quality_audit.json",
                    "--html",
                    "{report_dir}/shadow_quality_audit.html",
                ],
                timeout=600,
            )
        )
    commands.append(
        ReportCommand(
            "Shadow CLV report ops",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                active_ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
                "--summary-csv",
                "{report_dir}/shadow_clv_summary.csv",
            ],
            timeout=600,
        )
    )
    if not skip_evidence:
        commands.append(
            ReportCommand(
                "Evidence gate",
                "evidence_gate.txt",
                [
                    "evidence_gate.py",
                    "--shadow-report",
                    "{report_dir}/shadow_clv_report.json",
                    "--quality-audit",
                    "{report_dir}/shadow_quality_audit.json",
                    "--big5-summary",
                    "reports/big5_xg_summary.json",
                    "--clv-readiness",
                    "reports/clv_readiness.json",
                    "--output",
                    "{report_dir}/evidence_gate.json",
                    "--html",
                    "{report_dir}/evidence_gate.html",
                ],
                timeout=600,
            )
        )
    if not skip_sample_plan:
        commands.append(
            ReportCommand(
                "Sample size plan",
                "sample_size_plan.txt",
                [
                    "sample_size_planner.py",
                    "--shadow-report",
                    "{report_dir}/shadow_clv_report.json",
                    "--output",
                    "{report_dir}/sample_size_plan.json",
                    "--html",
                    "{report_dir}/sample_size_plan.html",
                ],
                timeout=300,
            )
        )
    if not skip_dashboard:
        commands.append(
            ReportCommand(
                "Dashboard ops",
                "dashboard_builder.txt",
                ["dashboard_builder.py", "--input", "{report_dir}"],
                timeout=300,
            )
        )
    return commands


def odds_lab_commands(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    skip_evidence: bool = False,
    skip_quality: bool = False,
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Odds source config",
            "odds_source_config.txt",
            ["odds_source_config.py", "--check"],
            timeout=300,
        ),
        ReportCommand(
            "Odds snapshot summary",
            "odds_snapshot_store.txt",
            ["odds_snapshot_store.py", "--store", snapshots, "--summary", "--output", "{report_dir}/odds_snapshot_summary.json"],
            timeout=300,
        ),
    ]
    if not skip_quality:
        commands.append(
            ReportCommand(
                "Odds source quality",
                "odds_source_quality.txt",
                [
                    "odds_source_quality_report.py",
                    "--snapshots",
                    snapshots,
                    "--output",
                    "{report_dir}/odds_source_quality.json",
                    "--html",
                    "{report_dir}/odds_source_quality.html",
                ],
                timeout=300,
            )
        )
        commands.append(
            ReportCommand(
                "Shadow quality audit",
                "shadow_quality_audit.txt",
                [
                    "shadow_quality_audit.py",
                    "--ledger",
                    ledger,
                    "--output",
                    "{report_dir}/shadow_quality_audit.json",
                    "--html",
                    "{report_dir}/shadow_quality_audit.html",
                ],
                timeout=600,
            )
        )
    commands.append(
        ReportCommand(
            "Shadow CLV report odds lab",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
            ],
            timeout=600,
        )
    )
    if not skip_evidence:
        commands.append(
            ReportCommand(
                "Evidence gate odds lab",
                "evidence_gate.txt",
                [
                    "evidence_gate.py",
                    "--shadow-report",
                    "{report_dir}/shadow_clv_report.json",
                    "--quality-audit",
                    "{report_dir}/shadow_quality_audit.json",
                    "--big5-summary",
                    "reports/big5_xg_summary.json",
                    "--clv-readiness",
                    "reports/clv_readiness.json",
                    "--output",
                    "{report_dir}/evidence_gate.json",
                    "--html",
                    "{report_dir}/evidence_gate.html",
                ],
                timeout=600,
            )
        )
    if not skip_dashboard:
        commands.append(
            ReportCommand(
                "Dashboard odds lab",
                "dashboard_builder.txt",
                ["dashboard_builder.py", "--input", "{report_dir}"],
                timeout=300,
            )
        )
    return commands


def odds_intake_commands(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    skip_evidence: bool = False,
    skip_quality: bool = False,
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Odds snapshot summary",
            "odds_snapshot_store.txt",
            ["odds_snapshot_store.py", "--store", snapshots, "--summary", "--output", "{report_dir}/odds_snapshot_summary.json"],
            timeout=300,
        )
    ]
    if not skip_quality:
        commands.append(
            ReportCommand(
                "Odds source quality",
                "odds_source_quality.txt",
                [
                    "odds_source_quality_report.py",
                    "--snapshots",
                    snapshots,
                    "--output",
                    "{report_dir}/odds_source_quality.json",
                    "--html",
                    "{report_dir}/odds_source_quality.html",
                ],
                timeout=300,
            )
        )
    commands.append(
        ReportCommand(
            "Odds intake audit",
            "odds_intake_audit.txt",
            [
                "odds_intake_audit.py",
                "--snapshots",
                snapshots,
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/odds_intake_audit.json",
                "--html",
                "{report_dir}/odds_intake_audit.html",
            ],
            timeout=300,
        )
    )
    if not skip_quality:
        commands.append(
            ReportCommand(
                "Shadow quality audit",
                "shadow_quality_audit.txt",
                [
                    "shadow_quality_audit.py",
                    "--ledger",
                    ledger,
                    "--output",
                    "{report_dir}/shadow_quality_audit.json",
                    "--html",
                    "{report_dir}/shadow_quality_audit.html",
                ],
                timeout=600,
            )
        )
    if not skip_evidence:
        commands.append(
            ReportCommand(
                "Evidence gate odds intake",
                "evidence_gate.txt",
                [
                    "evidence_gate.py",
                    "--quality-audit",
                    "{report_dir}/shadow_quality_audit.json",
                    "--big5-summary",
                    "reports/big5_xg_summary.json",
                    "--clv-readiness",
                    "reports/clv_readiness.json",
                    "--output",
                    "{report_dir}/evidence_gate.json",
                    "--html",
                    "{report_dir}/evidence_gate.html",
                ],
                timeout=600,
            )
        )
    if not skip_dashboard:
        commands.append(
            ReportCommand(
                "Dashboard odds intake",
                "dashboard_builder.txt",
                ["dashboard_builder.py", "--input", "{report_dir}"],
                timeout=300,
            )
        )
    return commands


def proof_commands(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    historical_clv: str = "",
    sport_map: str = "config/sport_key_map.example.json",
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "External evidence catalog",
            "external_evidence_catalog.txt",
            [
                "external_evidence_catalog.py",
                "--output",
                "{report_dir}/external_evidence_catalog.json",
                "--html",
                "{report_dir}/external_evidence_catalog.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Shadow CLV report proof",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Shadow quality audit proof",
            "shadow_quality_audit.txt",
            [
                "shadow_quality_audit.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_quality_audit.json",
                "--html",
                "{report_dir}/shadow_quality_audit.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Near-close batch dry-run",
            "near_close_batch_runner.txt",
            [
                "near_close_batch_runner.py",
                "--ledger",
                ledger,
                "--snapshots",
                snapshots,
                "--sport-map",
                sport_map,
                "--dry-run",
                "--output",
                "{report_dir}/near_close_batch_runner.json",
                "--html",
                "{report_dir}/near_close_batch_runner.html",
            ],
            timeout=300,
        ),
    ]
    if historical_clv:
        commands.append(
            ReportCommand(
                "Historical CLV backtest",
                "historical_clv_backtest.txt",
                [
                    "historical_clv_backtester.py",
                    "--input",
                    historical_clv,
                    "--output",
                    "{report_dir}/historical_clv_backtest.json",
                    "--html",
                    "{report_dir}/historical_clv_backtest.html",
                ],
                timeout=600,
            )
        )
    commands.extend([
        ReportCommand(
            "Evidence gate proof",
            "evidence_gate.txt",
            [
                "evidence_gate.py",
                "--shadow-report",
                "{report_dir}/shadow_clv_report.json",
                "--quality-audit",
                "{report_dir}/shadow_quality_audit.json",
                "--big5-summary",
                "reports/big5_xg_summary.json",
                "--clv-readiness",
                "reports/clv_readiness.json",
                "--historical-clv",
                "{report_dir}/historical_clv_backtest.json",
                "--output",
                "{report_dir}/evidence_gate.json",
                "--html",
                "{report_dir}/evidence_gate.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Proof dashboard",
            "proof_dashboard.txt",
            [
                "proof_dashboard.py",
                "--shadow",
                "{report_dir}/shadow_clv_report.json",
                "--evidence",
                "{report_dir}/evidence_gate.json",
                "--big5",
                "reports/big5_xg_summary.json",
                "--historical-clv",
                "{report_dir}/historical_clv_backtest.json",
                "--quality",
                "{report_dir}/shadow_quality_audit.json",
                "--output",
                "{report_dir}/proof_dashboard.json",
                "--html",
                "{report_dir}/proof_dashboard.html",
            ],
            timeout=300,
        ),
    ])
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard proof", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
    return commands


def same_day_commands(
    ledger: str = "reports/shadow_ledger.csv",
    sport_map: str = "config/sport_key_map.example.json",
    date: str = "",
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    date = date or datetime.now().strftime("%Y-%m-%d")
    same_dir = f"{{report_dir}}/api_football_same_day_{date.replace('-', '_')}"
    commands = [
        ReportCommand(
            "API-Football same-day dry-run",
            "api_football_same_day_runner.txt",
            [
                "api_football_same_day_runner.py",
                "--date",
                date,
                "--dry-run",
                "--debug",
                "--ledger",
                ledger,
                "--output-dir",
                same_dir,
            ],
            timeout=600,
        ),
        ReportCommand(
            "API-Football odds debug same-day",
            "api_football_odds_debug_report.txt",
            [
                "api_football_odds_debug_report.py",
                "--odds",
                f"{same_dir}/odds_enriched.csv",
                "--output",
                "{report_dir}/api_football_odds_debug.json",
                "--html",
                "{report_dir}/api_football_odds_debug.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Near-close today helper",
            "near_close_today_helper.txt",
            [
                "near_close_today_helper.py",
                "--ledger",
                ledger,
                "--sport-map",
                sport_map,
                "--date",
                date,
                "--output",
                "{report_dir}/near_close_today.json",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Source coverage same-day",
            "source_coverage_report.txt",
            [
                "source_coverage_report.py",
                "--same-day-summary",
                f"{same_dir}/summary.json",
                "--output",
                "{report_dir}/source_coverage_report.json",
                "--html",
                "{report_dir}/source_coverage_report.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Evidence gate same-day",
            "evidence_gate.txt",
            [
                "evidence_gate.py",
                "--shadow-report",
                "reports/shadow_clv_report.json",
                "--big5-summary",
                "reports/big5_xg_summary.json",
                "--clv-readiness",
                "reports/clv_readiness.json",
                "--output",
                "{report_dir}/evidence_gate.json",
                "--html",
                "{report_dir}/evidence_gate.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Proof dashboard same-day",
            "proof_dashboard.txt",
            [
                "proof_dashboard.py",
                "--shadow",
                "reports/shadow_clv_report.json",
                "--evidence",
                "{report_dir}/evidence_gate.json",
                "--big5",
                "reports/big5_xg_summary.json",
                "--same-day",
                f"{same_dir}/summary.json",
                "--near-close-today",
                "{report_dir}/near_close_today.json",
                "--output",
                "{report_dir}/proof_dashboard.json",
                "--html",
                "{report_dir}/proof_dashboard.html",
            ],
            timeout=300,
        ),
    ]
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard same-day", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
    return commands


def api_odds_commands(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    scan_report: str = "{report_dir}/soccer_odds_sport_scan.json",
    selection_summary: str = "reports/shadow_selection_summary.json",
    near_close_plan: str = "{report_dir}/near_close_plan.json",
    skip_evidence: bool = False,
    skip_quality: bool = False,
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Soccer odds sport scanner",
            "soccer_odds_sport_scanner.txt",
            [
                "soccer_odds_sport_scanner.py",
                "--dry-run",
                "--output",
                scan_report,
                "--html",
                "{report_dir}/soccer_odds_sport_scan.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Near-close workflow status",
            "near_close_workflow.txt",
            [
                "near_close_workflow.py",
                "--ledger",
                ledger,
                "--status",
                "--output",
                near_close_plan,
                "--html",
                "{report_dir}/near_close_plan.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Real guard ledger scope",
            "real_observation_guard.txt",
            [
                "real_observation_guard.py",
                "--ledger",
                ledger,
                "--snapshots",
                snapshots,
                "--phase",
                "pre_match",
                "--scope",
                "ledger",
                "--output",
                "{report_dir}/real_observation_guard.json",
                "--html",
                "{report_dir}/real_observation_guard.html",
            ],
            timeout=300,
        ),
    ]
    if not skip_quality:
        commands.append(
            ReportCommand(
                "Odds source quality",
                "odds_source_quality.txt",
                [
                    "odds_source_quality_report.py",
                    "--snapshots",
                    snapshots,
                    "--output",
                    "{report_dir}/odds_source_quality.json",
                    "--html",
                    "{report_dir}/odds_source_quality.html",
                ],
                timeout=300,
            )
        )
    if not skip_evidence:
        commands.append(
            ReportCommand(
                "Evidence gate API odds",
                "evidence_gate.txt",
                [
                    "evidence_gate.py",
                    "--real-guard",
                    "{report_dir}/real_observation_guard.json",
                    "--big5-summary",
                    "reports/big5_xg_summary.json",
                    "--clv-readiness",
                    "reports/clv_readiness.json",
                    "--output",
                    "{report_dir}/evidence_gate.json",
                    "--html",
                    "{report_dir}/evidence_gate.html",
                ],
                timeout=600,
            )
        )
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard API odds", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
    return commands


def shadow_ops_commands(
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Event lifecycle",
            "event_lifecycle.txt",
            [
                "event_lifecycle_manager.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/event_lifecycle.json",
                "--html",
                "{report_dir}/event_lifecycle.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Near-close scheduler",
            "near_close_schedule.txt",
            [
                "near_close_scheduler.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/near_close_schedule.json",
                "--html",
                "{report_dir}/near_close_schedule.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Real guard ledger scope",
            "real_observation_guard.txt",
            [
                "real_observation_guard.py",
                "--ledger",
                ledger,
                "--snapshots",
                snapshots,
                "--phase",
                "pre_match",
                "--scope",
                "ledger",
                "--output",
                "{report_dir}/real_observation_guard.json",
                "--html",
                "{report_dir}/real_observation_guard.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Evidence gate lifecycle",
            "evidence_gate.txt",
            [
                "evidence_gate.py",
                "--lifecycle",
                "{report_dir}/event_lifecycle.json",
                "--real-guard",
                "{report_dir}/real_observation_guard.json",
                "--shadow-report",
                "reports/shadow_clv_report.json",
                "--output",
                "{report_dir}/evidence_gate.json",
                "--html",
                "{report_dir}/evidence_gate.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Shadow progress dashboard",
            "shadow_progress_dashboard.txt",
            [
                "shadow_progress_dashboard.py",
                "--ledger",
                ledger,
                "--lifecycle",
                "{report_dir}/event_lifecycle.json",
                "--evidence",
                "{report_dir}/evidence_gate.json",
                "--output",
                "{report_dir}/shadow_progress_dashboard.html",
                "--json",
                "{report_dir}/shadow_progress_dashboard.json",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Odds autopilot dry-run",
            "odds_autopilot_dryrun.txt",
            [
                "odds_autopilot_dryrun.py",
                "--ledger",
                ledger,
                "--snapshots",
                snapshots,
                "--reports-dir",
                "{report_dir}",
                "--output",
                "{report_dir}/odds_autopilot_dryrun.json",
                "--html",
                "{report_dir}/odds_autopilot_dryrun.html",
            ],
            timeout=300,
        ),
    ]
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard shadow ops", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
    return commands


def project_blueprint_commands(skip_evidence: bool = False, skip_dashboard: bool = False) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Architecture canonique",
            "architecture_map.txt",
            [
                "oracle_architecture_map.py",
                "--show",
                "--status",
                "--json",
                "{report_dir}/architecture_map.json",
                "--html",
                "{report_dir}/architecture_map.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Pipeline contracts",
            "pipeline_contracts.txt",
            [
                "pipeline_contracts.py",
                "--list",
                "--json",
                "{report_dir}/pipeline_contracts.json",
                "--html",
                "{report_dir}/pipeline_contracts.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Project scorecard",
            "project_scorecard.txt",
            [
                "oracle_project_scorecard.py",
                "--output",
                "{report_dir}/project_scorecard.json",
                "--html",
                "{report_dir}/project_scorecard.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "LLM analyst contract",
            "llm_analyst_contract.txt",
            [
                "llm_analyst_contract.py",
                "--show",
                "--template-json",
                "{report_dir}/llm_analyst_input_template.json",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Restitution schema",
            "restitution_schema.txt",
            [
                "restitution_schema.py",
                "--template",
                "{report_dir}/restitution_template.json",
                "--render",
                "{report_dir}/restitution_template.json",
                "--output",
                "{report_dir}/restitution_preview.txt",
                "--html",
                "{report_dir}/restitution_preview.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Progress loop",
            "progress_loop.txt",
            [
                "progress_loop.py",
                "--path",
                "{report_dir}/progress_loop.csv",
                "--init",
                "--summary",
                "--html",
                "{report_dir}/progress_loop.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Agent dry-run",
            "agent_orchestrator_dryrun.txt",
            ["agent_orchestrator_dryrun.py", "--full"],
            timeout=300,
        ),
    ]
    if not skip_evidence:
        commands.append(
            ReportCommand(
                "Evidence gate blueprint",
                "evidence_gate.txt",
                [
                    "evidence_gate.py",
                    "--shadow-report",
                    "reports/shadow_clv_report.json",
                    "--quality-audit",
                    "reports/shadow_quality_audit.json",
                    "--big5-summary",
                    "reports/big5_xg_summary.json",
                    "--clv-readiness",
                    "reports/clv_readiness.json",
                    "--output",
                    "{report_dir}/evidence_gate.json",
                    "--html",
                    "{report_dir}/evidence_gate.html",
                ],
                timeout=600,
            )
        )
    if not skip_dashboard:
        commands.append(
            ReportCommand(
                "Dashboard blueprint",
                "dashboard_builder.txt",
                ["dashboard_builder.py", "--input", "{report_dir}"],
                timeout=300,
            )
        )
    return commands


def matchday_commands(
    matchday_pack: str = "reports/matchday_2026_06_01",
    ledger: str = "reports/shadow_ledger.csv",
    snapshots: str = "reports/odds_snapshots.csv",
    phase: str = "full_day",
    skip_dashboard: bool = False,
) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "Matchday status",
            "matchday_status.txt",
            [
                "matchday_status_report.py",
                "--pack",
                matchday_pack,
                "--output",
                "{report_dir}/matchday_status.json",
                "--html",
                "{report_dir}/matchday_status.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Matchday runner dry-run",
            "matchday_runner.txt",
            ["matchday_runner.py", "--pack", matchday_pack, "--full-dry-run", "--phase", phase],
            timeout=300,
        ),
        ReportCommand(
            "Real observation guard",
            "real_observation_guard.txt",
            [
                "real_observation_guard.py",
                "--ledger",
                ledger,
                "--snapshots",
                snapshots,
                "--output",
                "{report_dir}/real_observation_guard.json",
                "--html",
                "{report_dir}/real_observation_guard.html",
                "--phase",
                phase,
            ],
            timeout=300,
        ),
        ReportCommand(
            "Shadow CLV report matchday",
            "shadow_clv_report.txt",
            [
                "shadow_clv_report.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_clv_report.json",
                "--html",
                "{report_dir}/shadow_clv_report.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Shadow quality audit matchday",
            "shadow_quality_audit.txt",
            [
                "shadow_quality_audit.py",
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/shadow_quality_audit.json",
                "--html",
                "{report_dir}/shadow_quality_audit.html",
            ],
            timeout=600,
        ),
        ReportCommand(
            "Odds intake audit matchday",
            "odds_intake_audit.txt",
            [
                "odds_intake_audit.py",
                "--snapshots",
                snapshots,
                "--ledger",
                ledger,
                "--output",
                "{report_dir}/odds_intake_audit.json",
                "--html",
                "{report_dir}/odds_intake_audit.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Evidence gate matchday",
            "evidence_gate.txt",
            [
                "evidence_gate.py",
                "--shadow-report",
                "{report_dir}/shadow_clv_report.json",
                "--quality-audit",
                "{report_dir}/shadow_quality_audit.json",
                "--big5-summary",
                "reports/big5_xg_summary.json",
                "--clv-readiness",
                "reports/clv_readiness.json",
                "--real-guard",
                "{report_dir}/real_observation_guard.json",
                "--matchday-status",
                "{report_dir}/matchday_status.json",
                "--output",
                "{report_dir}/evidence_gate.json",
                "--html",
                "{report_dir}/evidence_gate.html",
            ],
            timeout=600,
        ),
    ]
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard matchday", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
    return commands


def source_coverage_commands(skip_dashboard: bool = False) -> List[ReportCommand]:
    commands = [
        ReportCommand(
            "The Odds API active sports dry-run",
            "the_odds_active_sports.txt",
            ["the_odds_active_sports.py", "--dry-run"],
            timeout=120,
        ),
        ReportCommand(
            "Source coverage report",
            "source_coverage_report.txt",
            [
                "source_coverage_report.py",
                "--active-sports",
                "reports/the_odds_api_active_soccer_sports.json",
                "--the-odds-scan",
                "reports/soccer_odds_sport_scan.json",
                "--fixtures",
                "reports/api_football_matchday_probe.json",
                "--manual-pack",
                "reports/matchday_from_intake",
                "--output",
                "{report_dir}/source_coverage_report.json",
                "--html",
                "{report_dir}/source_coverage_report.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "API-Football matchday dry-run",
            "api_football_matchday_probe.txt",
            ["api_football_matchday_probe.py", "--dry-run", "--date", "2026-06-03"],
            timeout=120,
        ),
        ReportCommand(
            "Near-close scheduler",
            "near_close_schedule.txt",
            [
                "near_close_scheduler.py",
                "--ledger",
                "reports/shadow_ledger.csv",
                "--output",
                "{report_dir}/near_close_schedule.json",
                "--html",
                "{report_dir}/near_close_schedule.html",
            ],
            timeout=300,
        ),
        ReportCommand(
            "Evidence gate source coverage",
            "evidence_gate.txt",
            [
                "evidence_gate.py",
                "--shadow-report",
                "reports/shadow_clv_report.json",
                "--quality-audit",
                "reports/shadow_quality_audit.json",
                "--big5-summary",
                "reports/big5_xg_summary.json",
                "--clv-readiness",
                "reports/clv_readiness.json",
                "--output",
                "{report_dir}/evidence_gate.json",
                "--html",
                "{report_dir}/evidence_gate.html",
            ],
            timeout=300,
        ),
    ]
    if not skip_dashboard:
        commands.append(ReportCommand("Dashboard source coverage", "dashboard_builder.txt", ["dashboard_builder.py", "--input", "{report_dir}"], timeout=300))
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
    if mode == "shadow":
        return shadow_commands()
    if mode == "daily-shadow":
        return daily_shadow_commands()
    if mode == "ops":
        return ops_commands()
    if mode == "odds-lab":
        return odds_lab_commands()
    if mode == "odds-intake":
        return odds_intake_commands()
    if mode == "api-odds":
        return api_odds_commands()
    if mode == "shadow-ops":
        return shadow_ops_commands()
    if mode == "project-blueprint":
        return project_blueprint_commands()
    if mode == "matchday":
        return matchday_commands()
    if mode == "source-coverage":
        return source_coverage_commands()
    if mode == "proof":
        return proof_commands()
    if mode == "same-day":
        return same_day_commands()
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
    mode.add_argument("--shadow", action="store_true", help="Lance le rapport shadow mode et la gouvernance locale")
    mode.add_argument("--daily-shadow", action="store_true", help="Lance le workflow quotidien shadow local")
    mode.add_argument("--ops", action="store_true", help="Lance le centre operations shadow local")
    mode.add_argument("--odds-lab", action="store_true", help="Lance le laboratoire local des sources de cotes")
    mode.add_argument("--odds-intake", action="store_true", help="Lance l'audit local du workflow odds intake")
    mode.add_argument("--api-odds", action="store_true", help="Lance les rapports API odds soccer sans reseau")
    mode.add_argument("--shadow-ops", action="store_true", help="Lance le lifecycle shadow, near-close scheduler et dashboard evidence local")
    mode.add_argument("--source-coverage", action="store_true", help="Lance le rapport de couverture sources sans reseau")
    mode.add_argument("--project-blueprint", action="store_true", help="Lance la carte architecture, contrats, scorecard et restitution")
    mode.add_argument("--matchday", action="store_true", help="Lance le rapport local de collecte matchday")
    mode.add_argument("--proof", action="store_true", help="Lance les rapports evidence acceleration V9.1 sans reseau")
    mode.add_argument("--same-day", action="store_true", help="Lance le workflow same-day V9.2 sans reseau")
    parser.add_argument("--output", default=None, help="Prefixe du dossier de sortie, ex: reports/oracle_report")
    parser.add_argument("--external-xg", default=DEFAULT_UNDERSTAT_XG, help="CSV Understat local deja exporte")
    parser.add_argument("--xgabora", default="data/features_modern.csv", help="CSV xgabora/features local")
    parser.add_argument("--closing-source", default="data/MATCHES.csv", help="CSV source closing odds pour --closing-readiness")
    parser.add_argument("--source-csv", default="", help="Alias de --closing-source pour --closing-preview")
    parser.add_argument("--features", default="", help="Alias explicite du CSV features pour --closing-preview")
    parser.add_argument("--preview-output", default="reports/features_with_closing_preview.csv", help="Sortie preview CLV partielle dans reports/")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv", help="Ledger shadow mode pour --shadow")
    parser.add_argument("--snapshots", default="reports/odds_snapshots.csv", help="Snapshots de cotes pour --odds-lab")
    parser.add_argument("--matchday-pack", default="reports/matchday_2026_06_01", help="Pack matchday pour --matchday")
    parser.add_argument("--scan-report", default="{report_dir}/soccer_odds_sport_scan.json", help="Rapport scan sports soccer a ecrire")
    parser.add_argument("--selection-summary", default="reports/shadow_selection_summary.json", help="Resume selection shadow existant")
    parser.add_argument("--near-close-plan", default="{report_dir}/near_close_plan.json", help="Plan near-close a ecrire")
    parser.add_argument("--historical-clv", default="", help="CSV CLV historique normalise optionnel pour --proof")
    parser.add_argument("--sport-map", default="config/sport_key_map.example.json", help="Mapping ligue -> sport key pour near-close")
    parser.add_argument("--date", default="", help="Date locale YYYY-MM-DD pour les modes matchday/same-day")
    parser.add_argument("--out-prefix", default=DEFAULT_UNDERSTAT_PREFIX, help="Prefixe des sorties reports/ du pipeline xG")
    parser.add_argument("--skip-benchmark", action="store_true", help="Pour --xg-understat/--big5-xg: ignore benchmark_governance")
    parser.add_argument("--skip-dashboard", action="store_true", help="Pour --daily-shadow: ignore dashboard_builder")
    parser.add_argument("--skip-evidence", action="store_true", help="Pour --ops: ignore evidence_gate")
    parser.add_argument("--skip-quality", action="store_true", help="Pour --ops: ignore shadow_quality_audit")
    parser.add_argument("--skip-sample-plan", action="store_true", help="Pour --ops: ignore sample_size_planner")
    parser.add_argument("--simulated-ledger", default="", help="Pour --ops: ledger shadow simule a utiliser")
    parser.add_argument("--skip-model", action="store_true", help="Pour --xg-understat: ignore xg_model_lab")
    parser.add_argument("--dry-run", action="store_true", help="Pour --xg-understat: affiche les etapes sans lancer le pipeline")
    parser.add_argument("--phase", default="full_day", help="Phase matchday: pre_match, near_close, post_match ou full_day")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    mode = (
        "closing-readiness" if args.closing_readiness
        else "closing-preview" if args.closing_preview
        else "shadow" if args.shadow
        else "daily-shadow" if args.daily_shadow
        else "ops" if args.ops
        else "odds-lab" if args.odds_lab
        else "odds-intake" if args.odds_intake
        else "api-odds" if args.api_odds
        else "shadow-ops" if args.shadow_ops
        else "source-coverage" if args.source_coverage
        else "project-blueprint" if args.project_blueprint
        else "matchday" if args.matchday
        else "proof" if args.proof
        else "same-day" if args.same_day
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
    elif mode == "shadow":
        commands = shadow_commands(
            ledger=args.ledger,
            features=args.features or args.xgabora,
            skip_benchmark=args.skip_benchmark,
        )
    elif mode == "daily-shadow":
        commands = daily_shadow_commands(
            ledger=args.ledger,
            features=args.features or args.xgabora,
            skip_benchmark=args.skip_benchmark,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "ops":
        commands = ops_commands(
            ledger=args.ledger,
            skip_evidence=args.skip_evidence,
            skip_quality=args.skip_quality,
            skip_sample_plan=args.skip_sample_plan,
            skip_dashboard=args.skip_dashboard,
            simulated_ledger=args.simulated_ledger,
        )
    elif mode == "odds-lab":
        commands = odds_lab_commands(
            ledger=args.ledger,
            snapshots=args.snapshots,
            skip_evidence=args.skip_evidence,
            skip_quality=args.skip_quality,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "odds-intake":
        commands = odds_intake_commands(
            ledger=args.ledger,
            snapshots=args.snapshots,
            skip_evidence=args.skip_evidence,
            skip_quality=args.skip_quality,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "api-odds":
        commands = api_odds_commands(
            ledger=args.ledger,
            snapshots=args.snapshots,
            scan_report=args.scan_report,
            selection_summary=args.selection_summary,
            near_close_plan=args.near_close_plan,
            skip_evidence=args.skip_evidence,
            skip_quality=args.skip_quality,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "shadow-ops":
        commands = shadow_ops_commands(
            ledger=args.ledger,
            snapshots=args.snapshots,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "source-coverage":
        commands = source_coverage_commands(skip_dashboard=args.skip_dashboard)
    elif mode == "project-blueprint":
        commands = project_blueprint_commands(
            skip_evidence=args.skip_evidence,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "matchday":
        commands = matchday_commands(
            matchday_pack=args.matchday_pack,
            ledger=args.ledger,
            snapshots=args.snapshots,
            phase=args.phase,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "proof":
        commands = proof_commands(
            ledger=args.ledger,
            snapshots=args.snapshots,
            historical_clv=args.historical_clv,
            sport_map=args.sport_map,
            skip_dashboard=args.skip_dashboard,
        )
    elif mode == "same-day":
        commands = same_day_commands(
            ledger=args.ledger,
            sport_map=args.sport_map,
            date=args.date,
            skip_dashboard=args.skip_dashboard,
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
