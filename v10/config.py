import os
from typing import Any, Mapping
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SECRET_KEYS = {
    "API_FOOTBALL_KEY",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DATABASE_URL",
    "THE_ODDS_API_KEY",
    "ODDS_API_KEY",
    "ODDSPAPI_KEY",
    "RAILWAY_TOKEN",
    "GITHUB_TOKEN",
}


def _truthy(value: Any, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "oui", "on", "y"}


def mask_secret(value: str, visible: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= visible:
        return "***"
    return text[:visible] + "***"


def mask_database_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("sqlite"):
        return "sqlite://***"
    try:
        parsed = urlsplit(text)
    except Exception:
        return "***"
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db_name = parsed.path.rsplit("/", 1)[-1] if parsed.path else ""
    return f"{parsed.scheme}://***@{host}{port}/{db_name}".rstrip("/")


def normalize_database_url(url: str, allow_sqlite: bool = True) -> str:
    text = str(url or "").strip()
    if not text:
        raise ValueError("DATABASE_URL absent: configurer PostgreSQL ou utiliser SQLite explicitement pour tests.")
    if text.startswith("postgres://"):
        return "postgresql+psycopg://" + text[len("postgres://") :]
    if text.startswith("postgresql://"):
        return "postgresql+psycopg://" + text[len("postgresql://") :]
    if text.startswith("postgresql+"):
        return text
    if text.startswith("sqlite"):
        if not allow_sqlite:
            raise ValueError("SQLite est reserve aux tests locaux et ne valide pas PostgreSQL.")
        return text
    raise ValueError("DATABASE_URL doit utiliser postgresql/postgres ou sqlite pour les tests.")


class V10Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    database_url: str = Field(default="", alias="DATABASE_URL")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=5, alias="DATABASE_MAX_OVERFLOW")
    database_pool_timeout_seconds: float = Field(default=30.0, alias="DATABASE_POOL_TIMEOUT_SECONDS")
    database_statement_timeout_ms: int = Field(default=30_000, alias="DATABASE_STATEMENT_TIMEOUT_MS")
    api_football_key: str = Field(default="", alias="API_FOOTBALL_KEY")
    api_football_base_url: str = Field(default="https://v3.football.api-sports.io", alias="API_FOOTBALL_BASE_URL")
    api_football_timeout_seconds: float = Field(default=20.0, alias="API_FOOTBALL_TIMEOUT_SECONDS")
    api_football_max_retries: int = Field(default=3, alias="API_FOOTBALL_MAX_RETRIES")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model_fast: str = Field(default="", alias="OPENAI_MODEL_FAST")
    openai_model_specialist: str = Field(default="", alias="OPENAI_MODEL_SPECIALIST")
    openai_model_final: str = Field(default="", alias="OPENAI_MODEL_FINAL")
    openai_daily_budget_usd: float = Field(default=0.0, alias="OPENAI_DAILY_BUDGET_USD")
    llm_enabled: bool = Field(default=False, alias="LLM_ENABLED")
    llm_shadow_only: bool = Field(default=True, alias="LLM_SHADOW_ONLY")
    llm_allow_paid_calls: bool = Field(default=False, alias="LLM_ALLOW_PAID_CALLS")
    openai_scan_budget_usd: float = Field(default=0.0, alias="OPENAI_SCAN_BUDGET_USD")
    openai_fixture_budget_usd: float = Field(default=0.0, alias="OPENAI_FIXTURE_BUDGET_USD")
    openai_candidate_budget_usd: float = Field(default=0.0, alias="OPENAI_CANDIDATE_BUDGET_USD")
    openai_sol_call_budget_usd: float = Field(default=0.0, alias="OPENAI_SOL_CALL_BUDGET_USD")
    openai_reasoning_fast: str = Field(default="low", alias="OPENAI_REASONING_FAST")
    openai_reasoning_specialist: str = Field(default="medium", alias="OPENAI_REASONING_SPECIALIST")
    openai_reasoning_final: str = Field(default="high", alias="OPENAI_REASONING_FINAL")
    openai_max_concurrency: int = Field(default=3, alias="OPENAI_MAX_CONCURRENCY")
    openai_max_agent_rounds: int = Field(default=2, alias="OPENAI_MAX_AGENT_ROUNDS")
    openai_max_tool_calls_per_agent: int = Field(default=4, alias="OPENAI_MAX_TOOL_CALLS_PER_AGENT")
    openai_max_calls_per_scan: int = Field(default=30, alias="OPENAI_MAX_CALLS_PER_SCAN")
    openai_max_candidates_per_scan: int = Field(default=10, alias="OPENAI_MAX_CANDIDATES_PER_SCAN")
    openai_max_sol_calls_per_scan: int = Field(default=2, alias="OPENAI_MAX_SOL_CALLS_PER_SCAN")
    openai_max_sol_calls_per_fixture: int = Field(default=1, alias="OPENAI_MAX_SOL_CALLS_PER_FIXTURE")
    openai_allow_xhigh: bool = Field(default=False, alias="OPENAI_ALLOW_XHIGH")
    openai_allow_max: bool = Field(default=False, alias="OPENAI_ALLOW_MAX")
    openai_allow_pro: bool = Field(default=False, alias="OPENAI_ALLOW_PRO")
    openai_max_calls_per_fixture: int = Field(default=0, alias="OPENAI_MAX_CALLS_PER_FIXTURE")
    openai_max_finalists_per_scan: int = Field(default=0, alias="OPENAI_MAX_FINALISTS_PER_SCAN")
    openai_fast_max_input_tokens: int = Field(default=6000, alias="OPENAI_FAST_MAX_INPUT_TOKENS")
    openai_fast_max_output_tokens: int = Field(default=350, alias="OPENAI_FAST_MAX_OUTPUT_TOKENS")
    openai_specialist_max_input_tokens: int = Field(default=10000, alias="OPENAI_SPECIALIST_MAX_INPUT_TOKENS")
    openai_specialist_max_output_tokens: int = Field(default=700, alias="OPENAI_SPECIALIST_MAX_OUTPUT_TOKENS")
    openai_final_max_input_tokens: int = Field(default=12000, alias="OPENAI_FINAL_MAX_INPUT_TOKENS")
    openai_final_max_output_tokens: int = Field(default=800, alias="OPENAI_FINAL_MAX_OUTPUT_TOKENS")
    openai_batch_enabled: bool = Field(default=False, alias="OPENAI_BATCH_ENABLED")
    telegram_enabled: bool = Field(default=False, alias="TELEGRAM_ENABLED")
    telegram_disable_send: bool = Field(default=True, alias="TELEGRAM_DISABLE_SEND")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    paper_betting_enabled: bool = Field(default=True, alias="PAPER_BETTING_ENABLED")
    real_money_actions_enabled: bool = Field(default=False, alias="REAL_MONEY_ACTIONS_ENABLED")
    statistical_model_validated_for_signals: bool = Field(default=False, alias="STATISTICAL_MODEL_VALIDATED_FOR_SIGNALS")
    min_data_completeness: float = Field(default=0.75, alias="MIN_DATA_COMPLETENESS")
    max_odds_age_seconds: int = Field(default=7200, alias="MAX_ODDS_AGE_SECONDS")
    min_bookmaker_count: int = Field(default=2, alias="MIN_BOOKMAKER_COUNT")
    min_edge_percentage_points: float = Field(default=3.0, alias="MIN_EDGE_PERCENTAGE_POINTS")
    min_expected_value: float = Field(default=0.02, alias="MIN_EXPECTED_VALUE")
    max_uncertainty: float = Field(default=0.08, alias="MAX_UNCERTAINTY")
    max_signals_per_day: int = Field(default=0, alias="MAX_SIGNALS_PER_DAY")
    kelly_fraction: float = Field(default=0.10, alias="KELLY_FRACTION")
    max_stake_percent_bankroll: float = Field(default=1.0, alias="MAX_STAKE_PERCENT_BANKROLL")
    max_daily_exposure_percent: float = Field(default=3.0, alias="MAX_DAILY_EXPOSURE_PERCENT")
    max_correlated_exposure_percent: float = Field(default=1.5, alias="MAX_CORRELATED_EXPOSURE_PERCENT")
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")
    scheduler_max_runtime_seconds: int = Field(default=240, alias="SCHEDULER_MAX_RUNTIME_SECONDS")
    scheduler_shutdown_margin_seconds: int = Field(default=20, alias="SCHEDULER_SHUTDOWN_MARGIN_SECONDS")
    scheduler_max_jobs_per_tick: int = Field(default=50, alias="SCHEDULER_MAX_JOBS_PER_TICK")
    scheduler_max_concurrency: int = Field(default=3, alias="SCHEDULER_MAX_CONCURRENCY")
    scan_cron: str = Field(default="", alias="SCAN_CRON")
    results_cron: str = Field(default="", alias="RESULTS_CRON")
    closing_odds_cron: str = Field(default="", alias="CLOSING_ODDS_CRON")
    max_fixture_age_minutes: int = Field(default=30, alias="MAX_FIXTURE_AGE_MINUTES")
    max_odds_age_minutes_t24: int = Field(default=180, alias="MAX_ODDS_AGE_MINUTES_T24")
    max_odds_age_minutes_t90: int = Field(default=20, alias="MAX_ODDS_AGE_MINUTES_T90")
    max_odds_age_minutes_t30: int = Field(default=10, alias="MAX_ODDS_AGE_MINUTES_T30")
    max_odds_age_minutes_t10: int = Field(default=5, alias="MAX_ODDS_AGE_MINUTES_T10")
    max_lineup_age_minutes: int = Field(default=15, alias="MAX_LINEUP_AGE_MINUTES")
    max_availability_age_minutes: int = Field(default=180, alias="MAX_AVAILABILITY_AGE_MINUTES")
    max_team_stats_age_hours: int = Field(default=24, alias="MAX_TEAM_STATS_AGE_HOURS")
    max_standings_age_hours: int = Field(default=24, alias="MAX_STANDINGS_AGE_HOURS")
    material_odds_relative_change: float = Field(default=0.03, alias="MATERIAL_ODDS_RELATIVE_CHANGE")
    material_fair_probability_change_pp: float = Field(default=0.015, alias="MATERIAL_FAIR_PROBABILITY_CHANGE_PP")
    material_model_probability_change_pp: float = Field(default=0.02, alias="MATERIAL_MODEL_PROBABILITY_CHANGE_PP")
    material_uncertainty_change: float = Field(default=0.10, alias="MATERIAL_UNCERTAINTY_CHANGE")
    internal_api_token: str = Field(default="", alias="INTERNAL_API_TOKEN")
    dashboard_enabled: bool = Field(default=False, alias="DASHBOARD_ENABLED")
    dashboard_require_auth: bool = Field(default=True, alias="DASHBOARD_REQUIRE_AUTH")
    railway_allow_deploy: bool = Field(default=False, alias="RAILWAY_ALLOW_DEPLOY")

    @model_validator(mode="after")
    def _validate_safety(self) -> "V10Settings":
        if self.real_money_actions_enabled:
            raise ValueError("REAL_MONEY_ACTIONS_ENABLED doit rester false: action bookmaker interdite.")
        if self.telegram_enabled and not self.telegram_disable_send and self.dry_run:
            raise ValueError("Telegram réel interdit en dry-run.")
        if self.railway_allow_deploy and self.app_env.lower() not in {"staging", "ci"}:
            raise ValueError("RAILWAY_ALLOW_DEPLOY reste desactive hors staging/ci explicite.")
        if self.app_env.lower() in {"production", "prod"} and self.real_money_actions_enabled:
            raise ValueError("Configuration production dangereuse: real money interdit.")
        if self.llm_allow_paid_calls and not self.llm_enabled:
            raise ValueError("LLM_ALLOW_PAID_CALLS exige LLM_ENABLED=true.")
        if self.llm_allow_paid_calls and self.openai_daily_budget_usd <= 0:
            raise ValueError("LLM_ALLOW_PAID_CALLS exige un budget quotidien positif.")
        return self

    def validate_lab_safety(self) -> list[str]:
        errors: list[str] = []
        if self.real_money_actions_enabled:
            errors.append("REAL_MONEY_ACTIONS_ENABLED doit rester false: action bookmaker interdite.")
        return errors

    @property
    def is_postgres_configured(self) -> bool:
        return normalize_database_url(self.database_url, allow_sqlite=True).startswith("postgresql+") if self.database_url else False

    def sqlalchemy_url(self, allow_sqlite: bool = True) -> str:
        return normalize_database_url(self.database_url, allow_sqlite=allow_sqlite)

    def require_database_url(self, allow_sqlite: bool = True) -> str:
        return self.sqlalchemy_url(allow_sqlite=allow_sqlite)

    def safe_report(self, env: Mapping[str, str] | None = None) -> dict[str, Any]:
        env = env or os.environ
        return {
            "app_env": self.app_env,
            "log_level": self.log_level,
            "dry_run": self.dry_run,
            "paper_betting_enabled": self.paper_betting_enabled,
            "real_money_actions_enabled": self.real_money_actions_enabled,
            "database_configured": bool(self.database_url),
            "database_url": mask_database_url(self.database_url),
            "database_echo": self.database_echo,
            "database_pool_size": self.database_pool_size,
            "database_max_overflow": self.database_max_overflow,
            "database_pool_timeout_seconds": self.database_pool_timeout_seconds,
            "database_statement_timeout_ms": self.database_statement_timeout_ms,
            "telegram_enabled": self.telegram_enabled,
            "llm": {
                "enabled": self.llm_enabled,
                "shadow_only": self.llm_shadow_only,
                "allow_paid_calls": self.llm_allow_paid_calls,
                "daily_budget_usd": self.openai_daily_budget_usd,
                "scan_budget_usd": self.openai_scan_budget_usd,
                "fixture_budget_usd": self.openai_fixture_budget_usd,
                "candidate_budget_usd": self.openai_candidate_budget_usd,
                "sol_call_budget_usd": self.openai_sol_call_budget_usd,
                "batch_enabled": self.openai_batch_enabled,
                "allow_xhigh": self.openai_allow_xhigh,
                "allow_max": self.openai_allow_max,
                "allow_pro": self.openai_allow_pro,
            },
            "openai_models_configured": {
                "fast": bool(self.openai_model_fast),
                "specialist": bool(self.openai_model_specialist),
                "final": bool(self.openai_model_final),
            },
            "secrets_present": {key: bool(str(env.get(key, "")).strip()) for key in sorted(SECRET_KEYS)},
            "lab_only": True,
            "can_influence_picks": False,
            "statistical_model_validated_for_signals": self.statistical_model_validated_for_signals,
            "scheduler": {
                "enabled": self.scheduler_enabled,
                "max_runtime_seconds": self.scheduler_max_runtime_seconds,
                "shutdown_margin_seconds": self.scheduler_shutdown_margin_seconds,
                "max_jobs_per_tick": self.scheduler_max_jobs_per_tick,
                "max_concurrency": self.scheduler_max_concurrency,
            },
            "railway_allow_deploy": self.railway_allow_deploy,
            "errors": self.validate_lab_safety(),
        }


def _settings_data_from_env(env: Mapping[str, str]) -> dict[str, Any]:
    return {
        "APP_ENV": str(env.get("APP_ENV", "local")).strip() or "local",
        "LOG_LEVEL": str(env.get("LOG_LEVEL", "INFO")).strip() or "INFO",
        "DATABASE_URL": str(env.get("DATABASE_URL", "")).strip(),
        "DATABASE_ECHO": _truthy(env.get("DATABASE_ECHO"), default=False),
        "DATABASE_POOL_SIZE": int(float(str(env.get("DATABASE_POOL_SIZE", 5)).strip() or 5)),
        "DATABASE_MAX_OVERFLOW": int(float(str(env.get("DATABASE_MAX_OVERFLOW", 5)).strip() or 5)),
        "DATABASE_POOL_TIMEOUT_SECONDS": float(str(env.get("DATABASE_POOL_TIMEOUT_SECONDS", 30)).strip() or 30),
        "DATABASE_STATEMENT_TIMEOUT_MS": int(float(str(env.get("DATABASE_STATEMENT_TIMEOUT_MS", 30000)).strip() or 30000)),
        "API_FOOTBALL_KEY": str(env.get("API_FOOTBALL_KEY", "")).strip(),
        "API_FOOTBALL_BASE_URL": str(env.get("API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io")).strip(),
        "API_FOOTBALL_TIMEOUT_SECONDS": float(str(env.get("API_FOOTBALL_TIMEOUT_SECONDS", 20)).strip() or 20),
        "API_FOOTBALL_MAX_RETRIES": int(float(str(env.get("API_FOOTBALL_MAX_RETRIES", 3)).strip() or 3)),
        "OPENAI_API_KEY": str(env.get("OPENAI_API_KEY", "")).strip(),
        "OPENAI_MODEL_FAST": str(env.get("OPENAI_MODEL_FAST", "")).strip(),
        "OPENAI_MODEL_SPECIALIST": str(env.get("OPENAI_MODEL_SPECIALIST", "")).strip(),
        "OPENAI_MODEL_FINAL": str(env.get("OPENAI_MODEL_FINAL", "")).strip(),
        "OPENAI_DAILY_BUDGET_USD": float(str(env.get("OPENAI_DAILY_BUDGET_USD", 0)).strip() or 0),
        "LLM_ENABLED": _truthy(env.get("LLM_ENABLED"), default=False),
        "LLM_SHADOW_ONLY": _truthy(env.get("LLM_SHADOW_ONLY"), default=True),
        "LLM_ALLOW_PAID_CALLS": _truthy(env.get("LLM_ALLOW_PAID_CALLS"), default=False),
        "OPENAI_SCAN_BUDGET_USD": float(str(env.get("OPENAI_SCAN_BUDGET_USD", 0)).strip() or 0),
        "OPENAI_FIXTURE_BUDGET_USD": float(str(env.get("OPENAI_FIXTURE_BUDGET_USD", 0)).strip() or 0),
        "OPENAI_CANDIDATE_BUDGET_USD": float(str(env.get("OPENAI_CANDIDATE_BUDGET_USD", 0)).strip() or 0),
        "OPENAI_SOL_CALL_BUDGET_USD": float(str(env.get("OPENAI_SOL_CALL_BUDGET_USD", 0)).strip() or 0),
        "OPENAI_REASONING_FAST": str(env.get("OPENAI_REASONING_FAST", "low")).strip() or "low",
        "OPENAI_REASONING_SPECIALIST": str(env.get("OPENAI_REASONING_SPECIALIST", "medium")).strip() or "medium",
        "OPENAI_REASONING_FINAL": str(env.get("OPENAI_REASONING_FINAL", "high")).strip() or "high",
        "OPENAI_MAX_CONCURRENCY": int(float(str(env.get("OPENAI_MAX_CONCURRENCY", 3)).strip() or 3)),
        "OPENAI_MAX_AGENT_ROUNDS": int(float(str(env.get("OPENAI_MAX_AGENT_ROUNDS", 2)).strip() or 2)),
        "OPENAI_MAX_TOOL_CALLS_PER_AGENT": int(float(str(env.get("OPENAI_MAX_TOOL_CALLS_PER_AGENT", 4)).strip() or 4)),
        "OPENAI_MAX_CALLS_PER_SCAN": int(float(str(env.get("OPENAI_MAX_CALLS_PER_SCAN", 30)).strip() or 30)),
        "OPENAI_MAX_CANDIDATES_PER_SCAN": int(float(str(env.get("OPENAI_MAX_CANDIDATES_PER_SCAN", 10)).strip() or 10)),
        "OPENAI_MAX_SOL_CALLS_PER_SCAN": int(float(str(env.get("OPENAI_MAX_SOL_CALLS_PER_SCAN", 2)).strip() or 2)),
        "OPENAI_MAX_SOL_CALLS_PER_FIXTURE": int(float(str(env.get("OPENAI_MAX_SOL_CALLS_PER_FIXTURE", 1)).strip() or 1)),
        "OPENAI_ALLOW_XHIGH": _truthy(env.get("OPENAI_ALLOW_XHIGH"), default=False),
        "OPENAI_ALLOW_MAX": _truthy(env.get("OPENAI_ALLOW_MAX"), default=False),
        "OPENAI_ALLOW_PRO": _truthy(env.get("OPENAI_ALLOW_PRO"), default=False),
        "OPENAI_MAX_CALLS_PER_FIXTURE": int(float(str(env.get("OPENAI_MAX_CALLS_PER_FIXTURE", 0)).strip() or 0)),
        "OPENAI_MAX_FINALISTS_PER_SCAN": int(float(str(env.get("OPENAI_MAX_FINALISTS_PER_SCAN", 0)).strip() or 0)),
        "OPENAI_FAST_MAX_INPUT_TOKENS": int(float(str(env.get("OPENAI_FAST_MAX_INPUT_TOKENS", 6000)).strip() or 6000)),
        "OPENAI_FAST_MAX_OUTPUT_TOKENS": int(float(str(env.get("OPENAI_FAST_MAX_OUTPUT_TOKENS", 350)).strip() or 350)),
        "OPENAI_SPECIALIST_MAX_INPUT_TOKENS": int(float(str(env.get("OPENAI_SPECIALIST_MAX_INPUT_TOKENS", 10000)).strip() or 10000)),
        "OPENAI_SPECIALIST_MAX_OUTPUT_TOKENS": int(float(str(env.get("OPENAI_SPECIALIST_MAX_OUTPUT_TOKENS", 700)).strip() or 700)),
        "OPENAI_FINAL_MAX_INPUT_TOKENS": int(float(str(env.get("OPENAI_FINAL_MAX_INPUT_TOKENS", 12000)).strip() or 12000)),
        "OPENAI_FINAL_MAX_OUTPUT_TOKENS": int(float(str(env.get("OPENAI_FINAL_MAX_OUTPUT_TOKENS", 800)).strip() or 800)),
        "OPENAI_BATCH_ENABLED": _truthy(env.get("OPENAI_BATCH_ENABLED"), default=False),
        "TELEGRAM_ENABLED": _truthy(env.get("TELEGRAM_ENABLED"), default=False),
        "TELEGRAM_DISABLE_SEND": _truthy(env.get("TELEGRAM_DISABLE_SEND"), default=True),
        "DRY_RUN": _truthy(env.get("DRY_RUN"), default=True),
        "PAPER_BETTING_ENABLED": _truthy(env.get("PAPER_BETTING_ENABLED"), default=True),
        "REAL_MONEY_ACTIONS_ENABLED": _truthy(env.get("REAL_MONEY_ACTIONS_ENABLED"), default=False),
        "STATISTICAL_MODEL_VALIDATED_FOR_SIGNALS": _truthy(env.get("STATISTICAL_MODEL_VALIDATED_FOR_SIGNALS"), default=False),
        "MIN_DATA_COMPLETENESS": float(str(env.get("MIN_DATA_COMPLETENESS", 0.75)).strip() or 0.75),
        "MAX_ODDS_AGE_SECONDS": int(float(str(env.get("MAX_ODDS_AGE_SECONDS", 7200)).strip() or 7200)),
        "MIN_BOOKMAKER_COUNT": int(float(str(env.get("MIN_BOOKMAKER_COUNT", 2)).strip() or 2)),
        "MIN_EDGE_PERCENTAGE_POINTS": float(str(env.get("MIN_EDGE_PERCENTAGE_POINTS", 3.0)).strip() or 3.0),
        "MIN_EXPECTED_VALUE": float(str(env.get("MIN_EXPECTED_VALUE", 0.02)).strip() or 0.02),
        "MAX_UNCERTAINTY": float(str(env.get("MAX_UNCERTAINTY", 0.08)).strip() or 0.08),
        "MAX_SIGNALS_PER_DAY": int(float(str(env.get("MAX_SIGNALS_PER_DAY", 0)).strip() or 0)),
        "KELLY_FRACTION": float(str(env.get("KELLY_FRACTION", 0.10)).strip() or 0.10),
        "MAX_STAKE_PERCENT_BANKROLL": float(str(env.get("MAX_STAKE_PERCENT_BANKROLL", 1.0)).strip() or 1.0),
        "MAX_DAILY_EXPOSURE_PERCENT": float(str(env.get("MAX_DAILY_EXPOSURE_PERCENT", 3.0)).strip() or 3.0),
        "MAX_CORRELATED_EXPOSURE_PERCENT": float(str(env.get("MAX_CORRELATED_EXPOSURE_PERCENT", 1.5)).strip() or 1.5),
        "SCHEDULER_ENABLED": _truthy(env.get("SCHEDULER_ENABLED"), default=False),
        "SCHEDULER_MAX_RUNTIME_SECONDS": int(float(str(env.get("SCHEDULER_MAX_RUNTIME_SECONDS", 240)).strip() or 240)),
        "SCHEDULER_SHUTDOWN_MARGIN_SECONDS": int(float(str(env.get("SCHEDULER_SHUTDOWN_MARGIN_SECONDS", 20)).strip() or 20)),
        "SCHEDULER_MAX_JOBS_PER_TICK": int(float(str(env.get("SCHEDULER_MAX_JOBS_PER_TICK", 50)).strip() or 50)),
        "SCHEDULER_MAX_CONCURRENCY": int(float(str(env.get("SCHEDULER_MAX_CONCURRENCY", 3)).strip() or 3)),
        "SCAN_CRON": str(env.get("SCAN_CRON", "")).strip(),
        "RESULTS_CRON": str(env.get("RESULTS_CRON", "")).strip(),
        "CLOSING_ODDS_CRON": str(env.get("CLOSING_ODDS_CRON", "")).strip(),
        "MAX_FIXTURE_AGE_MINUTES": int(float(str(env.get("MAX_FIXTURE_AGE_MINUTES", 30)).strip() or 30)),
        "MAX_ODDS_AGE_MINUTES_T24": int(float(str(env.get("MAX_ODDS_AGE_MINUTES_T24", 180)).strip() or 180)),
        "MAX_ODDS_AGE_MINUTES_T90": int(float(str(env.get("MAX_ODDS_AGE_MINUTES_T90", 20)).strip() or 20)),
        "MAX_ODDS_AGE_MINUTES_T30": int(float(str(env.get("MAX_ODDS_AGE_MINUTES_T30", 10)).strip() or 10)),
        "MAX_ODDS_AGE_MINUTES_T10": int(float(str(env.get("MAX_ODDS_AGE_MINUTES_T10", 5)).strip() or 5)),
        "MAX_LINEUP_AGE_MINUTES": int(float(str(env.get("MAX_LINEUP_AGE_MINUTES", 15)).strip() or 15)),
        "MAX_AVAILABILITY_AGE_MINUTES": int(float(str(env.get("MAX_AVAILABILITY_AGE_MINUTES", 180)).strip() or 180)),
        "MAX_TEAM_STATS_AGE_HOURS": int(float(str(env.get("MAX_TEAM_STATS_AGE_HOURS", 24)).strip() or 24)),
        "MAX_STANDINGS_AGE_HOURS": int(float(str(env.get("MAX_STANDINGS_AGE_HOURS", 24)).strip() or 24)),
        "MATERIAL_ODDS_RELATIVE_CHANGE": float(str(env.get("MATERIAL_ODDS_RELATIVE_CHANGE", 0.03)).strip() or 0.03),
        "MATERIAL_FAIR_PROBABILITY_CHANGE_PP": float(str(env.get("MATERIAL_FAIR_PROBABILITY_CHANGE_PP", 0.015)).strip() or 0.015),
        "MATERIAL_MODEL_PROBABILITY_CHANGE_PP": float(str(env.get("MATERIAL_MODEL_PROBABILITY_CHANGE_PP", 0.02)).strip() or 0.02),
        "MATERIAL_UNCERTAINTY_CHANGE": float(str(env.get("MATERIAL_UNCERTAINTY_CHANGE", 0.10)).strip() or 0.10),
        "INTERNAL_API_TOKEN": str(env.get("INTERNAL_API_TOKEN", "")).strip(),
        "DASHBOARD_ENABLED": _truthy(env.get("DASHBOARD_ENABLED"), default=False),
        "DASHBOARD_REQUIRE_AUTH": _truthy(env.get("DASHBOARD_REQUIRE_AUTH"), default=True),
        "RAILWAY_ALLOW_DEPLOY": _truthy(env.get("RAILWAY_ALLOW_DEPLOY"), default=False),
    }


def load_settings(env: Mapping[str, str] | None = None) -> V10Settings:
    if env is None:
        return V10Settings()
    return V10Settings(**_settings_data_from_env(env))
