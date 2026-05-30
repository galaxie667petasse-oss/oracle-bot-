import os
import tempfile
from pathlib import Path

import odds_source_config


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "odds_sources.example.json"
        odds_source_config.write_example(str(path))
        config = odds_source_config.load_odds_source_config(str(path))
        report = odds_source_config.validate_config(config)
        assert report["ok"] is True
        assert "api_football" in report["sources"]
        os.environ["API_FOOTBALL_KEY"] = "secret_value_for_test"
        assert odds_source_config.get_api_key_from_env("api_football", config) == "secret_value_for_test"
        del os.environ["API_FOOTBALL_KEY"]
        bad = {"manual_csv": {"enabled": True}}
        bad_report = odds_source_config.validate_config(bad)
        assert bad_report["ok"] is False

    print("test_odds_source_config ok")


if __name__ == "__main__":
    main()
