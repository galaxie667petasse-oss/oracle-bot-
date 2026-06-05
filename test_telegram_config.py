import os
import tempfile
from pathlib import Path

import telegram_config


def main():
    saved = dict(os.environ)
    try:
        for key in [telegram_config.TOKEN_ENV, telegram_config.CHAT_ENV, telegram_config.DISABLE_SEND_ENV]:
            os.environ.pop(key, None)
        report = telegram_config.validate_config(telegram_config.load_telegram_config())
        assert report["token_present"] is False
        assert report["can_send"] is False
        os.environ[telegram_config.TOKEN_ENV] = "123456:secret"
        os.environ[telegram_config.CHAT_ENV] = "987654"
        os.environ[telegram_config.DISABLE_SEND_ENV] = "false"
        report = telegram_config.validate_config(telegram_config.load_telegram_config())
        assert report["token_present"] is True
        assert report["chat_id_present"] is True
        assert report["can_send"] is True
        assert "secret" not in str(report)
        with tempfile.TemporaryDirectory() as tmp:
            path = telegram_config.write_example(str(Path(tmp) / "telegram.example.env"))
            text = path.read_text(encoding="utf-8")
            assert "TELEGRAM_BOT_TOKEN=" in text
            assert "secret" not in text
    finally:
        os.environ.clear()
        os.environ.update(saved)
    print("test_telegram_config ok")


if __name__ == "__main__":
    main()
