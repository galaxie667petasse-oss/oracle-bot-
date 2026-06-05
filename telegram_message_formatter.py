import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from shadow_ledger import read_ledger


FORBIDDEN_TERMS = [
    "bankroll",
    "stake",
    "staking",
    "kelly",
    "pari sur",
    "pari sûr",
    "pari sur",
    "all-in",
    "conseil de pari",
    "pick automatique",
    "rentabilite garantie",
    "rentabilité garantie",
]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("La preview Telegram ne doit pas etre ecrite dans data/.")
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


def _safe(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return text.replace("\r", " ").replace("\n", " ")


def assert_message_policy(text: str) -> None:
    lower = text.lower()
    problems = [term for term in FORBIDDEN_TERMS if term in lower]
    if " mise" in lower and "aucune mise" not in lower:
        problems.append("mise hors contexte aucune mise")
    if problems:
        raise ValueError("Terme interdit detecte dans le message Telegram: " + ", ".join(sorted(set(problems))))


def format_shadow_observation(row: Dict[str, Any]) -> str:
    clv = "calculee" if _safe(row.get("clv_available")).lower() == "true" else "en attente"
    lines = [
        "OBSERVATION SHADOW - NON VALIDEE",
        f"ID: {_safe(row.get('shadow_id'))}",
        f"Match: {_safe(row.get('home_team'))} - {_safe(row.get('away_team'))}",
        f"Date: {_safe(row.get('match_date'))}",
        f"Ligue: {_safe(row.get('league'))}",
        f"Marche: {_safe(row.get('market_type'))} / {_safe(row.get('side'))}",
        f"Cote prise: {_safe(row.get('taken_odds'))}",
        f"Source: {_safe(row.get('bookmaker')) or 'non renseignee'}",
        f"Statut: CLV {clv}",
        "Preuve insuffisante",
        "Rappel: aucune mise, observation laboratoire uniquement.",
    ]
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def format_ledger_preview(ledger: str, limit: int = 20, rows: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    selected = list(rows) if rows is not None else read_ledger(ledger)[:limit]
    lines = ["ORACLE SHADOW LAB - OBSERVATIONS", "Statut: laboratoire local", ""]
    if not selected:
        lines.append("Aucune observation shadow a publier.")
    for row in selected[:limit]:
        lines.append(format_shadow_observation(row))
        lines.append("")
    text = "\n".join(lines).strip() + "\n"
    assert_message_policy(text)
    return text


def format_near_close_item(item: Dict[str, Any]) -> str:
    lines = [
        "NEAR-CLOSE A CAPTURER",
        f"Observation: {_safe(item.get('shadow_id'))}",
        f"Match: {_safe(item.get('home_team'))} - {_safe(item.get('away_team'))}",
        f"Kickoff: {_safe(item.get('kickoff_time')) or _safe(item.get('match_date'))}",
        f"Marche: {_safe(item.get('market_type'))} / {_safe(item.get('side'))}",
        f"Statut fenetre: {_safe(item.get('near_close_status'))}",
        "Action: capturer la cote proche du debut.",
        "Rappel: aucune cote n'est inventee.",
    ]
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def format_near_close_preview(path: str, limit: int = 20) -> str:
    report = read_json(path)
    observations = report.get("observations") or []
    lines = [
        "ORACLE SHADOW LAB - NEAR-CLOSE",
        f"Due now: {report.get('due_now_count', 0)}",
        f"Overdue: {report.get('overdue_count', 0)}",
        "",
    ]
    if not observations:
        lines.append("Aucune near-close a capturer.")
    for item in observations[:limit]:
        lines.append(format_near_close_item(item))
        lines.append("")
    text = "\n".join(lines).strip() + "\n"
    assert_message_policy(text)
    return text


def format_result_observation(row: Dict[str, Any], evidence_status: str = "", sample: int = 0) -> str:
    result = _safe(row.get("result")) or "unknown"
    clv = _safe(row.get("clv_percent")) or "non calculable"
    lines = [
        "RESULTAT OBSERVATION",
        f"ID: {_safe(row.get('shadow_id'))}",
        f"Match: {_safe(row.get('home_team'))} - {_safe(row.get('away_team'))}",
        f"Observation: {result}",
        f"CLV: {clv}",
        f"ROI shadow: {_safe(row.get('profit')) or 'non calcule'}",
        f"Verdict evidence gate: {evidence_status or 'non valide'}",
    ]
    if sample < 30:
        lines.append("Avertissement: sample insuffisant.")
    lines.append("Rappel: aucune mise, lecture laboratoire uniquement.")
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def format_results_preview(ledger: str, evidence_path: str = "", only_rows: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    rows = list(only_rows) if only_rows is not None else [
        row for row in read_ledger(ledger)
        if _safe(row.get("result")).lower() in {"win", "loss", "push", "void"}
    ]
    evidence = read_json(evidence_path)
    sample = int(evidence.get("shadow_sample") or len(rows) or 0)
    lines = ["ORACLE SHADOW LAB - RESULTATS", ""]
    if not rows:
        lines.append("Aucun resultat shadow a publier.")
    for row in rows:
        lines.append(format_result_observation(row, str(evidence.get("global_status") or "non valide"), sample))
        lines.append("")
    text = "\n".join(lines).strip() + "\n"
    assert_message_policy(text)
    return text


def format_proof_preview(proof_path: str) -> str:
    proof = read_json(proof_path)
    sections = proof.get("sections") or {}
    shadow = sections.get("shadow") or {}
    evidence = sections.get("evidence_gate") or {}
    lines = [
        "ORACLE SHADOW LAB - RAPPORT DE PREUVE",
        f"Statut global: {_safe(proof.get('global_status')) or 'non demarre'}",
        f"Observations actives: {_safe(shadow.get('sample')) or 0}",
        f"CLV coverage: {_safe(shadow.get('clv_coverage')) or 0}%",
        f"Evidence gate: {_safe(evidence.get('global_status')) or 'non disponible'}",
        "Action humaine: continuer la collecte, renseigner closing et resultats.",
        "Rappel: aucune mise, preuve insuffisante.",
    ]
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def format_daily_report(date: str, daily_ops: Dict[str, Any] = None, near_close: Dict[str, Any] = None, proof: Dict[str, Any] = None, evidence: Dict[str, Any] = None) -> str:
    daily_ops = daily_ops or {}
    near_close = near_close or {}
    proof = proof or {}
    evidence = evidence or {}
    phases = daily_ops.get("phases") or {}
    shadow_report = ((phases.get("post_match") or {}).get("shadow_report") or {})
    active = shadow_report.get("signals_total") or proof.get("shadow_sample") or 0
    pending_results = shadow_report.get("pending_results") or evidence.get("pending_results_count") or 0
    lines = [
        f"ORACLE SHADOW LAB - RAPPORT DU JOUR {date}",
        "Statut: laboratoire local",
        f"Observations actives: {active}",
        f"Due near-close: {near_close.get('due_now_count', 0)}",
        f"Resultats a verifier: {pending_results}",
        f"Evidence: {evidence.get('global_status') or proof.get('global_status') or 'insufficient_evidence'}",
        "Action humaine: verifier les observations, capturer les near-close, renseigner les resultats.",
        "Aucune mise.",
    ]
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def write_text(text: str, output: str) -> Path:
    assert_message_policy(text)
    target = ensure_reports_path(output)
    target.write_text(text, encoding="utf-8")
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Formate les previews Telegram read-only Oracle.")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--proof", default="")
    parser.add_argument("--near-close-plan", default="")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--results", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.proof:
            text = format_proof_preview(args.proof)
        elif args.near_close_plan:
            text = format_near_close_preview(args.near_close_plan, limit=args.limit)
        elif args.results:
            text = format_results_preview(args.ledger, args.evidence)
        elif args.ledger:
            text = format_ledger_preview(args.ledger, limit=args.limit)
        else:
            raise ValueError("--ledger, --proof ou --near-close-plan requis")
        path = write_text(text, args.output)
        print("Telegram formatter Oracle")
        print(f"- Preview ecrite: {path}")
        print("- Read-only: aucune mise, aucune emission reelle.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
