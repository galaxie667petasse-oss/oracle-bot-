import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from near_close_window_planner import build_window_plan, write_json as write_window_json
from telegram_daily_reporter import run_daily_reporter
from telegram_message_formatter import format_near_close_preview, write_text
from telegram_notifier import send_message_text
from telegram_result_reporter import publish_results
from telegram_shadow_publisher import publish_shadow_observations


def _path(reports_dir: str, name: str) -> str:
    return str(Path(reports_dir) / name)


def run_pre_close(
    ledger: str,
    reports_dir: str,
    allow_send: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    plan = build_window_plan(ledger, hours_before=2, due_now_only=True)
    plan_path = write_window_json(plan, _path(reports_dir, "telegram_near_close_window_plan.json"))
    text = format_near_close_preview(str(plan_path))
    preview = write_text(text, _path(reports_dir, "telegram_near_close_preview.md"))
    notify = send_message_text(text, allow_send=allow_send, dry_run=(dry_run or not allow_send))
    return {
        "phase": "pre_close",
        "plan": plan,
        "preview": str(preview),
        "dry_run": bool(dry_run or not allow_send),
        "notify": notify,
        "lab_only": True,
        "can_influence_picks": False,
    }


def run_telegram_ops(
    date: str = "",
    ledger: str = "reports/shadow_ledger.csv",
    reports_dir: str = "reports/telegram_ops",
    morning: bool = False,
    pre_close: bool = False,
    post_match: bool = False,
    full_dry_run: bool = False,
    allow_send: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    active_date = date or datetime.now().strftime("%Y-%m-%d")
    Path(reports_dir).mkdir(parents=True, exist_ok=True)
    effective_dry = bool(dry_run or full_dry_run or not allow_send)
    phases: Dict[str, Any] = {}
    if morning or full_dry_run:
        phases["morning_daily"] = run_daily_reporter(
            active_date,
            ledger=ledger,
            reports_dir=_path(reports_dir, "daily"),
            output=_path(reports_dir, "telegram_daily_preview.md"),
            allow_send=allow_send and not full_dry_run,
            dry_run=effective_dry,
        )
        phases["morning_shadow"] = publish_shadow_observations(
            ledger,
            output=_path(reports_dir, "telegram_shadow_preview.md"),
            tracking=_path(reports_dir, "telegram_published_observations.json"),
            only_new=True,
            allow_send=allow_send and not full_dry_run,
            dry_run=effective_dry,
        )
    if pre_close or full_dry_run:
        phases["pre_close"] = run_pre_close(
            ledger,
            reports_dir,
            allow_send=allow_send and not full_dry_run,
            dry_run=effective_dry,
        )
    if post_match or full_dry_run:
        phases["post_match"] = publish_results(
            ledger,
            output=_path(reports_dir, "telegram_results_preview.md"),
            tracking=_path(reports_dir, "telegram_published_results.json"),
            only_updated=True,
            allow_send=allow_send and not full_dry_run,
            dry_run=effective_dry,
        )
    return {
        "date": active_date,
        "reports_dir": reports_dir,
        "dry_run": effective_dry,
        "allow_send": bool(allow_send and not full_dry_run),
        "phases": phases,
        "lab_only": True,
        "can_influence_picks": False,
        "message": "Telegram ops read-only: observations shadow uniquement.",
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram ops runner Oracle")
    print(f"- Date: {report.get('date')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Envoi autorise: {report.get('allow_send')}")
    print(f"- Phases: {', '.join((report.get('phases') or {}).keys()) or 'aucune'}")
    print("- Read-only: aucune mise, aucune activation.")


def has_notify_errors(report: Dict[str, Any]) -> bool:
    for phase in (report.get("phases") or {}).values():
        notify = phase.get("notify") if isinstance(phase, dict) else None
        if notify and notify.get("errors"):
            return True
        if isinstance(phase, dict):
            for nested in phase.values():
                if isinstance(nested, dict) and (nested.get("notify") or {}).get("errors"):
                    return True
    return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Runner Telegram read-only Oracle.")
    parser.add_argument("--date", default="")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--reports-dir", default="reports/telegram_ops")
    parser.add_argument("--full-dry-run", action="store_true")
    parser.add_argument("--morning", action="store_true")
    parser.add_argument("--pre-close", action="store_true")
    parser.add_argument("--post-match", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        selected = any([args.morning, args.pre_close, args.post_match, args.full_dry_run])
        report = run_telegram_ops(
            args.date,
            ledger=args.ledger,
            reports_dir=args.reports_dir,
            morning=args.morning,
            pre_close=args.pre_close,
            post_match=args.post_match,
            full_dry_run=args.full_dry_run or not selected,
            allow_send=args.allow_send,
            dry_run=(args.dry_run or not args.allow_send),
        )
        print_report(report)
        return 1 if has_notify_errors(report) else 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
