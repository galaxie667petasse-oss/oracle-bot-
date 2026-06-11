import os
import tempfile
from pathlib import Path

import telegram_pipeline_smoke_test


def main():
    saved = dict(os.environ)
    try:
        os.environ["TELEGRAM_BOT_TOKEN"] = "123:secret"
        os.environ["TELEGRAM_CHAT_ID"] = "-100123"
        os.environ["TELEGRAM_DISABLE_SEND"] = "false"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            daily_calls = []
            send_calls = []
            original_daily = telegram_pipeline_smoke_test.run_daily_reporter
            original_send = telegram_pipeline_smoke_test.send_message_text

            def fake_daily(date, **kwargs):
                daily_calls.append({"date": date, **kwargs})
                preview = Path(kwargs["output"])
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_text("ORACLE DAILY\nAucune mise.", encoding="utf-8")
                return {
                    "date": date,
                    "preview": str(preview),
                    "message": "ORACLE DAILY\nAucune mise.",
                    "notify": {"dry_run": True, "sent": 0, "errors": []},
                    "lab_only": True,
                    "can_influence_picks": False,
                }

            def fake_send(text, **kwargs):
                send_calls.append({"text": text, **kwargs})
                return {
                    "dry_run": kwargs.get("dry_run"),
                    "sent": 0 if kwargs.get("dry_run") else 1,
                    "errors": [],
                    "plain_text": kwargs.get("plain_text", False),
                }

            telegram_pipeline_smoke_test.run_daily_reporter = fake_daily
            telegram_pipeline_smoke_test.send_message_text = fake_send
            try:
                dry = telegram_pipeline_smoke_test.build_telegram_pipeline_smoke_test(
                    "2026-06-11",
                    allow_send=False,
                    plain_text_test=False,
                    output_json=str(root / "reports" / "telegram.json"),
                    output_html=str(root / "reports" / "telegram.html"),
                    reports_dir=str(root / "reports" / "telegram_smoke"),
                )
                assert dry["observations_published"] is False
                assert dry["test_send"]["skipped"] is True
                assert send_calls[-1]["allow_send"] is False
                assert send_calls[-1]["dry_run"] is True
                assert "secret" not in str(dry)
                assert (root / "reports" / "telegram.json").exists()

                sent = telegram_pipeline_smoke_test.build_telegram_pipeline_smoke_test(
                    "2026-06-11",
                    allow_send=True,
                    plain_text_test=True,
                    output_json=str(root / "reports" / "telegram_send.json"),
                    output_html=str(root / "reports" / "telegram_send.html"),
                    reports_dir=str(root / "reports" / "telegram_smoke_send"),
                )
                assert sent["test_send"]["sent"] == 1
                assert send_calls[-1]["text"] == "ORACLE TEST READ ONLY"
                assert send_calls[-1]["allow_send"] is True
                assert send_calls[-1]["dry_run"] is False
                assert send_calls[-1]["plain_text"] is True
                assert "secret" not in str(sent)
            finally:
                telegram_pipeline_smoke_test.run_daily_reporter = original_daily
                telegram_pipeline_smoke_test.send_message_text = original_send
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("test_telegram_pipeline_smoke_test ok")


if __name__ == "__main__":
    main()
