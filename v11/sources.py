"""Bounded provider calls, using the existing V10 persistent cache and quota log."""
from __future__ import annotations

from datetime import datetime

import httpx
from sqlalchemy import select

from api_football_fixtures_adapter import normalize_fixtures_payload
from v10.db.models import ProviderQuotaUsage
from v10.normalization.the_odds_api import normalize_odds_payload
from v10.operations.provider_cache import ProviderCache, provider_cache_key
from v10.operations.quota import ProviderQuotaManager
from v10.time import ensure_utc
from v11.contracts import Fixture, Quote, Snapshot


REQUESTED_BOOKMAKERS = ("Betclic France", "Winamax", "Unibet", "PMU", "NetBet")
FR_BOOKMAKER_KEYS = {"Betclic France": "betclic_fr", "Winamax": "winamax_fr", "Unibet": "unibet_fr",
                     "PMU": "pmu_fr", "NetBet": "netbet_fr"}


class SourceError(RuntimeError):
    pass


class Collector:
    def __init__(self, session, keys: dict[str, str], allow_network: bool = False,
                 max_calls: int = 2, transport=None):
        if not 0 <= max_calls <= 5:
            raise ValueError("max_calls must be between 0 and 5")
        self.session, self.keys = session, keys
        self.allow_network, self.max_calls = allow_network, max_calls
        self.calls = 0
        self.transport = transport
        self.cache = ProviderCache(session)
        self.quota = ProviderQuotaManager()

    def fetch(self, provider: str, parameters: dict, now: datetime) -> dict:
        from v10.db.locks import AdvisoryLockManager
        with AdvisoryLockManager(self.session, f"v11-collector:{provider}"):
            return self._fetch(provider, parameters, now)

    def _fetch(self, provider: str, parameters: dict, now: datetime) -> dict:
        ensure_utc(now)
        if provider not in {"api_football", "the_odds_api"}:
            raise ValueError("unknown provider")
        if provider == "api_football":
            if set(parameters) != {"date"}:
                raise ValueError("API-Football fixture collection requires date only")
            from datetime import date
            date.fromisoformat(parameters["date"])
            url, endpoint = "https://v3.football.api-sports.io/fixtures", "fixtures"
            expected_cost = 1
        else:
            sport = parameters.get("sport", "")
            if set(parameters) != {"sport"} or not sport.startswith("soccer_") or not all(c.isalnum() or c == "_" for c in sport):
                raise ValueError("explicit soccer sport key required")
            url, endpoint = f"https://api.the-odds-api.com/v4/sports/{sport}/odds", "odds"
            expected_cost = 1
        key = provider_cache_key(provider, endpoint, parameters)
        cached = self.cache.get(key, now)
        if cached and not cached["stale"]:
            return {**cached["response"], "cache_hit": True}
        if not self.allow_network or not self.keys.get(provider):
            raise SourceError("network_disabled_or_key_missing")
        if self.calls >= self.max_calls:
            raise SourceError("per_run_request_limit")
        previous = self.session.scalar(select(ProviderQuotaUsage).where(
            ProviderQuotaUsage.provider_key == provider).order_by(ProviderQuotaUsage.observed_at.desc()).limit(1))
        remaining = previous.estimated_remaining_quota if previous else None
        if remaining is not None and remaining < expected_cost:
            raise SourceError("quota_exhausted")
        if not self.quota.allow_request(remaining, "background_refresh").allowed:
            raise SourceError("quota_reserved_for_critical_operations")
        query = {"date": parameters["date"]} if provider == "api_football" else {
            "apiKey": self.keys[provider], "bookmakers": ",".join(FR_BOOKMAKER_KEYS.values()),
            "markets": "h2h", "oddsFormat": "decimal"}
        headers = {"x-apisports-key": self.keys[provider]} if provider == "api_football" else {}
        self.calls += 1
        safe_headers = {"x-requests-remaining": str(max(remaining-expected_cost, 0))} if remaining is not None else {}
        try:
            # No retries, no redirect following, no exception URL containing a key.
            with httpx.Client(transport=self.transport, timeout=20, follow_redirects=False) as client:
                response = client.get(url, params=query, headers=headers)
            safe_headers.update({k: v for k, v in response.headers.items() if k.lower() in {
                "x-requests-remaining", "x-requests-used", "x-requests-last", "x-ratelimit-remaining",
                "x-ratelimit-requests-remaining"}})
            if "x-ratelimit-requests-remaining" in safe_headers:
                safe_headers["x-ratelimit-remaining"] = safe_headers["x-ratelimit-requests-remaining"]
            if response.status_code != 200:
                self.quota.record_headers(self.session, provider, endpoint, safe_headers, failures=1, observed_at=now)
                raise SourceError(f"provider_http_{response.status_code}")
            payload = response.json()
            if provider == "api_football" and (not isinstance(payload, dict) or payload.get("errors")):
                self.quota.record_headers(self.session, provider, endpoint, safe_headers, failures=1, observed_at=now)
                raise SourceError("provider_payload_errors")
            if provider == "the_odds_api" and not isinstance(payload, list):
                self.quota.record_headers(self.session, provider, endpoint, safe_headers, failures=1, observed_at=now)
                raise SourceError("provider_payload_not_event_list")
        except (httpx.HTTPError, ValueError):
            self.quota.record_headers(self.session, provider, endpoint, safe_headers, failures=1, observed_at=now)
            raise SourceError("provider_transport_or_json_error") from None
        self.quota.record_headers(self.session, provider, endpoint, safe_headers, observed_at=now)
        result = {"provider": provider, "payload": payload, "fetched_at": now.isoformat(),
                  "quota_headers": safe_headers, "cache_hit": False}
        self.cache.put(provider, endpoint, parameters, result, phase="T10", now=now)
        return result


def odds_snapshot(payload: list, observed_at: datetime, provenance: str = "real_provider") -> Snapshot:
    """Reuse V10 canonical normalization, preserving source IDs and bookmaker clocks."""
    from copy import deepcopy
    from v10.time import parse_utc
    normalized_input = deepcopy(payload)
    if not isinstance(normalized_input, list):
        raise ValueError("event list required")
    for event in normalized_input:
        if not isinstance(event, dict):
            raise ValueError("event object required")
        for bookmaker in event.get("bookmakers") or []:
            if not isinstance(bookmaker, dict):
                raise ValueError("bookmaker object required")
            book_time = bookmaker.pop("last_update", None)
            for market in bookmaker.get("markets") or []:
                if not isinstance(market, dict):
                    raise ValueError("market object required")
                clocks = [parse_utc(t) for t in (book_time, market.get("last_update")) if t]
                market["last_update"] = min(clocks).isoformat() if clocks else None
    report = normalize_odds_payload(normalized_input, observed_at)
    if report.errors:
        raise ValueError("odds normalization rejected payload: " + "; ".join(report.errors[:3]))
    fixtures = []
    for f in report.fixtures:
        if not f.external_fixture_id or f.home_team_name == "home_unknown" or f.away_team_name == "away_unknown":
            raise ValueError("source fixture id and named teams required")
        quotes = [Quote(source=q.provider_key, bookmaker=q.bookmaker_external_id or q.bookmaker_name,
                        market=q.market_key, selection=q.selection_key, odds=float(q.decimal_odds),
                        line=float(q.line_value) if q.line_value is not None else None,
                        observed_at=q.observed_at, provider_updated_at=q.provider_timestamp)
                  for q in report.odds if q.external_fixture_id == f.external_fixture_id]
        fixtures.append(Fixture(fixture_id=f"the_odds_api:{f.external_fixture_id}", source=f.provider_key,
                                competition=f.external_competition_id, home=f.home_team_name,
                                away=f.away_team_name, kickoff=f.event_time, observed_at=f.observed_at, quotes=quotes))
    return Snapshot(captured_at=observed_at, provenance=provenance, fixtures=fixtures)


def football_fixtures(payload: dict) -> list[dict]:
    if payload.get("errors"):
        raise ValueError("API-Football errors present")
    rows = normalize_fixtures_payload(payload)
    if any(row["validation_status"] != "valid" for row in rows):
        raise ValueError("invalid API-Football fixture")
    return rows


def coverage(snapshot: Snapshot) -> dict:
    observed = sorted({q.bookmaker for f in snapshot.fixtures for q in f.quotes})
    return {"provenance": snapshot.provenance, "observed_bookmaker_keys": observed,
            "observed_markets": sorted({q.market for f in snapshot.fixtures for q in f.quotes}),
            "requested_bookmakers": list(REQUESTED_BOOKMAKERS),
            "coverage_by_requested_bookmaker": {name: {"key": key, "observed": key in observed}
                                                for name, key in FR_BOOKMAKER_KEYS.items()},
            "france_account_coverage": "unverified",
            "note": "An EU key or display name does not prove a French bookmaker account or all its markets."}
