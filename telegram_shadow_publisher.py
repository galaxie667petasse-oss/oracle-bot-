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
    since_date: str = "",
    max_messages: int = 0,
    mark_existing_as_published: bool = False,
    preview_only_new: bool = False,
) -> Dict[str, Any]:
    rows = read_ledger(ledger)
    state = _read_tracking(tracking)
    tracking_exists = Path(tracking).exists()
    sent_ids = set(state.get("published_shadow_ids") or [])
    selected: List[Dict[str, Any]] = []
    skipped_old = 0
    skipped_published = 0
    skipped_without_baseline = 0
    effective_only_new = bool(only_new or preview_only_new)
    max_selected = max_messages if max_messages and max_messages > 0 else limit
    baseline_missing = bool(effective_only_new and not tracking_exists and not since_date and not force)
    effective_dry_run = bool(dry_run if mark_existing_as_published else (dry_run or not allow_send or preview_only_new))
    for row in rows:
        shadow_id = str(row.get("shadow_id") or "")
        match_date = str(row.get("match_date") or "")[:10]
        if since_date and match_date and match_date < since_date:
            skipped_old += 1
            continue
        if effective_only_new and shadow_id in sent_ids and not force:
            skipped_published += 1
            continue
        if baseline_missing:
            skipped_without_baseline += 1
            continue
        selected.append(row)
    selected = selected[:max_selected]

    mark_rows = []
    if mark_existing_as_published:
        for row in rows:
            match_date = str(row.get("match_date") or "")[:10]
            if since_date and match_date and match_date < since_date:
                continue
            if str(row.get("shadow_id") or ""):
                mark_rows.append(row)
        selected = []

    preview_rows = mark_rows[:max_selected] if mark_existing_as_published else selected
    text = format_ledger_preview(ledger, limit=max_selected, rows=preview_rows)
    preview = None
    if not (mark_existing_as_published and not effective_dry_run):
        preview = write_text(text, output)
    notify = {"errors": [], "sent": 0, "dry_run": True, "message": "Tracking uniquement, aucun Telegram."}
    if not mark_existing_as_published and selected:
        notify = send_message_text(text, allow_send=allow_send and not preview_only_new, dry_run=effective_dry_run)
    elif not mark_existing_as_published:
        notify = {"errors": [], "sent": 0, "dry_run": True, "message": "Aucune observation selectionnee, aucun Telegram."}
    updated = False
    if mark_existing_as_published and not dry_run:
        marked = 0
        for row in mark_rows:
            shadow_id = str(row.get("shadow_id") or "")
            if shadow_id and shadow_id not in sent_ids:
                state.setdefault("published_shadow_ids", []).append(shadow_id)
                sent_ids.add(shadow_id)
                marked += 1
        state.setdefault("events", []).append({
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "event": "mark_existing_as_published",
            "count": marked,
            "dry_run": False,
            "lab_only": True,
            "can_influence_picks": False,
        })
        _write_tracking(tracking, state)
        updated = True
    elif allow_send and selected and not preview_only_new and not notify.get("errors"):
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
        "only_new": effective_only_new,
        "since_date": since_date,
        "max_messages": max_selected,
        "mark_existing_as_published": bool(mark_existing_as_published),
        "preview_only_new": bool(preview_only_new),
        "would_mark_existing": len(mark_rows),
        "skipped_old": skipped_old,
        "skipped_published": skipped_published,
        "skipped_without_tracking_baseline": skipped_without_baseline,
        "dry_run": effective_dry_run,
        "preview": str(preview) if preview else "",
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
    print(f"- Since date: {report.get('since_date') or 'aucune'}")
    print(f"- Max messages: {report.get('max_messages')}")
    if report.get("mark_existing_as_published"):
        print(f"- Existantes a marquer publiees: {report.get('would_mark_existing')}")
    if report.get("skipped_without_tracking_baseline"):
        print("- Warning: tracking absent et --since-date absent; anciennes observations ignorees pour eviter le spam.")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Preview: {report.get('preview')}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publie les observations shadow en Telegram read-only.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output", default="reports/telegram_shadow_preview.md")
    parser.add_argument("--tracking", default="reports/telegram_published_observations.json")
    parser.add_argument("--only-new", action="store_true")
    parser.add_argument("--since-date", default="")
    parser.add_argument("--max-messages", type=int, default=0)
    parser.add_argument("--mark-existing-as-published", action="store_true")
    parser.add_argument("--preview-only-new", action="store_true")
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
            dry_run=(args.dry_run or (not args.allow_send and not args.mark_existing_as_published)),
            limit=args.limit,
            since_date=args.since_date,
            max_messages=args.max_messages,
            mark_existing_as_published=args.mark_existing_as_published,
            preview_only_new=args.preview_only_new,
        )
        print_report(report)
        return 0 if not (report.get("notify") or {}).get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
