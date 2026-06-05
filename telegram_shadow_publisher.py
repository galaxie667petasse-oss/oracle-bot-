import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import read_ledger
from telegram_message_formatter import format_ledger_preview, write_text
from telegram_notifier import send_message_text


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le tracking Telegram doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_tracking(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"published_shadow_ids": [], "events": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"published_shadow_ids": [], "events": []}
    except Exception:
        return {"published_shadow_ids": [], "events": []}


def _write_tracking(path: str, data: Dict[str, Any]) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def publish_shadow_observations(
    ledger: str = "reports/shadow_ledger.csv",
    output: str = "reports/telegram_shadow_preview.md",
    tracking: str = "reports/telegram_published_observations.json",
    only_new: bool = False,
    force: bool = False,
    allow_send: bool = False,
    dry_run: bool = True,
    limit: int = 20,
) -> Dict[str, Any]:
    rows = read_ledger(ledger)
    state = _read_tracking(tracking)
    sent_ids = set(state.get("published_shadow_ids") or [])
    selected: List[Dict[str, Any]] = []
    for row in rows:
        shadow_id = str(row.get("shadow_id") or "")
        if only_new and shadow_id in sent_ids and not force:
            continue
        selected.append(row)
    selected = selected[:limit]
    text = format_ledger_preview(ledger, limit=limit, rows=selected)
    preview = write_text(text, output)
    notify = send_message_text(text, allow_send=allow_send, dry_run=(dry_run or not allow_send))
    updated = False
    if allow_send and not notify.get("errors"):
        for row in selected:
            shadow_id = str(row.get("shadow_id") or "")
            if shadow_id and shadow_id not in sent_ids:
                state.setdefault("published_shadow_ids", []).append(shadow_id)
        state.setdefault("events", []).append({
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "count": len(selected),
            "lab_only": True,
            "can_influence_picks": False,
        })
        _write_tracking(tracking, state)
        updated = True
    return {
        "ledger": ledger,
        "rows_total": len(rows),
        "selected": len(selected),
        "only_new": only_new,
        "dry_run": bool(dry_run or not allow_send),
        "preview": str(preview),
        "tracking_updated": updated,
        "notify": notify,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram shadow publisher Oracle")
    print(f"- Ledger: {report.get('ledger')}")
    print(f"- Observations lues: {report.get('rows_total')}")
    print(f"- Observations selectionnees: {report.get('selected')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Preview: {report.get('preview')}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publie les observations shadow en Telegram read-only.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="reports/telegram_shadow_preview.md")
    parser.add_argument("--tracking", default="reports/telegram_published_observations.json")
    parser.add_argument("--only-new", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = publish_shadow_observations(
            args.ledger,
            output=args.output,
            tracking=args.tracking,
            only_new=args.only_new,
            force=args.force,
            allow_send=args.allow_send,
            dry_run=(args.dry_run or not args.allow_send),
            limit=args.limit,
        )
        print_report(report)
        return 0 if not (report.get("notify") or {}).get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
