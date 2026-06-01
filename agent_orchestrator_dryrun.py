import argparse
from typing import List


DAILY_STEPS = [
    "Verifier oracle_ops --health",
    "Verifier le ledger shadow",
    "Lister pending closing",
    "Lister pending results",
    "Generer templates si besoin",
    "Relancer shadow_quality_audit",
    "Relancer evidence_gate",
]

ODDS_STEPS = [
    "Verifier odds_source_config sans cle affichee",
    "Valider le CSV manuel de cotes",
    "Resumer odds_snapshots",
    "Convertir snapshots taken en shadow en dry-run",
    "Matcher near-close en dry-run",
    "Auditer odds_intake",
]

EVIDENCE_STEPS = [
    "Generer shadow_clv_report",
    "Auditer qualite ledger",
    "Lire Big 5 summary si disponible",
    "Lire CLV readiness si disponible",
    "Executer evidence_gate",
    "Generer restitution preview",
]


def build_steps(mode: str) -> List[str]:
    if mode == "daily":
        return DAILY_STEPS
    if mode == "odds-cycle":
        return ODDS_STEPS
    if mode == "evidence-cycle":
        return EVIDENCE_STEPS
    return DAILY_STEPS + ODDS_STEPS + EVIDENCE_STEPS


def print_steps(mode: str) -> None:
    print("Agent orchestrator dry-run Oracle")
    print(f"- Mode: {mode}")
    print("- Dry-run uniquement: aucun reseau, aucun Telegram, aucune mise.")
    for index, step in enumerate(build_steps(mode), start=1):
        print(f"{index}. {step}")
    print("- Decision maximale: analyse approfondie requise si evidence gate le permet.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Simulation locale de l'agent orchestrateur Oracle.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daily", action="store_true")
    group.add_argument("--odds-cycle", action="store_true")
    group.add_argument("--evidence-cycle", action="store_true")
    group.add_argument("--full", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    mode = "daily"
    if args.odds_cycle:
        mode = "odds-cycle"
    elif args.evidence_cycle:
        mode = "evidence-cycle"
    elif args.full:
        mode = "full"
    print_steps(mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
