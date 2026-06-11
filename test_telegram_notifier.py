import os
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

import telegram_notifier


def _prepare_env(token="123:secret"):
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["TELEGRAM_CHAT_ID"] = "456"
    os.environ["TELEGRAM_DISABLE_SEND"] = "false"
    os.environ.pop("TELEGRAM_PARSE_MODE", None)


def _with_http_mock(fake_post, callback):
    original = telegram_notifier._http_post
    telegram_notifier._http_post = fake_post
    try:
        return callback()
    finally:
        telegram_notifier._http_post = original


def main():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            message = Path(tmp) / "message.md"
            message.write_text("OBSERVATION SHADOW\nRappel: aucune mise.", encoding="utf-8")
            dry_calls = []

            def dry_fake_post(url, payload, timeout=20):
                dry_calls.append((url, payload))
                return {"ok": True}

            dry = _with_http_mock(
                dry_fake_post,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=True,
                    allow_send=False,
                    log_path=str(root / "log.jsonl"),
                ),
            )
            assert dry["dry_run"] is True
            assert dry["sent"] == 0
            assert dry_calls == []
            assert not (root / "log.jsonl").exists()

            _prepare_env()
            calls = []

            def fake_post(url, payload, timeout=20):
                calls.append((url, payload))
                return {"ok": True, "result": {"message_id": 1}}

            sent = _with_http_mock(
                fake_post,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(root / "log.jsonl"),
                ),
            )
            assert sent["sent"] == 1
            assert calls
            assert calls[0][1]["parse_mode"] == "Markdown"
            assert "secret" not in str(sent)
            assert "secret" not in (root / "log.jsonl").read_text(encoding="utf-8")

            error_log = root / "error.jsonl"
            error_calls = []

            def fake_400(url, payload, timeout=20):
                error_calls.append((url, payload))
                return {
                    "ok": False,
                    "error_code": 400,
                    "description": "Bad Request: invalid chat_id",
                    "_http_status": 400,
                    "_http_reason": "Bad Request",
                }

            failed = _with_http_mock(
                fake_400,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(error_log),
                ),
            )
            assert failed["sent"] == 0
            assert failed["error_details"][0]["error_code"] == 400
            assert failed["error_details"][0]["description"] == "Bad Request: invalid chat_id"
            log_text = error_log.read_text(encoding="utf-8")
            assert "invalid chat_id" in log_text
            assert "secret" not in log_text

            out = StringIO()
            with redirect_stdout(out):
                telegram_notifier.print_report(failed, show_error_detail=True)
            printed = out.getvalue()
            assert "Erreur Telegram: 400 Bad Request" in printed
            assert "Description: Bad Request: invalid chat_id" in printed
            assert "Conseil: essaye --plain-text si Markdown echoue." in printed
            assert "secret" not in printed

            fallback_log = root / "fallback.jsonl"
            fallback_calls = []

            def fake_markdown_then_plain(url, payload, timeout=20):
                fallback_calls.append((url, payload))
                if len(fallback_calls) == 1:
                    assert payload.get("parse_mode") == "Markdown"
                    return {
                        "ok": False,
                        "error_code": 400,
                        "description": "Bad Request: can't parse entities: Can't find end of the entity",
                        "_http_status": 400,
                        "_http_reason": "Bad Request",
                    }
                assert "parse_mode" not in payload
                return {"ok": True, "result": {"message_id": 2}}

            fallback = _with_http_mock(
                fake_markdown_then_plain,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(fallback_log),
                ),
            )
            assert fallback["sent"] == 1
            assert fallback["errors"] == []
            assert fallback["fallback_used"] is True
            assert len(fallback_calls) == 2
            assert "fallback_used" in fallback_log.read_text(encoding="utf-8")

            plain_calls = []

            def fake_plain(url, payload, timeout=20):
                plain_calls.append((url, payload))
                return {"ok": True}

            plain = _with_http_mock(
                fake_plain,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(root / "plain.jsonl"),
                    plain_text=True,
                ),
            )
            assert plain["sent"] == 1
            assert "parse_mode" not in plain_calls[0][1]

            os.environ["TELEGRAM_PARSE_MODE"] = ""
            no_parse_calls = []

            def fake_no_parse(url, payload, timeout=20):
                no_parse_calls.append((url, payload))
                return {"ok": True}

            no_parse = _with_http_mock(
                fake_no_parse,
                lambda: telegram_notifier.send_message_file(
                    str(message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(root / "no_parse.jsonl"),
                ),
            )
            assert no_parse["sent"] == 1
            assert "parse_mode" not in no_parse_calls[0][1]
            os.environ.pop("TELEGRAM_PARSE_MODE", None)

            bom_message = root / "bom.md"
            bom_message.write_text("\ufeffOBSERVATION SHADOW\nRappel: aucune mise.", encoding="utf-8")
            bom_calls = []

            def fake_bom(url, payload, timeout=20):
                bom_calls.append((url, payload))
                return {"ok": True}

            bom = _with_http_mock(
                fake_bom,
                lambda: telegram_notifier.send_message_file(
                    str(bom_message),
                    dry_run=False,
                    allow_send=True,
                    log_path=str(root / "bom.jsonl"),
                ),
            )
            assert bom["sent"] == 1
            assert not bom_calls[0][1]["text"].startswith("\ufeff")

            chunks = telegram_notifier.split_message("a" * 8000, limit=3900)
            assert len(chunks) >= 3
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("test_telegram_notifier ok")


if __name__ == "__main__":
    main()
