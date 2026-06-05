import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from telegram_config import load_telegram_config, validate_config
from telegram_message_formatter import assert_message_policy


TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les logs Telegram doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    current = []
    current_len = 0
    for line in text.splitlines():
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if line_len > limit:
            for idx in range(0, len(line), limit):
                chunks.append(line[idx:idx + limit])
            continue
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks or [""]


def _http_post(url: str, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8", errors="replace")
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {"ok": False, "raw": body}
    except Exception:
        return {"ok": False, "raw": body}


def _error_reason(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 401:
            return "unauthorized"
        if exc.code == 404:
            return "chat not found"
        if exc.code == 429:
            return "rate limit"
        return f"http {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return "reseau indisponible"
    return str(exc)


def append_log(entry: Dict[str, Any], log_path: str = "reports/telegram_send_log.jsonl") -> Path:
    target = ensure_reports_path(log_path)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return target


def send_message_text(
    text: str,
    allow_send: bool = False,
    dry_run: bool = True,
    log_path: str = "reports/telegram_send_log.jsonl",
) -> Dict[str, Any]:
    assert_message_policy(text)
    chunks = split_message(text)
    config = load_telegram_config()
    validated = validate_config(config)
    report = {
        "dry_run": bool(dry_run or not allow_send),
        "allow_send": bool(allow_send),
        "chunks": len(chunks),
        "sent": 0,
        "errors": [],
        "config": validated,
        "lab_only": True,
        "can_influence_picks": False,
    }
    if not allow_send or dry_run:
        report["message"] = "Dry-run Telegram: aucun message reel envoye."
        return report
    if not config.get("can_send"):
        report["errors"].append("Configuration Telegram incomplete ou envoi desactive.")
        report["message"] = "Envoi refuse."
        return report
    url = f"{TELEGRAM_API}/bot{config.get('_token')}/sendMessage"
    for chunk in chunks:
        payload = {
            "chat_id": config.get("_chat_id"),
            "text": chunk,
            "parse_mode": config.get("parse_mode") or "Markdown",
            "disable_web_page_preview": "true",
        }
        try:
            result = _http_post(url, payload)
            if result.get("ok"):
                report["sent"] += 1
            else:
                report["errors"].append(str(result.get("description") or result))
        except Exception as exc:
            report["errors"].append(_error_reason(exc))
    report["message"] = "Envoi Telegram termine." if report["sent"] else "Aucun message envoye."
    append_log({
        "sent_at": datetime.now().isoformat(timespec="seconds"),
        "chunks": len(chunks),
        "sent": report["sent"],
        "errors": report["errors"],
        "lab_only": True,
        "can_influence_picks": False,
    }, log_path)
    return report


def send_message_file(message_file: str, allow_send: bool = False, dry_run: bool = True, log_path: str = "reports/telegram_send_log.jsonl") -> Dict[str, Any]:
    path = Path(message_file)
    if not path.exists():
        raise FileNotFoundError(f"Message Telegram introuvable: {message_file}")
    text = path.read_text(encoding="utf-8")
    return send_message_text(text, allow_send=allow_send, dry_run=dry_run, log_path=log_path)


def print_report(report: Dict[str, Any]) -> None:
    print("Telegram notifier Oracle")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Chunks: {report.get('chunks')}")
    print(f"- Envoyes: {report.get('sent')}")
    print(f"- Erreurs: {len(report.get('errors') or [])}")
    for error in report.get("errors") or []:
        print(f"  - {error}")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Notifie Telegram seulement avec --allow-send.")
    parser.add_argument("--message-file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--log", default="reports/telegram_send_log.jsonl")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = send_message_file(args.message_file, allow_send=args.allow_send, dry_run=(args.dry_run or not args.allow_send), log_path=args.log)
        print_report(report)
        return 0 if not report.get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
