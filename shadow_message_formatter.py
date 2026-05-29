import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import read_ledger


FORBIDDEN_PARTS = ("pari", "conseill")


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("La preview message shadow ne doit pas etre ecrite dans data/.")
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


def _safe(text: Any) -> str:
    return str(text or "").strip()


def format_ledger_messages(ledger: str, limit: int = 50) -> str:
    rows = read_ledger(ledger)[:limit]
    lines: List[str] = [
        "Oracle Shadow Mode",
        "Statut: observation seulement",
        "Rappel: aucune mise conseillee, aucun envoi Telegram.",
        "",
    ]
    if not rows:
        lines.append("Aucune observation shadow enregistree.")
    for row in rows:
        lines.extend([
            f"Observation: {_safe(row.get('shadow_id'))}",
            f"Match: {_safe(row.get('match_date'))} | {_safe(row.get('league'))} | {_safe(row.get('home_team'))} - {_safe(row.get('away_team'))}",
            f"Marche: {_safe(row.get('market_type'))} | side: {_safe(row.get('side'))}",
            f"Cote prise: {_safe(row.get('taken_odds'))} | bookmaker: {_safe(row.get('bookmaker'))}",
            f"Raison: {_safe(row.get('reason'))}",
            f"Statut: {_safe(row.get('status'))} | resultat: {_safe(row.get('result'))}",
            "Rappel: observation shadow, preuve insuffisante tant que CLV/sample manquent.",
            "",
        ])
    text = "\n".join(lines)
    lowered = text.lower()
    if all(part in lowered for part in FORBIDDEN_PARTS):
        raise ValueError("Terme interdit detecte dans la preview message.")
    return text


def format_summary_message(shadow_report_path: str) -> str:
    report = read_json(shadow_report_path)
    lines = [
        "Oracle Shadow Mode",
        "Resume evidence shadow",
        "Statut: observation seulement",
        f"Signaux: {report.get('signals_total', 0)}",
        f"Pending closing: {report.get('pending_closing', 0)}",
        f"Pending resultats: {report.get('pending_results', 0)}",
        f"CLV coverage: {report.get('clv_coverage', 0)}%",
        f"CLV moyenne: {report.get('clv_mean')}",
        f"Verdict: {report.get('verdict', 'not_validated')}",
        "Blockers:",
    ]
    for warning in report.get("warnings") or ["preuve insuffisante"]:
        lines.append(f"- {warning}")
    lines.append("Rappel: aucune mise conseillee, aucun envoi Telegram.")
    text = "\n".join(lines)
    lowered = text.lower()
    if all(part in lowered for part in FORBIDDEN_PARTS):
        raise ValueError("Terme interdit detecte dans la preview message.")
    return text


def write_text(text: str, path: str) -> Path:
    target = ensure_reports_path(path)
    target.write_text(text, encoding="utf-8")
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Formate des messages shadow en texte, sans envoi Telegram.")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--shadow-report", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=50)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.shadow_report:
            text = format_summary_message(args.shadow_report)
        elif args.ledger:
            text = format_ledger_messages(args.ledger, limit=args.limit)
        else:
            raise ValueError("--ledger ou --shadow-report est requis")
        path = write_text(text, args.output)
        print("Shadow Message Formatter Oracle Bot")
        print(f"- Preview ecrite: {path}")
        print("- Aucun envoi Telegram, aucune mise conseillee.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
