import json
import re
from datetime import datetime
from decimal import Decimal
from statistics import mean, median
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from v10.hashing import content_hash, odds_snapshot_fingerprint, request_fingerprint
from v10.odds import proportional_no_vig
from v10.time import ensure_utc, utc_now

from .models import (
    Bookmaker,
    Competition,
    Fixture,
    FixtureStatusHistory,
    IngestionRun,
    Market,
    MarketSelection,
    NormalizedMarketSnapshot,
    OddsSnapshot,
    Provider,
    RawApiPayload,
    Season,
    Team,
)


MARKET_DEFINITIONS = {
    "match_winner": {"name": "Match Winner", "selection_count": 3, "settlement_handler": "match_winner"},
    "double_chance": {"name": "Double Chance", "selection_count": 3, "settlement_handler": "double_chance"},
    "draw_no_bet": {"name": "Draw No Bet", "selection_count": 2, "settlement_handler": "draw_no_bet"},
    "total_goals": {"name": "Total Goals", "selection_count": 2, "settlement_handler": "total_goals"},
    "both_teams_to_score": {"name": "Both Teams To Score", "selection_count": 2, "settlement_handler": "both_teams_to_score"},
}


def canonical_key(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def _json_size(payload: Any) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class ProviderRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_key(self, key: str) -> Provider | None:
        return self.session.scalar(select(Provider).where(Provider.key == key))

    def get_or_create_provider(
        self,
        key: str,
        name: str,
        provider_type: str,
        base_url: str | None = None,
        is_active: bool = True,
    ) -> tuple[Provider, bool]:
        existing = self.get_by_key(key)
        if existing:
            return existing, False
        provider = Provider(key=key, name=name, provider_type=provider_type, base_url=base_url, is_active=is_active)
        self.session.add(provider)
        try:
            self.session.flush()
            return provider, True
        except IntegrityError:
            self.session.rollback()
            existing = self.get_by_key(key)
            if existing:
                return existing, False
            raise


class CompetitionRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_competition(
        self,
        provider_id: str,
        external_id: str,
        name: str,
        country: str | None = None,
        competition_type: str | None = None,
        level: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Competition, bool]:
        stmt = select(Competition).where(Competition.provider_id == provider_id, Competition.external_id == str(external_id))
        existing = self.session.scalar(stmt)
        if existing:
            existing.name = name or existing.name
            existing.country = country
            existing.competition_type = competition_type
            existing.level = level
            existing.metadata_json = dict(metadata or existing.metadata_json or {})
            return existing, False
        row = Competition(
            provider_id=provider_id,
            external_id=str(external_id),
            name=name,
            country=country,
            competition_type=competition_type,
            level=level,
            metadata_json=dict(metadata or {}),
        )
        self.session.add(row)
        self.session.flush()
        return row, True


class SeasonRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_season(
        self,
        competition_id: str,
        external_id: str,
        start_year: int | None = None,
        end_year: int | None = None,
        name: str | None = None,
        status: str | None = None,
    ) -> tuple[Season, bool]:
        stmt = select(Season).where(Season.competition_id == competition_id, Season.external_id == str(external_id))
        existing = self.session.scalar(stmt)
        if existing:
            existing.start_year = start_year
            existing.end_year = end_year
            existing.name = name
            existing.status = status
            return existing, False
        row = Season(
            competition_id=competition_id,
            external_id=str(external_id),
            start_year=start_year,
            end_year=end_year,
            name=name,
            status=status,
        )
        self.session.add(row)
        self.session.flush()
        return row, True


class TeamRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_team(
        self,
        provider_id: str,
        external_id: str,
        name: str,
        country: str | None = None,
        code: str | None = None,
        logo_url: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Team, bool]:
        stmt = select(Team).where(Team.provider_id == provider_id, Team.external_id == str(external_id))
        existing = self.session.scalar(stmt)
        if existing:
            existing.name = name or existing.name
            existing.country = country
            existing.code = code
            existing.logo_url = logo_url
            existing.metadata_json = dict(metadata or existing.metadata_json or {})
            return existing, False
        row = Team(
            provider_id=provider_id,
            external_id=str(external_id),
            name=name,
            country=country,
            code=code,
            logo_url=logo_url,
            metadata_json=dict(metadata or {}),
        )
        self.session.add(row)
        self.session.flush()
        return row, True


class FixtureRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, fixture_id: str) -> Fixture | None:
        return self.session.get(Fixture, fixture_id)

    def get_by_external(self, provider_id: str, external_id: str) -> Fixture | None:
        return self.session.scalar(select(Fixture).where(Fixture.provider_id == provider_id, Fixture.external_id == str(external_id)))

    def upsert_fixture(
        self,
        provider_id: str,
        external_id: str,
        competition_id: str,
        home_team_id: str,
        away_team_id: str,
        event_time: datetime,
        canonical_status: str,
        provider_status: str | None,
        observed_at: datetime,
        season_id: str | None = None,
        venue: str | None = None,
        round_name: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[Fixture, bool]:
        event_time = ensure_utc(event_time, "event_time")
        observed_at = ensure_utc(observed_at, "observed_at")
        existing = self.get_by_external(provider_id, str(external_id))
        if existing:
            incoming_has_status = canonical_status != "UNKNOWN" or str(provider_status or "").strip().upper() not in ("", "UNKNOWN")
            existing.competition_id = competition_id
            existing.season_id = season_id
            existing.home_team_id = home_team_id
            existing.away_team_id = away_team_id
            existing.event_time = event_time
            if incoming_has_status:
                existing.canonical_status = canonical_status
                existing.provider_status = provider_status
            existing.venue = venue
            existing.round_name = round_name
            existing.last_observed_at = max(ensure_utc(existing.last_observed_at), observed_at)
            existing.metadata_json = dict(metadata or existing.metadata_json or {})
            return existing, False
        row = Fixture(
            provider_id=provider_id,
            external_id=str(external_id),
            competition_id=competition_id,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            event_time=event_time,
            canonical_status=canonical_status,
            provider_status=provider_status,
            venue=venue,
            round_name=round_name,
            initial_observed_at=observed_at,
            last_observed_at=observed_at,
            metadata_json=dict(metadata or {}),
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def append_fixture_status(
        self,
        fixture_id: str,
        canonical_status: str,
        provider_status: str | None,
        observed_at: datetime,
        raw_payload_id: str | None = None,
    ) -> tuple[FixtureStatusHistory, bool]:
        observed_at = ensure_utc(observed_at, "observed_at")
        stmt = select(FixtureStatusHistory).where(
            FixtureStatusHistory.fixture_id == fixture_id,
            FixtureStatusHistory.canonical_status == canonical_status,
            FixtureStatusHistory.provider_status == provider_status,
            FixtureStatusHistory.observed_at == observed_at,
        )
        existing = self.session.scalar(stmt)
        if existing:
            return existing, False
        row = FixtureStatusHistory(
            fixture_id=fixture_id,
            canonical_status=canonical_status,
            provider_status=provider_status,
            observed_at=observed_at,
            raw_payload_id=raw_payload_id,
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def get_fixture_state_as_of(self, fixture_id: str, as_of: datetime) -> dict[str, Any] | None:
        as_of = ensure_utc(as_of, "as_of")
        fixture = self.get_by_id(fixture_id)
        if not fixture or ensure_utc(fixture.initial_observed_at) > as_of:
            return None
        status = self.session.scalar(
            select(FixtureStatusHistory)
            .where(FixtureStatusHistory.fixture_id == fixture_id, FixtureStatusHistory.observed_at <= as_of)
            .order_by(FixtureStatusHistory.observed_at.desc())
        )
        return {
            "fixture_id": fixture.id,
            "external_id": fixture.external_id,
            "event_time": ensure_utc(fixture.event_time),
            "canonical_status": status.canonical_status if status else fixture.canonical_status,
            "provider_status": status.provider_status if status else fixture.provider_status,
            "as_of": as_of,
        }


class BookmakerRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_bookmaker(
        self,
        provider_id: str,
        external_id: str | None,
        name: str,
        canonical: str | None = None,
    ) -> tuple[Bookmaker, bool]:
        external_id = str(external_id or canonical_key(name))
        canonical = canonical or canonical_key(name)
        stmt = select(Bookmaker).where(Bookmaker.provider_id == provider_id, Bookmaker.external_id == external_id)
        existing = self.session.scalar(stmt)
        if existing:
            existing.name = name or existing.name
            existing.canonical_key = canonical
            return existing, False
        row = Bookmaker(provider_id=provider_id, external_id=external_id, name=name, canonical_key=canonical)
        self.session.add(row)
        self.session.flush()
        return row, True


class MarketRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create_market(self, key: str, name: str | None = None, settlement_handler: str | None = None, selection_count: int | None = None) -> tuple[Market, bool]:
        key = canonical_key(key)
        existing = self.session.scalar(select(Market).where(Market.key == key))
        if existing:
            return existing, False
        definition = MARKET_DEFINITIONS.get(key, {})
        row = Market(
            key=key,
            name=name or definition.get("name") or key,
            selection_count=selection_count if selection_count is not None else definition.get("selection_count"),
            settlement_handler=settlement_handler or definition.get("settlement_handler") or key,
            parameters_json={},
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def get_or_create_selection(
        self,
        market_id: str,
        selection_key: str,
        label: str,
        line_value: Decimal | None = None,
        handicap_value: Decimal | None = None,
    ) -> tuple[MarketSelection, bool]:
        stmt = select(MarketSelection).where(
            MarketSelection.market_id == market_id,
            MarketSelection.selection_key == selection_key,
            MarketSelection.line_value == line_value,
            MarketSelection.handicap_value == handicap_value,
        )
        existing = self.session.scalar(stmt)
        if existing:
            return existing, False
        row = MarketSelection(
            market_id=market_id,
            selection_key=selection_key,
            label=label,
            line_value=line_value,
            handicap_value=handicap_value,
        )
        self.session.add(row)
        self.session.flush()
        return row, True


class IngestionRunRepository:
    def __init__(self, session: Session):
        self.session = session

    def start_run(self, run_type: str, source: str, parameters: Mapping[str, Any] | None = None, code_version: str | None = None) -> IngestionRun:
        row = IngestionRun(
            run_type=run_type,
            source=source,
            parameters_json=dict(parameters or {}),
            started_at=utc_now(),
            status="running",
            code_version=code_version,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def finish_run(
        self,
        run: IngestionRun,
        status: str,
        records_received: int = 0,
        inserted: int = 0,
        updated: int = 0,
        ignored: int = 0,
        failed: int = 0,
        error_summary: str | None = None,
    ) -> IngestionRun:
        run.finished_at = utc_now()
        run.status = status
        run.records_received = records_received
        run.inserted = inserted
        run.updated = updated
        run.ignored = ignored
        run.failed = failed
        run.error_summary = error_summary
        self.session.flush()
        return run


class RawPayloadRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_raw_payload_by_hash(self, provider_id: str, endpoint: str, req_fingerprint: str, payload_hash: str) -> RawApiPayload | None:
        return self.session.scalar(
            select(RawApiPayload).where(
                RawApiPayload.provider_id == provider_id,
                RawApiPayload.endpoint == endpoint,
                RawApiPayload.request_fingerprint == req_fingerprint,
                RawApiPayload.content_hash == payload_hash,
            )
        )

    def store_raw_payload(
        self,
        provider_id: str,
        endpoint: str,
        payload: Any,
        fetched_at: datetime,
        request_parameters: Mapping[str, Any] | None = None,
        http_status: int | None = None,
        provider_request_id: str | None = None,
        ingestion_run_id: str | None = None,
    ) -> tuple[RawApiPayload, bool]:
        fetched_at = ensure_utc(fetched_at, "fetched_at")
        request_parameters = dict(request_parameters or {})
        req_fp = request_fingerprint(provider_id, endpoint, request_parameters)
        payload_hash = content_hash(payload)
        existing = self.find_raw_payload_by_hash(provider_id, endpoint, req_fp, payload_hash)
        if existing:
            return existing, False
        row = RawApiPayload(
            provider_id=provider_id,
            ingestion_run_id=ingestion_run_id,
            endpoint=endpoint,
            request_fingerprint=req_fp,
            request_parameters_json=request_parameters,
            http_status=http_status,
            provider_request_id=provider_request_id,
            fetched_at=fetched_at,
            content_hash=payload_hash,
            payload_json=payload,
            payload_size=_json_size(payload),
            schema_version="1.0",
            processing_status="stored",
        )
        self.session.add(row)
        try:
            self.session.flush()
            return row, True
        except IntegrityError:
            self.session.rollback()
            existing = self.find_raw_payload_by_hash(provider_id, endpoint, req_fp, payload_hash)
            if existing:
                return existing, False
            raise

    def get_raw_payloads_observed_before(self, as_of: datetime) -> list[RawApiPayload]:
        as_of = ensure_utc(as_of, "as_of")
        return list(self.session.scalars(select(RawApiPayload).where(RawApiPayload.fetched_at <= as_of).order_by(RawApiPayload.fetched_at)))

    def list_by_run(self, run_id: str) -> list[RawApiPayload]:
        return list(self.session.scalars(select(RawApiPayload).where(RawApiPayload.ingestion_run_id == run_id).order_by(RawApiPayload.fetched_at)))


class OddsSnapshotRepository:
    def __init__(self, session: Session):
        self.session = session

    def append_odds_snapshot(
        self,
        fixture_id: str,
        bookmaker_id: str,
        market_id: str,
        selection_key: str,
        decimal_odds: Decimal,
        original_odds: str,
        observed_at: datetime,
        effective_at: datetime | None = None,
        original_format: str = "decimal",
        line_value: Decimal | None = None,
        status: str = "active",
        provider_event_timestamp: datetime | None = None,
        raw_payload_id: str | None = None,
        ingestion_run_id: str | None = None,
    ) -> tuple[OddsSnapshot, bool]:
        observed_at = ensure_utc(observed_at, "observed_at")
        effective_at = ensure_utc(effective_at or observed_at, "effective_at")
        if provider_event_timestamp is not None:
            provider_event_timestamp = ensure_utc(provider_event_timestamp, "provider_event_timestamp")
        decimal_odds = Decimal(str(decimal_odds))
        if decimal_odds <= Decimal("1"):
            raise ValueError("decimal_odds must be > 1")
        fingerprint = odds_snapshot_fingerprint(
            fixture_id,
            bookmaker_id,
            market_id,
            selection_key,
            line_value,
            decimal_odds,
            observed_at,
            provider_event_timestamp,
        )
        existing = self.session.scalar(select(OddsSnapshot).where(OddsSnapshot.content_fingerprint == fingerprint))
        if existing:
            return existing, False
        row = OddsSnapshot(
            fixture_id=fixture_id,
            bookmaker_id=bookmaker_id,
            market_id=market_id,
            selection_key=selection_key,
            line_value=line_value,
            decimal_odds=decimal_odds,
            original_odds=str(original_odds),
            original_format=original_format,
            status=status,
            provider_event_timestamp=provider_event_timestamp,
            observed_at=observed_at,
            effective_at=effective_at,
            raw_payload_id=raw_payload_id,
            ingestion_run_id=ingestion_run_id,
            content_fingerprint=fingerprint,
        )
        self.session.add(row)
        self.session.flush()
        return row, True

    def list_odds_between(self, fixture_id: str, start: datetime, end: datetime) -> list[OddsSnapshot]:
        start = ensure_utc(start, "start")
        end = ensure_utc(end, "end")
        return list(
            self.session.scalars(
                select(OddsSnapshot)
                .where(OddsSnapshot.fixture_id == fixture_id, OddsSnapshot.observed_at >= start, OddsSnapshot.observed_at <= end)
                .order_by(OddsSnapshot.observed_at, OddsSnapshot.created_at)
            )
        )

    def list_fixture_odds_at(self, fixture_id: str, as_of: datetime) -> list[OddsSnapshot]:
        as_of = ensure_utc(as_of, "as_of")
        return list(
            self.session.scalars(
                select(OddsSnapshot)
                .where(OddsSnapshot.fixture_id == fixture_id, OddsSnapshot.observed_at <= as_of)
                .order_by(OddsSnapshot.observed_at, OddsSnapshot.created_at)
            )
        )

    def list_latest_fixture_odds(self, fixture_id: str) -> list[OddsSnapshot]:
        return self.get_latest_odds_as_of(fixture_id, "all", utc_now())

    def get_latest_odds_as_of(self, fixture_id: str, market_key: str, as_of: datetime) -> list[OddsSnapshot]:
        as_of = ensure_utc(as_of, "as_of")
        market_ids = None
        if market_key != "all":
            market_ids = [row.id for row in self.session.scalars(select(Market).where(Market.key == market_key))]
        rows = self.list_fixture_odds_at(fixture_id, as_of)
        latest: dict[tuple[str, str, str, str | None], OddsSnapshot] = {}
        for row in rows:
            if market_ids is not None and row.market_id not in market_ids:
                continue
            key = (row.bookmaker_id, row.market_id, row.selection_key, str(row.line_value) if row.line_value is not None else None)
            current = latest.get(key)
            if current is None or row.observed_at > current.observed_at:
                latest[key] = row
        return sorted(latest.values(), key=lambda item: (item.market_id, item.selection_key, item.bookmaker_id))

    def get_market_snapshot_as_of(self, fixture_id: str, market_key: str, as_of: datetime) -> dict[str, Any]:
        rows = self.get_latest_odds_as_of(fixture_id, market_key, as_of)
        grouped: dict[str, list[OddsSnapshot]] = {}
        for row in rows:
            grouped.setdefault(row.selection_key, []).append(row)
        best: dict[str, str] = {}
        med: dict[str, str] = {}
        avg: dict[str, str] = {}
        for selection, items in grouped.items():
            values = [float(item.decimal_odds) for item in items]
            best[selection] = str(max(values))
            med[selection] = str(median(values))
            avg[selection] = str(round(mean(values), 6))
        fair = proportional_no_vig({selection: value for selection, value in best.items()}) if len(best) >= 2 else {}
        return {
            "fixture_id": fixture_id,
            "market_key": market_key,
            "as_of": ensure_utc(as_of, "as_of"),
            "bookmaker_count": len({row.bookmaker_id for row in rows}),
            "best_odds": best,
            "median_odds": med,
            "mean_odds": avg,
            "fair_probabilities": {key: round(value, 8) for key, value in fair.items()},
            "source_odds_snapshot_ids": [row.id for row in rows],
        }


def ensure_default_markets(session: Session) -> dict[str, Market]:
    repo = MarketRepository(session)
    markets = {}
    for key, definition in MARKET_DEFINITIONS.items():
        markets[key], _ = repo.get_or_create_market(
            key,
            name=definition["name"],
            selection_count=definition["selection_count"],
            settlement_handler=definition["settlement_handler"],
        )
    return markets
