import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from shadow_ledger import read_ledger
from telegram_message_formatter import write_text
from telegram_notifier import send_message_text


DEFAULT_OUTPUT = "reports/telegram_near_close_preview.md"
DEFAULT_TRACKING = "reports/telegram_published_near_close.json"


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le tracking Telegram near-close doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _read_tracking(path: str) -> Dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {"published_near_close_ids": [], "events": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"published_near_close_ids": [], "events": []}
    except Exception:
        return {"published_near_close_ids": [], "events": []}


def _write_tracking(path: str, data: Dict[str, Any]) -> Path:
    target = ensure_reports_path(path)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _find_row(ledger: str, shadow_id: str) -> Dict[str, str]:
    for row in read_ledger(ledger):
        if str(row.get("shadow_id") or "").strip() == shadow_id:
            return row
    raise ValueError(f"shadow_id introuvable: {shadow_id}")


def _fmt_odds(value: Any) -> str:
    try:
        return f"{float(str(value).replace(',', '.')):.2f}"
    except Exception:
        return str(value or "n/a")


def _fmt_pct(row: Dict[str, str]) -> str:
    raw_pct = str(row.get("clv_pct") or "").strip()
    if raw_pct:
        try:
            return f"{float(raw_pct.replace(',', '.')):.2f}%"
        except Exception:
            return f"{raw_pct}%"
    raw = str(row.get("clv") or "").strip()
    if raw:
        try:
            return f"{float(raw.replace(',', '.')) * 100.0:.2f}%"
        except Exception:
            pass
    return "n/a"


def _result_status(row: Dict[str, str]) -> str:
    result = str(row.get("result") or "unknown").strip().lower()
    if result in {"", "unknown"}:
        return "résultat en attente"
    return result


def build_message(row: Dict[str, str]) -> str:
    closing = str(row.get("closing_odds") or "").strip()
    if not closing:
        raise ValueError("Near-close absente dans le ledger pour cette observation.")
    quality = str(row.get("closing_quality") or "unavailable").strip() or "unavailable"
    return "\n".join([
        "⏱️ ORACLE SHADOW LAB — NEAR-CLOSE CAPTURÉE",
        f"Match : {row.get('home_team') or ''} - {row.get('away_team') or ''}",
        f"Observation : {row.get('market_type') or ''} {row.get('side') or ''}".strip(),
        f"Cote prise : {_fmt_odds(row.get('taken_odds'))}",
        f"Cote near-close : {_fmt_odds(closing)}",
        f"CLV : {_fmt_pct(row)}",
        f"Qualité : {quality}",
        f"Statut : {_result_status(row)}",
        "Aucune mise. Laboratoire local uniquement.",
    ])


def publish_near_close(
    ledger: str = "reports/shadow_ledger.csv",
    shadow_id: str = "",
    output: str = DEFAULT_OUTPUT,
    tracking: str = DEFAULT_TRACKING,
    force: bool = False,
    allow_send: bool = False,
    dry_run: bool = True,
    plain_text: bool = False,
) -> Dict[str, Any]:
    if not shadow_id:
        raise ValueError("--shadow-id est requis.")
    row = _find_row(ledger, shadow_id)
    try:
        text = build_message(row)
    except ValueError as exc:
        return {
            "ledger": ledger,
            "shadow_id": shadow_id,
            "selected": False,
            "duplicate": False,
            "force": bool(force),
            "dry_run": True,
            "allow_send": bool(allow_send),
            "preview": "",
            "tracking": tracking,
            "tracking_updated": False,
            "notify": {"errors": [], "sent": 0, "dry_run": True, "message": str(exc)},
            "status": "missing_closing",
            "lab_only": True,
            "can_influence_picks": False,
        }
    preview = write_text(text, output)
    state = _read_tracking(tracking)
    published = set(state.get("published_near_close_ids") or [])
    duplicate = shadow_id in published
    notify = {"errors": [], "sent": 0, "dry_run": True, "message": "Doublon deja publie, aucun Telegram."}
    tracking_updated = False
    selected = not duplicate or force
    effective_dry_run = bool(dry_run or not allow_send)
    if selected:
        notify = send_message_text(
            text,
            allow_send=allow_send,
            dry_run=effective_dry_run,
            plain_text=plain_text,
            no_parse_mode=plain_text,
        )
    if selected and allow_send and not notify.get("errors"):
        if shadow_id not in published:
            state.setdefault("published_near_close_ids", []).append(shadow_id)
        state.setdefault("events", []).append({
            "published_at": datetime.now().isoformat(timespec="seconds"),
            "shadow_id": shadow_id,
            "force": bool(force),
            "lab_only": True,
            "can_influence_picks": False,
        })
        _write_tracking(tracking, state)
        tracking_updated = True
    return {
        "ledger": ledger,
        "shadow_id": shadow_id,
        "selected": bool(selected),
        "duplicate": bool(duplicate),
        "force": bool(force),
        "dry_run": effective_dry_run,
        "allow_send": bool(allow_send),
        "preview": str(preview),
        "tracking": tracking,
        "tracking_updated": tracking_updated,
        "notify": notify,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram near-close reporter Oracle")
    print(f"- Ledger: {report.get('ledger')}")
    print(f"- Observation: {report.get('shadow_id')}")
    print(f"- Selectionnee: {report.get('selected')}")
    print(f"- Doublon: {report.get('duplicate')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Preview: {report.get('preview')}")
    print(f"- Tracking mis a jour: {report.get('tracking_updated')}")
    if report.get("status"):
        print(f"- Statut: {report.get('status')}")
    message = (report.get("notify") or {}).get("message")
    if message:
        print(f"- Message: {message}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Publie une near-close capturee en Telegram read-only.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--shadow-id", required=True)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--tracking", default=DEFAULT_TRACKING)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--plain-text", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = publish_near_close(
            ledger=args.ledger,
            shadow_id=args.shadow_id,
            output=args.output,
            tracking=args.tracking,
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
