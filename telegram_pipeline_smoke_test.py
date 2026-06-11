import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict

from telegram_config import load_telegram_config, validate_config
from telegram_daily_reporter import run_daily_reporter
from telegram_notifier import send_message_text


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le smoke test Telegram doit ecrire hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def default_json_path(date: str) -> str:
    return f"reports/telegram_pipeline_smoke_test_{date}.json"


def default_html_path(date: str) -> str:
    return f"reports/telegram_pipeline_smoke_test_{date}.html"


def build_telegram_pipeline_smoke_test(
    date: str,
    allow_send: bool = False,
    plain_text_test: bool = False,
    output_json: str = "",
    output_html: str = "",
    reports_dir: str = "reports/telegram_pipeline_smoke",
    ledger: str = "reports/shadow_ledger.csv",
) -> Dict[str, Any]:
    if not date:
        raise ValueError("--date requis")
    config_report = validate_config(load_telegram_config())
    daily = run_daily_reporter(
        date,
        ledger=ledger,
        reports_dir=reports_dir,
        output=str(Path(reports_dir) / "telegram_daily_preview.md"),
        allow_send=False,
        dry_run=True,
    )
    notifier_dry_run = send_message_text(
        daily.get("message") or "",
        allow_send=False,
        dry_run=True,
    )
    test_send = {
        "skipped": True,
        "reason": "envoi test non demande",
        "sent": 0,
        "errors": [],
    }
    if allow_send and plain_text_test:
        test_send = send_message_text(
            "ORACLE TEST READ ONLY",
            allow_send=True,
            dry_run=False,
            plain_text=True,
            no_parse_mode=True,
        )
    report = {
        "date": date,
        "allow_send": bool(allow_send),
        "plain_text_test": bool(plain_text_test),
        "config": config_report,
        "daily_preview": daily.get("preview"),
        "notifier_dry_run": notifier_dry_run,
        "test_send": test_send,
        "observations_published": False,
        "lab_only": True,
        "can_influence_picks": False,
    }
    write_json(report, output_json or default_json_path(date))
    write_html(report, output_html or default_html_path(date))
    return report


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Telegram Pipeline Smoke Test</h1><pre>"
        + html.escape(json.dumps(report, ensure_ascii=False, indent=2))
        + "</pre><p>Read-only, aucune observation publiee par ce smoke test.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram pipeline smoke test Oracle")
    print(f"- Date: {report.get('date')}")
    print(f"- Token: {'present' if (report.get('config') or {}).get('token_present') else 'absent'}")
    print(f"- Envoi possible: {(report.get('config') or {}).get('status') == 'ready_to_send'}")
    print(f"- Daily preview: {report.get('daily_preview')}")
    print(f"- Notifier dry-run: {(report.get('notifier_dry_run') or {}).get('dry_run')}")
    print(f"- Plain text test: {report.get('plain_text_test')}")
    print(f"- Test envoye: {(report.get('test_send') or {}).get('sent', 0)}")
    print("- Aucune observation publiee, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Smoke test pipeline Telegram read-only.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--plain-text-test", action="store_true")
    parser.add_argument("--reports-dir", default="reports/telegram_pipeline_smoke")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--output-json", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_telegram_pipeline_smoke_test(
            args.date,
            allow_send=args.allow_send,
            plain_text_test=args.plain_text_test,
            output_json=args.output_json,
            output_html=args.html,
            reports_dir=args.reports_dir,
            ledger=args.ledger,
        )
        print_report(report)
        return 0 if not (report.get("test_send") or {}).get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
