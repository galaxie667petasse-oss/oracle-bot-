from pathlib import Path


SCRIPTS = [
    "scripts/oracle_daily_morning.ps1",
    "scripts/oracle_pre_close.ps1",
    "scripts/oracle_post_match.ps1",
    "scripts/install_windows_tasks.example.ps1",
]


FORBIDDEN = [
    "TELEGRAM_BOT_TOKEN=",
    "API_FOOTBALL" + "_KEY=",
    "THE_ODDS_API" + "_KEY=",
    "x-apisports-key",
    "api.telegram.org/bot",
]


def main():
    root = Path.cwd()
    for rel in SCRIPTS:
        path = root / rel
        assert path.exists(), f"script absent: {rel}"
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in text, f"secret ou endpoint sensible dans {rel}: {forbidden}"
        if "--allow-send" in text:
            assert "ORACLE_ALLOW_TELEGRAM_SEND" in text, f"--allow-send non protege dans {rel}"
        if "--allow-network" in text:
            assert "ORACLE_ALLOW_NETWORK" in text or rel.endswith(".example.ps1"), f"--allow-network non documente/protege dans {rel}"
    print("test_windows_scheduler_scripts ok")


if __name__ == "__main__":
    main()
