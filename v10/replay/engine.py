import json
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy.orm import Session

from v10 import VERSION
from v10.db.repositories import (
    BookmakerRepository,
    CompetitionRepository,
    FixtureRepository,
    IngestionRunRepository,
    MarketRepository,
    OddsSnapshotRepository,
    ProviderRepository,
    RawPayloadRepository,
    SeasonRepository,
    TeamRepository,
    canonical_key,
    ensure_default_markets,
)
from v10.db.models import Provider
from v10.normalization import api_football, the_odds_api
from v10.normalization.schemas import CanonicalFixtureObservation, CanonicalOddsObservation, NormalizationReport
from v10.time import parse_utc, utc_now


MAX_REPLAY_FILE_BYTES = 20_000_000

PROVIDER_DEFAULTS = {
    "api_football": {
        "name": "API-Football",
        "provider_type": "football",
        "base_url": "https://v3.football.api-sports.io",
    },
    "the_odds_api": {
        "name": "The Odds API",
        "provider_type": "odds",
        "base_url": "https://api.the-odds-api.com",
    },
}


def load_json_limited(path: str, max_bytes: int = MAX_REPLAY_FILE_BYTES) -> Any:
    source = Path(path)
    size = source.stat().st_size
    if size > max_bytes:
        raise ValueError(f"payload trop volumineux pour replay direct: {size} octets > {max_bytes}")
    return json.loads(source.read_text(encoding="utf-8"))


def infer_endpoint(provider_key: str, payload: Any) -> str:
    if provider_key == "api_football" and isinstance(payload, Mapping):
        endpoint = str(payload.get("get") or "").strip()
        if endpoint:
            return endpoint
        response = payload.get("response") or []
        if response and isinstance(response, list) and any((item.get("bookmakers") if isinstance(item, Mapping) else None) for item in response):
            return "odds"
        return "fixtures"
    if provider_key == "the_odds_api":
        return "odds"
    return "payload"


def normalize_provider_payload(provider_key: str, endpoint: str, payload: Any, observed_at: Any, raw_payload_id: str | None = None) -> NormalizationReport:
    endpoint_key = endpoint.strip().lower()
    if provider_key == "api_football":
        if endpoint_key == "odds" or "odds" in endpoint_key:
            return api_football.normalize_odds_payload(payload, observed_at, raw_payload_id=raw_payload_id)
        return api_football.normalize_fixtures_payload(payload, observed_at)
    if provider_key == "the_odds_api":
        return the_odds_api.normalize_odds_payload(payload, observed_at, raw_payload_id=raw_payload_id)
    return NormalizationReport(provider_key=provider_key, endpoint=endpoint, errors=[f"provider non supporte: {provider_key}"])


def _provider_defaults(provider_key: str) -> dict[str, str]:
    return PROVIDER_DEFAULTS.get(provider_key, {"name": provider_key, "provider_type": "unknown", "base_url": ""})


def _apply_fixture(session: Session, provider_id: str, obs: CanonicalFixtureObservation, raw_payload_id: str | None) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "ignored": 0}
    competition, created = CompetitionRepository(session).upsert_competition(
        provider_id,
        obs.external_competition_id,
        obs.competition_name,
        country=obs.country,
        metadata=obs.metadata,
    )
    counts["inserted" if created else "updated"] += 1
    season_id = None
    if obs.season_external_id:
        season, created = SeasonRepository(session).upsert_season(
            competition.id,
            obs.season_external_id,
            name=obs.season_name,
            status="active",
        )
        season_id = season.id
        counts["inserted" if created else "updated"] += 1
    home, created = TeamRepository(session).upsert_team(
        provider_id,
        obs.home_team_external_id,
        obs.home_team_name,
        country=obs.country,
        metadata={"warnings": obs.warnings},
    )
    counts["inserted" if created else "updated"] += 1
    away, created = TeamRepository(session).upsert_team(
        provider_id,
        obs.away_team_external_id,
        obs.away_team_name,
        country=obs.country,
        metadata={"warnings": obs.warnings},
    )
    counts["inserted" if created else "updated"] += 1
    fixture, created = FixtureRepository(session).upsert_fixture(
        provider_id=provider_id,
        external_id=obs.external_fixture_id,
        competition_id=competition.id,
        season_id=season_id,
        home_team_id=home.id,
        away_team_id=away.id,
        event_time=obs.event_time,
        canonical_status=obs.canonical_status,
        provider_status=obs.provider_status,
        observed_at=obs.observed_at,
        venue=obs.venue,
        round_name=obs.round_name,
        metadata={"warnings": obs.warnings},
    )
    counts["inserted" if created else "updated"] += 1
    provider_status = str(obs.provider_status or "").strip().upper()
    if obs.canonical_status != "UNKNOWN" or provider_status not in ("", "UNKNOWN"):
        _, created = FixtureRepository(session).append_fixture_status(
            fixture.id,
            obs.canonical_status,
            obs.provider_status,
            obs.observed_at,
            raw_payload_id=raw_payload_id,
        )
        counts["inserted" if created else "ignored"] += 1
    else:
        counts["ignored"] += 1
    return counts


def _apply_odds(session: Session, provider_id: str, obs: CanonicalOddsObservation, raw_payload_id: str | None, ingestion_run_id: str | None) -> dict[str, int]:
    fixture = FixtureRepository(session).get_by_external(provider_id, obs.external_fixture_id)
    if not fixture:
        raise ValueError(f"fixture introuvable pour odds: {obs.external_fixture_id}")
    bookmaker, created = BookmakerRepository(session).upsert_bookmaker(
        provider_id,
        obs.bookmaker_external_id,
        obs.bookmaker_name,
        canonical=canonical_key(obs.bookmaker_name),
    )
    counts = {"inserted": 1 if created else 0, "updated": 0 if created else 1, "ignored": 0}
    market, created = MarketRepository(session).get_or_create_market(obs.market_key)
    counts["inserted" if created else "ignored"] += 1
    _, created = MarketRepository(session).get_or_create_selection(
        market.id,
        obs.selection_key,
        obs.selection_key,
        line_value=obs.line_value,
    )
    counts["inserted" if created else "ignored"] += 1
    _, created = OddsSnapshotRepository(session).append_odds_snapshot(
        fixture_id=fixture.id,
        bookmaker_id=bookmaker.id,
        market_id=market.id,
        selection_key=obs.selection_key,
        line_value=obs.line_value,
        decimal_odds=obs.decimal_odds,
        original_odds=obs.original_odds,
        original_format=obs.original_format,
        status=obs.status,
        provider_event_timestamp=obs.provider_timestamp,
        observed_at=obs.observed_at,
        effective_at=obs.observed_at,
        raw_payload_id=raw_payload_id,
        ingestion_run_id=ingestion_run_id,
    )
    counts["inserted" if created else "ignored"] += 1
    return counts


def _merge_counts(target: dict[str, int], source: Mapping[str, int]) -> None:
    for key in ("inserted", "updated", "ignored", "failed"):
        target[key] = int(target.get(key, 0)) + int(source.get(key, 0))


def dry_run_provider_payload(provider_key: str, endpoint: str, payload: Any, observed_at: Any) -> dict[str, Any]:
    report = normalize_provider_payload(provider_key, endpoint, payload, observed_at)
    return {
        "provider": provider_key,
        "endpoint": endpoint,
        "dry_run": True,
        "fixtures": len(report.fixtures),
        "odds": len(report.odds),
        "errors": report.errors,
        "warnings": report.warnings,
        "applied": False,
        "lab_only": True,
        "can_influence_picks": False,
    }


def apply_provider_payload(
    session: Session,
    provider_key: str,
    endpoint: str,
    payload: Any,
    observed_at: Any,
    source: str = "replay",
    request_parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    observed_at_dt = parse_utc(observed_at, "observed_at")
    defaults = _provider_defaults(provider_key)
    provider, provider_created = ProviderRepository(session).get_or_create_provider(
        provider_key,
        defaults["name"],
        defaults["provider_type"],
        base_url=defaults["base_url"],
    )
    ensure_default_markets(session)
    run = IngestionRunRepository(session).start_run(
        "provider_replay",
        source,
        parameters={"provider": provider_key, "endpoint": endpoint, **dict(request_parameters or {})},
        code_version=VERSION,
    )
    raw, raw_created = RawPayloadRepository(session).store_raw_payload(
        provider.id,
        endpoint,
        payload,
        fetched_at=observed_at_dt,
        request_parameters=request_parameters,
        http_status=200,
        ingestion_run_id=run.id,
    )
    report = normalize_provider_payload(provider_key, endpoint, payload, observed_at_dt, raw_payload_id=raw.id)
    counts = {
        "provider_created": int(provider_created),
        "raw_payload_created": int(raw_created),
        "inserted": int(provider_created) + int(raw_created),
        "updated": 0,
        "ignored": 0,
        "failed": 0,
    }
    for fixture_obs in report.fixtures:
        try:
            _merge_counts(counts, _apply_fixture(session, provider.id, fixture_obs, raw.id))
        except Exception as exc:
            counts["failed"] += 1
            report.errors.append(f"fixture_apply:{fixture_obs.external_fixture_id}:{exc}")
    for odds_obs in report.odds:
        try:
            _merge_counts(counts, _apply_odds(session, provider.id, odds_obs, raw.id, run.id))
        except Exception as exc:
            counts["failed"] += 1
            report.errors.append(f"odds_apply:{odds_obs.external_fixture_id}:{exc}")
    status = "completed" if not report.errors else "completed_with_errors"
    IngestionRunRepository(session).finish_run(
        run,
        status=status,
        records_received=len(report.fixtures) + len(report.odds),
        inserted=counts["inserted"],
        updated=counts["updated"],
        ignored=counts["ignored"],
        failed=counts["failed"],
        error_summary="; ".join(report.errors)[:500] if report.errors else None,
    )
    return {
        "provider": provider_key,
        "endpoint": endpoint,
        "dry_run": False,
        "applied": True,
        "ingestion_run_id": run.id,
        "raw_payload_id": raw.id,
        "fixtures": len(report.fixtures),
        "odds": len(report.odds),
        "errors": report.errors,
        "warnings": report.warnings,
        **counts,
        "lab_only": True,
        "can_influence_picks": False,
    }


def replay_provider_file(
    session: Session | None,
    file_path: str,
    provider_key: str,
    observed_at: Any | None = None,
    endpoint: str | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    payload = load_json_limited(file_path)
    endpoint = endpoint or infer_endpoint(provider_key, payload)
    observed_at = observed_at or utc_now()
    if not apply:
        return dry_run_provider_payload(provider_key, endpoint, payload, observed_at)
    if session is None:
        raise ValueError("session requise pour --apply")
    return apply_provider_payload(session, provider_key, endpoint, payload, observed_at, source=file_path)


def replay_run(session: Session, run_id: str) -> dict[str, Any]:
    raw_payloads = RawPayloadRepository(session).list_by_run(run_id)
    summary = {"run_id": run_id, "raw_payloads": len(raw_payloads), "applied": True, "inserted": 0, "updated": 0, "ignored": 0, "failed": 0, "errors": []}
    for raw in raw_payloads:
        provider = session.get(Provider, raw.provider_id)
        if provider is None:
            summary["failed"] += 1
            summary["errors"].append(f"provider introuvable pour raw payload {raw.id}")
            continue
        provider_key = provider.key
        report = apply_provider_payload(session, provider_key, raw.endpoint, raw.payload_json, raw.fetched_at, source=f"stored_run:{run_id}")
        for key in ("inserted", "updated", "ignored", "failed"):
            summary[key] += int(report.get(key) or 0)
        summary["errors"].extend(report.get("errors") or [])
    return summary
