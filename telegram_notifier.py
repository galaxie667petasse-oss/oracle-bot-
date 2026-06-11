import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram_config import load_telegram_config, validate_config
from telegram_message_formatter import assert_message_policy, to_plain_text


TELEGRAM_API = "https://api.telegram.org"
MAX_MESSAGE_LENGTH = 3900
DEFAULT_LOG_PATH = "reports/telegram_send_log.jsonl"


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


def _parse_telegram_body(body: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return parsed
        return {"ok": False, "raw": body}
    except Exception:
        return {"ok": False, "raw": body}


def _http_post(url: str, payload: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            result = _parse_telegram_body(body)
            result.setdefault("_http_status", getattr(response, "status", 200))
            result.setdefault("_http_reason", getattr(response, "reason", "OK"))
            return result
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        result = _parse_telegram_body(body)
        result.setdefault("ok", False)
        result.setdefault("_http_status", exc.code)
        result.setdefault("_http_reason", exc.reason or "HTTP Error")
        return result


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


def _redact_secret(value: Any, token: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_secret(item, token)
            for key, item in value.items()
            if key not in {"_token", "token", "url"}
        }
    if isinstance(value, list):
        return [_redact_secret(item, token) for item in value]
    if isinstance(value, str) and token:
        return value.replace(token, "[TOKEN_REDACTED]")
    return value


def append_log(entry: Dict[str, Any], log_path: str = DEFAULT_LOG_PATH, token: str = "") -> Path:
    target = ensure_reports_path(log_path)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_redact_secret(entry, token), ensure_ascii=False) + "\n")
    return target


def read_message_file_text(message_file: str) -> str:
    path = Path(message_file)
    if not path.exists():
        raise FileNotFoundError(f"Message Telegram introuvable: {message_file}")
    return path.read_text(encoding="utf-8-sig").lstrip("\ufeff")


def _effective_parse_mode(config: Dict[str, Any], plain_text: bool = False, no_parse_mode: bool = False) -> str:
    if plain_text or no_parse_mode:
        return ""
    if "TELEGRAM_PARSE_MODE" in os.environ:
        return str(os.environ.get("TELEGRAM_PARSE_MODE") or "").strip()
    return str(config.get("parse_mode") or "").strip()


def _build_payload(chat_id: str, text: str, parse_mode: str = "") -> Dict[str, Any]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    return payload


def _retry_after(result: Dict[str, Any]) -> Optional[Any]:
    parameters = result.get("parameters") if isinstance(result.get("parameters"), dict) else {}
    return parameters.get("retry_after") or result.get("retry_after")


def _description(result: Dict[str, Any], fallback: str = "") -> str:
    return str(result.get("description") or result.get("raw") or fallback or "").strip()


def _http_status_text(result: Dict[str, Any]) -> str:
    status = result.get("_http_status") or result.get("http_status") or result.get("error_code")
    reason = result.get("_http_reason") or result.get("http_reason") or ""
    if not reason:
        description = _description(result)
        if ":" in description:
            reason = description.split(":", 1)[0].strip()
    if status and reason:
        return f"{status} {reason}"
    if status:
        return str(status)
    return "erreur inconnue"


def _is_markdown_parse_error(result: Dict[str, Any], parse_mode: str) -> bool:
    if not str(parse_mode or "").lower().startswith("markdown"):
        return False
    description = _description(result).lower()
    return "can't parse entities" in description or ("can't parse" in description and "entities" in description)


def _error_detail(
    result: Dict[str, Any],
    chunk_index: int,
    parse_mode: str,
    fallback_used: bool,
) -> Dict[str, Any]:
    return {
        "error_code": result.get("error_code") or result.get("_http_status"),
        "description": _description(result, fallback="Erreur Telegram sans description."),
        "retry_after": _retry_after(result),
        "chunk_index": chunk_index,
        "parse_mode": parse_mode or "",
        "fallback_used": bool(fallback_used),
        "http_status": result.get("_http_status") or result.get("error_code"),
        "http_reason": result.get("_http_reason") or "",
        "telegram_response": result,
    }


def _exception_detail(
    exc: Exception,
    chunk_index: int,
    parse_mode: str,
    fallback_used: bool,
) -> Dict[str, Any]:
    return {
        "error_code": getattr(exc, "code", None),
        "description": _error_reason(exc),
        "retry_after": None,
        "chunk_index": chunk_index,
        "parse_mode": parse_mode or "",
        "fallback_used": bool(fallback_used),
        "http_status": getattr(exc, "code", None),
        "http_reason": getattr(exc, "reason", ""),
        "telegram_response": None,
    }


def send_message_text(
    text: str,
    allow_send: bool = False,
    dry_run: bool = True,
    log_path: str = DEFAULT_LOG_PATH,
    plain_text: bool = False,
    no_parse_mode: bool = False,
) -> Dict[str, Any]:
    if plain_text:
        text = to_plain_text(text)
    assert_message_policy(text)
    chunks = split_message(text)
    config = load_telegram_config()
    validated = validate_config(config)
    parse_mode = _effective_parse_mode(config, plain_text=plain_text, no_parse_mode=no_parse_mode)
    report = {
        "dry_run": bool(dry_run or not allow_send),
        "allow_send": bool(allow_send),
        "chunks": len(chunks),
        "sent": 0,
        "errors": [],
        "error_details": [],
        "fallbacks": [],
        "fallback_used": False,
        "plain_text": bool(plain_text),
        "parse_mode": parse_mode,
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
    for idx, chunk in enumerate(chunks, start=1):
        payload = _build_payload(str(config.get("_chat_id") or ""), chunk, parse_mode=parse_mode)
        try:
            result = _http_post(url, payload)
            if result.get("ok"):
                report["sent"] += 1
            else:
                if _is_markdown_parse_error(result, parse_mode):
                    fallback_payload = _build_payload(str(config.get("_chat_id") or ""), chunk, parse_mode="")
                    fallback_result = _http_post(url, fallback_payload)
                    report["fallback_used"] = True
                    report["fallbacks"].append({
                        "chunk_index": idx,
                        "parse_mode": parse_mode,
                        "fallback_parse_mode": "",
                        "original_error": _error_detail(result, idx, parse_mode, fallback_used=False),
                        "fallback_ok": bool(fallback_result.get("ok")),
                    })
                    if fallback_result.get("ok"):
                        report["sent"] += 1
                        continue
                    detail = _error_detail(fallback_result, idx, "", fallback_used=True)
                else:
                    detail = _error_detail(result, idx, parse_mode, fallback_used=False)
                report["error_details"].append(detail)
                report["errors"].append(_description(detail, fallback="Erreur Telegram."))
        except Exception as exc:
            detail = _exception_detail(exc, idx, parse_mode, fallback_used=False)
            report["error_details"].append(detail)
            report["errors"].append(detail["description"])
    report["message"] = "Envoi Telegram termine." if report["sent"] else "Aucun message envoye."
    append_log({
        "sent_at": datetime.now().isoformat(timespec="seconds"),
        "chunks": len(chunks),
        "sent": report["sent"],
        "errors": report["errors"],
        "error_details": report["error_details"],
        "fallbacks": report["fallbacks"],
        "fallback_used": report["fallback_used"],
        "plain_text": bool(plain_text),
        "parse_mode": parse_mode,
        "lab_only": True,
        "can_influence_picks": False,
    }, log_path, token=str(config.get("_token") or ""))
    return report


def send_message_file(
    message_file: str,
    allow_send: bool = False,
    dry_run: bool = True,
    log_path: str = DEFAULT_LOG_PATH,
    plain_text: bool = False,
    no_parse_mode: bool = False,
) -> Dict[str, Any]:
    text = read_message_file_text(message_file)
    return send_message_text(
        text,
        allow_send=allow_send,
        dry_run=dry_run,
        log_path=log_path,
        plain_text=plain_text,
        no_parse_mode=no_parse_mode,
    )


def print_report(report: Dict[str, Any], show_error_detail: bool = False) -> None:
    print("Telegram notifier Oracle")
    print(f"- Dry-run: {report.get('dry_run')}")
    print(f"- Chunks: {report.get('chunks')}")
    print(f"- Envoyes: {report.get('sent')}")
    print(f"- Erreurs: {len(report.get('errors') or [])}")
    details = report.get("error_details") or []
    if details:
        for detail in details:
            print(f"Erreur Telegram: {_http_status_text(detail)}")
            print(f"Description: {detail.get('description') or 'non fournie'}")
            if detail.get("retry_after"):
                print(f"Retry-after: {detail.get('retry_after')}")
            if show_error_detail:
                print(f"Chunk: {detail.get('chunk_index')}")
                print(f"Parse mode: {detail.get('parse_mode') or 'aucun'}")
                print(f"Fallback plain text: {detail.get('fallback_used')}")
            print("Conseil: essaye --plain-text si Markdown echoue.")
    else:
        for error in report.get("errors") or []:
            print(f"  - {error}")
    if report.get("fallback_used"):
        print("- Fallback plain text utilise: True")
    print("- Read-only: aucune mise, aucune activation.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Notifie Telegram seulement avec --allow-send.")
    parser.add_argument("--message-file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-send", action="store_true")
    parser.add_argument("--plain-text", action="store_true")
    parser.add_argument("--no-parse-mode", action="store_true")
    parser.add_argument("--show-error-detail", action="store_true")
    parser.add_argument("--log", default=DEFAULT_LOG_PATH)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = send_message_file(
            args.message_file,
            allow_send=args.allow_send,
            dry_run=(args.dry_run or not args.allow_send),
            log_path=args.log,
            plain_text=args.plain_text,
            no_parse_mode=(args.no_parse_mode or args.plain_text),
        )
        print_report(report, show_error_detail=args.show_error_detail)
        return 0 if not report.get("errors") else 1
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
