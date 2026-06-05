import os
import tempfile
from pathlib import Path

import telegram_notifier


def main():
    saved = dict(os.environ)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            message = Path(tmp) / "message.md"
            message.write_text("OBSERVATION SHADOW\nRappel: aucune mise.", encoding="utf-8")
            dry = telegram_notifier.send_message_file(str(message), dry_run=True, allow_send=False, log_path=str(Path(tmp) / "log.jsonl"))
            assert dry["dry_run"] is True
            assert dry["sent"] == 0
            assert not (Path(tmp) / "log.jsonl").exists()
            os.environ["TELEGRAM_BOT_TOKEN"] = "123:secret"
            os.environ["TELEGRAM_CHAT_ID"] = "456"
            os.environ["TELEGRAM_DISABLE_SEND"] = "false"
            calls = []

            def fake_post(url, payload, timeout=20):
                calls.append((url, payload))
                return {"ok": True, "result": {"message_id": 1}}

            original = telegram_notifier._http_post
            telegram_notifier._http_post = fake_post
            try:
                sent = telegram_notifier.send_message_file(str(message), dry_run=False, allow_send=True, log_path=str(Path(tmp) / "log.jsonl"))
            finally:
                telegram_notifier._http_post = original
            assert sent["sent"] == 1
            assert calls
            assert "secret" not in str(sent)
            assert (Path(tmp) / "log.jsonl").exists()
            chunks = telegram_notifier.split_message("a" * 8000, limit=3900)
            assert len(chunks) >= 3
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("test_telegram_notifier ok")


if __name__ == "__main__":
    main()
