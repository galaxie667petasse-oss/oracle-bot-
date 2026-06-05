import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TELEGRAM_CHAT_ID"
PARSE_MODE_ENV = "TELEGRAM_PARSE_MODE"
DISABLE_SEND_ENV = "TELEGRAM_DISABLE_SEND"


def _truthy(value: Any, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "oui", "on", "y"}


def load_telegram_config(env: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    env = env or os.environ
    token = str(env.get(TOKEN_ENV) or "").strip()
    chat_id = str(env.get(CHAT_ENV) or "").strip()
    parse_mode = str(env.get(PARSE_MODE_ENV) or "Markdown").strip() or "Markdown"
    disable_send = _truthy(env.get(DISABLE_SEND_ENV), default=True)
    can_send = bool(token and chat_id and not disable_send)
    return {
        "token_present": bool(token),
        "chat_id_present": bool(chat_id),
        "chat_id_preview": _mask_chat_id(chat_id),
        "parse_mode": parse_mode,
        "disable_send": disable_send,
        "can_send": can_send,
        "lab_only": True,
        "can_influence_picks": False,
        "_token": token,
        "_chat_id": chat_id,
    }


def _mask_chat_id(chat_id: str) -> str:
    if not chat_id:
        return ""
    if len(chat_id) <= 4:
        return "***"
    return f"{chat_id[:2]}***{chat_id[-2:]}"


def safe_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if key not in {"_token", "_chat_id"}
    }


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    warnings = []
    errors = []
    if not config.get("token_present"):
        warnings.append("Token Telegram absent.")
    if not config.get("chat_id_present"):
        warnings.append("Chat ID Telegram absent.")
    if config.get("disable_send"):
        warnings.append("Envoi Telegram desactive par TELEGRAM_DISABLE_SEND.")
    return {
        **safe_config(config),
        "warnings": warnings,
        "errors": errors,
        "status": "ready_to_send" if config.get("can_send") else "read_only_or_not_configured",
    }


def write_example(path: str = "config/telegram.example.env") -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join([
            "TELEGRAM_BOT_TOKEN=",
            "TELEGRAM_CHAT_ID=",
            "TELEGRAM_DISABLE_SEND=true",
            "TELEGRAM_PARSE_MODE=Markdown",
            "",
        ]),
        encoding="utf-8",
    )
    return target


def print_safe(report: Dict[str, Any]) -> None:
    print("Configuration Telegram Oracle")
    print(f"- Token: {'present' if report.get('token_present') else 'absent'}")
    print(f"- Chat ID: {'present' if report.get('chat_id_present') else 'absent'}")
    print(f"- Parse mode: {report.get('parse_mode')}")
    print(f"- Envoi desactive: {report.get('disable_send')}")
    print(f"- Envoi possible: {report.get('can_send')}")
    print("- Mode: Telegram read-only, laboratoire local.")
    for warning in report.get("warnings") or []:
        print(f"- Warning: {warning}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Verifie la configuration Telegram sans afficher le token.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--show-safe", action="store_true")
    parser.add_argument("--write-example", action="store_true")
    parser.add_argument("--example-path", default="config/telegram.example.env")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.write_example:
            path = write_example(args.example_path)
            print(f"- Exemple Telegram ecrit: {path}")
        report = validate_config(load_telegram_config())
        if args.show_safe:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_safe(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
