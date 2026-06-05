import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from daily_operations_runner import run_daily_operations
from evidence_gate import build_evidence_gate
from near_close_window_planner import build_window_plan, write_html as write_window_html, write_json as write_window_json
from telegram_message_formatter import format_daily_report, write_text
from telegram_notifier import send_message_text


def _path(reports_dir: str, name: str) -> str:
    return str(Path(reports_dir) / name)


def build_daily_telegram_report(
    date: str = "",
    ledger: str = "reports/shadow_ledger.csv",
    reports_dir: str = "reports/telegram_daily",
) -> Dict[str, Any]:
    active_date = date or datetime.now().strftime("%Y-%m-%d")
    daily = run_daily_operations(
        active_date,
        reports_dir=reports_dir,
        ledger=ledger,
        allow_network=False,
        full_dry_run=True,
    )
    near = build_window_plan(ledger, hours_before=2)
    write_window_json(near, _path(reports_dir, "near_close_window_plan.json"))
    write_window_html(near, _path(reports_dir, "near_close_window_plan.html"))
    evidence = build_evidence_gate(
        shadow_report_path=_path(reports_dir, "shadow_clv_report.json"),
        near_close_window_path=_path(reports_dir, "near_close_window_plan.json"),
        subscription_evaluator_path=_path(reports_dir, "data_subscription_evaluator.json"),
    )
    text = format_daily_report(active_date, daily_ops=daily, near_close=near, evidence=evidence)
    return {
        "date": active_date,
        "daily_operations": daily,
        "near_close": near,
        "evidence": evidence,
        "message": text,
        "lab_only": True,
        "can_influence_picks": False,
    }


def run_daily_reporter(
    date: str = "",
    ledger: str = "reports/shadow_ledger.csv",
    reports_dir: str = "reports/telegram_daily",
    output: str = "reports/telegram_daily_preview.md",
    allow_send: bool = False,
    dry_run: bool = True,
) -> Dict[str, Any]:
    report = build_daily_telegram_report(date, ledger, reports_dir)
    preview = write_text(report["message"], output)
    notify = send_message_text(report["message"], allow_send=allow_send, dry_run=(dry_run or not allow_send))
    return {
        **report,
        "preview": str(preview),
        "dry_run": bool(dry_run or not allow_send),
        "notify": notify,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram daily reporter Oracle")
    print(f"- Date: {report.get('date')}")
    print(f"- Preview: {report.get('preview')}")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Due near-close: {(report.get('near_close') or {}).get('due_now_count')}")
    print(f"- Evidence: {(report.get('evidence') or {}).get('global_status')}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Rapport Telegram quotidien read-only.")
    parser.add_argument("--date", default="")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--reports-dir", default="reports/telegram_daily")
    parser.add_argument("--output", default="reports/telegram_daily_preview.md")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = run_daily_reporter(
            args.date,
            ledger=args.ledger,
            reports_dir=args.reports_dir,
            output=args.output,
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
