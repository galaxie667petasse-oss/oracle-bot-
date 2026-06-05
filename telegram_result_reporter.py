import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from evidence_gate import read_json
from shadow_ledger import read_ledger
from telegram_message_formatter import format_results_preview, write_text
from telegram_notifier import send_message_text


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


def _result_rows(ledger: str) -> List[Dict[str, Any]]:
    return [
        row for row in read_ledger(ledger)
        if str(row.get("result") or "").strip().lower() in {"win", "loss", "push", "void"}
    ]


def publish_results(
    ledger: str = "reports/shadow_ledger.csv",
    evidence: str = "reports/evidence_gate.json",
    output: str = "reports/telegram_results_preview.md",
    tracking: str = "reports/telegram_published_results.json",
    only_updated: bool = False,
    force: bool = False,
    allow_send: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    rows = _result_rows(ledger)
    state = _read_tracking(tracking)
    sent_ids = set(state.get("published_result_ids") or [])
    selected = []
    for row in rows:
        shadow_id = str(row.get("shadow_id") or "")
        if only_updated and shadow_id in sent_ids and not force:
            continue
        selected.append(row)
    evidence_data = read_json(evidence)
    text = format_results_preview(ledger, evidence, only_rows=selected)
    preview = write_text(text, output)
    notify = send_message_text(text, allow_send=allow_send, dry_run=(dry_run or not allow_send))
    updated = False
    if allow_send and not notify.get("errors"):
        for row in selected:
            shadow_id = str(row.get("shadow_id") or "")
            if shadow_id and shadow_id not in sent_ids:
                state.setdefault("published_result_ids", []).append(shadow_id)
        state.setdefault("events", []).append({
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(selected),
            "evidence_status": evidence_data.get("global_status"),
            "lab_only": True,
            "can_influence_picks": False,
        })
        _write_tracking(tracking, state)
        updated = True
    return {
        "ledger": ledger,
        "results_total": len(rows),
        "selected": len(selected),
        "only_updated": only_updated,
        "dry_run": bool(dry_run or not allow_send),
        "preview": str(preview),
        "tracking_updated": updated,
        "evidence_status": evidence_data.get("global_status"),
        "notify": notify,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram result reporter Oracle")
    print(f"- Resultats lus: {report.get('results_total')}")
    print(f"- Resultats selectionnes: {report.get('selected')}")
    print(f"- Evidence: {report.get('evidence_status')}")
    print(f"- Preview: {report.get('preview')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publie les resultats shadow en Telegram read-only.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--evidence", default="reports/evidence_gate.json")
    parser.add_argument("--output", default="reports/telegram_results_preview.md")
    parser.add_argument("--tracking", default="reports/telegram_published_results.json")
    parser.add_argument("--only-updated", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = publish_results(
            args.ledger,
            evidence=args.evidence,
            output=args.output,
            tracking=args.tracking,
            only_updated=args.only_updated,
            force=args.force,
            allow_send=args.allow_send,
            dry_run=(args.dry_run or not args.allow_send),
        )
        print_report(report)
        return 0 if not (report.get("notify") or {}).get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
