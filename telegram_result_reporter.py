import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from evidence_gate import read_json
from shadow_ledger import read_ledger
from telegram_message_formatter import assert_message_policy, write_text
from telegram_notifier import send_message_text


DEFAULT_TRACKING = "reports/telegram_published_results.json"


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le tracking resultats Telegram doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_tracking(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"published_result_ids": [], "events": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"published_result_ids": [], "events": []}
    except Exception:
        return {"published_result_ids": [], "events": []}


def _write_tracking(path: str, data: Dict[str, Any]) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _result_status(row: Dict[str, Any]) -> str:
    return str(row.get("result_status") or row.get("result") or "unknown").strip().lower()


def _is_settled(row: Dict[str, Any]) -> bool:
    result = _result_status(row)
    settlement = str(row.get("settlement_status") or row.get("status") or "").strip().lower()
    final = str(row.get("is_result_final") or "").strip().lower()
    return result in {"win", "loss", "push", "void"} and (
        settlement in {"settled", "overwritten"} or final == "true" or str(row.get("status") or "").lower() == "settled"
    )


def _result_rows(ledger: str) -> List[Dict[str, Any]]:
    return [row for row in read_ledger(ledger) if _is_settled(row)]


def _find_row(ledger: str, shadow_id: str) -> Optional[Dict[str, Any]]:
    for row in read_ledger(ledger):
        if str(row.get("shadow_id") or "") == shadow_id:
            return row
    return None


def _float(value: Any):
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _format_odds(value: Any) -> str:
    number = _float(value)
    return f"{number:.2f}" if number is not None else str(value or "n/a")


def _format_clv(row: Dict[str, Any]) -> str:
    pct = _float(row.get("clv_pct"))
    if pct is not None:
        return f"{pct:.2f}%"
    decimal = _float(row.get("clv"))
    if decimal is None:
        decimal = _float(row.get("clv_percent"))
    if decimal is None:
        return "n/a"
    return f"{decimal * 100.0:.2f}%"


def _profit_units(row: Dict[str, Any]):
    direct = _float(row.get("profit_units"))
    if direct is not None:
        return direct
    result = _result_status(row)
    odds = _float(row.get("taken_odds"))
    if odds is None:
        return None
    if result == "win":
        return round(odds - 1.0, 6)
    if result == "loss":
        return -1.0
    if result == "push":
        return 0.0
    return None


def _format_profit(row: Dict[str, Any]) -> str:
    profit = _profit_units(row)
    if profit is None:
        return "n/a"
    return f"{profit:+.2f}u"


def _evidence_label(evidence_data: Dict[str, Any]) -> str:
    status = str(evidence_data.get("global_status") or "").strip().lower()
    sample = int(_float(evidence_data.get("shadow_sample")) or 0)
    if status in {"ready_for_deep_review"} and sample >= 1000:
        return "revue humaine requise"
    return "sample insuffisant"


def format_result_message(row: Dict[str, Any], evidence_data: Dict[str, Any] = None, plain_text: bool = False) -> str:
    evidence_data = evidence_data or {}
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    hg = str(row.get("result_home_goals") or "").strip()
    ag = str(row.get("result_away_goals") or "").strip()
    if not hg or not ag:
        hg = str(row.get("home_goals") or "").strip()
        ag = str(row.get("away_goals") or "").strip()
    lines = [
        "📌 ORACLE SHADOW LAB — RÉSULTAT OBSERVATION",
        f"Match : {home} - {away}",
        f"Observation : {row.get('market_type')} {row.get('side')}",
        f"Cote prise : {_format_odds(row.get('taken_odds'))}",
        f"Near-close : {_format_odds(row.get('closing_odds'))}",
        f"CLV : {_format_clv(row)}",
        f"Score final : {home} {hg or 'n/a'} - {ag or 'n/a'} {away}",
        f"Résultat shadow : {_result_status(row)}",
        f"Profit shadow : {_format_profit(row)}",
        f"Statut preuve : {_evidence_label(evidence_data)}",
        "Aucune mise. Laboratoire local uniquement.",
    ]
    text = "\n".join(lines)
    assert_message_policy(text)
    return text


def _write_preview(text: str, output: str, plain_text: bool = False) -> Path:
    return write_text(text, output, plain_text=plain_text)


def publish_results(
    ledger: str = "reports/shadow_ledger.csv",
    shadow_id: str = "",
    evidence: str = "reports/evidence_gate.json",
    output: str = "reports/telegram_results_preview.md",
    tracking: str = DEFAULT_TRACKING,
    only_updated: bool = False,
    force: bool = False,
    allow_send: bool = False,
    dry_run: bool = True,
    plain_text: bool = False,
) -> Dict[str, Any]:
    evidence_data = read_json(evidence)
    state = _read_tracking(tracking)
    published_ids = set(state.get("published_result_ids") or [])

    if shadow_id:
        row = _find_row(ledger, shadow_id)
        rows = [row] if row else []
    else:
        rows = _result_rows(ledger)

    settled_rows = [row for row in rows if row and _is_settled(row)]
    skipped_pending = len(rows) - len(settled_rows)
    selected = []
    duplicate_skipped = 0
    for row in settled_rows:
        current_id = str(row.get("shadow_id") or "")
        if current_id in published_ids and not force:
            duplicate_skipped += 1
            continue
        selected.append(row)

    if shadow_id and not rows:
        text = f"Observation introuvable: {shadow_id}\n"
    elif not selected:
        if skipped_pending:
            text = "Aucun resultat settled a publier pour cette observation.\n"
        elif duplicate_skipped:
            text = "Resultat deja publie. Utiliser --force pour republier.\n"
        else:
            text = "Aucun resultat shadow a publier.\n"
    else:
        text = "\n\n".join(format_result_message(row, evidence_data, plain_text=plain_text) for row in selected) + "\n"
    assert_message_policy(text)
    preview = _write_preview(text, output, plain_text=plain_text)

    effective_dry_run = bool(dry_run or not allow_send)
    notify = send_message_text(
        text,
        allow_send=allow_send,
        dry_run=effective_dry_run,
        plain_text=plain_text,
        no_parse_mode=plain_text,
    )
    tracking_updated = False
    if allow_send and not effective_dry_run and not notify.get("errors") and selected:
        for row in selected:
            current_id = str(row.get("shadow_id") or "")
            if current_id and current_id not in published_ids:
                state.setdefault("published_result_ids", []).append(current_id)
        state.setdefault("events", []).append({
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "shadow_ids": [row.get("shadow_id") for row in selected],
            "count": len(selected),
            "evidence_status": evidence_data.get("global_status"),
            "lab_only": True,
            "can_influence_picks": False,
        })
        _write_tracking(tracking, state)
        tracking_updated = True

    return {
        "ledger": ledger,
        "shadow_id": shadow_id,
        "results_total": len(_result_rows(ledger)),
        "selected": len(selected),
        "skipped_pending": skipped_pending,
        "duplicate_skipped": duplicate_skipped,
        "only_updated": only_updated,
        "dry_run": effective_dry_run,
        "allow_send": bool(allow_send),
        "plain_text": bool(plain_text),
        "preview": str(preview),
        "tracking": tracking,
        "tracking_updated": tracking_updated,
        "evidence_status": evidence_data.get("global_status"),
        "notify": notify,
        "message": "Preview Telegram resultat generee.",
        "message_length": len(text),
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram result reporter Oracle")
    print(f"- Resultats settled lus: {report.get('results_total')}")
    print(f"- Resultats selectionnes: {report.get('selected')}")
    print(f"- Pending ignores: {report.get('skipped_pending')}")
    print(f"- Doublons ignores: {report.get('duplicate_skipped')}")
    print(f"- Evidence: {report.get('evidence_status')}")
    print(f"- Preview: {report.get('preview')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Allow-send: {report.get('allow_send')}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publie un resultat shadow en Telegram read-only.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--shadow-id", default="")
    parser.add_argument("--evidence", default="reports/evidence_gate.json")
    parser.add_argument("--output", default="reports/telegram_results_preview.md")
    parser.add_argument("--tracking", default=DEFAULT_TRACKING)
    parser.add_argument("--only-updated", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--plain-text", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = publish_results(
            ledger=args.ledger,
            shadow_id=args.shadow_id,
            evidence=args.evidence,
            output=args.output,
            tracking=args.tracking,
            only_updated=args.only_updated,
            force=args.force,
            allow_send=args.allow_send,
            dry_run=(args.dry_run or not args.allow_send),
            plain_text=args.plain_text,
        )
        print_report(report)
        return 0 if not (report.get("notify") or {}).get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
