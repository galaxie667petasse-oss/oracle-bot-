import os
from dataclasses import dataclass
from pathlib import Path
import pytz

@dataclass(frozen=True)
class Settings:
    version: str = "V5.0-MODULAR"
    timezone: str = "Europe/Paris"
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id: int = int(os.getenv("CHAT_ID", "0") or 0)
    odds_key: str = (os.getenv("ODDSPAPI_KEY", "") or os.getenv("ODDS_API_KEY", "") or os.getenv("THE_ODDS_API_KEY", "")).strip()
    football_key: str = (os.getenv("FOOTBALL_KEY", "") or os.getenv("API_FOOTBALL_KEY", "") or os.getenv("APISPORTS_KEY", "")).strip()
    football_data_key: str = (os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALLDATA_KEY", "")).strip()
    bankroll: float = float(os.getenv("BANKROLL", "100") or 100)
    scan_hour: int = int(os.getenv("SCAN_HOUR", "9") or 9)
    settle_hour: int = int(os.getenv("SETTLE_HOUR", "8") or 8)
    max_matches: int = int(os.getenv("MAX_MATCHES", "80") or 80)
    max_analyzed: int = int(os.getenv("MAX_ANALYZED", "32") or 32)
    top_picks: int = int(os.getenv("TOP_PICKS", "4") or 4)
    watchlist_limit: int = int(os.getenv("WATCHLIST_LIMIT", "6") or 6)
    max_h2h_top: int = int(os.getenv("MAX_H2H_TOP", "1") or 1)
    mode: str = os.getenv("ORACLE_MODE", "balanced").lower().strip()
    odds_regions: str = os.getenv("ODDS_REGIONS", "eu")
    odds_markets: str = os.getenv("ODDS_MARKETS", "h2h,totals,btts")
    db_file: Path = Path(os.getenv("DB_FILE", "oracle_db.json"))
    football_data_comps: tuple = ("PL", "FL1", "BL1", "SA", "PD", "CL", "ELC")

    @property
    def tz(self):
        return pytz.timezone(self.timezone)

    @property
    def mode_cfg(self):
        return {
            "safe": {"min_conf": 62, "min_value": -2},
            "balanced": {"min_conf": 58, "min_value": -8},
            "aggressive": {"min_conf": 56, "min_value": -14},
        }.get(self.mode, {"min_conf": 58, "min_value": -8})

    def validate(self):
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_TOKEN")
        if not self.chat_id:
            missing.append("CHAT_ID")
        if not self.odds_key:
            missing.append("ODDSPAPI_KEY")
        if missing:
            raise RuntimeError("Variables Railway manquantes: " + ", ".join(missing))

settings = Settings()
