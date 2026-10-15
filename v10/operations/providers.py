from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from v10.time import ensure_utc, utc_now


class FixtureProvider(Protocol):
    def discover_fixtures(self, start: datetime, end: datetime) -> list[dict[str, Any]]: ...
    def refresh_fixture(self, fixture_id: str) -> dict[str, Any]: ...


class OddsProvider(Protocol):
    def refresh_odds(self, fixture_id: str, observed_at: datetime) -> list[dict[str, Any]]: ...


class ResultsProvider(Protocol):
    def refresh_results(self, fixture_id: str) -> dict[str, Any]: ...


class TeamStatisticsProvider(Protocol):
    def refresh_team_statistics(self, fixture_id: str) -> dict[str, Any]: ...


class StandingsProvider(Protocol):
    def refresh_standings(self, competition_id: str) -> dict[str, Any]: ...


class PlayerAvailabilityProvider(Protocol):
    def refresh_availability(self, fixture_id: str) -> dict[str, Any]: ...


class LineupProvider(Protocol):
    def refresh_lineups(self, fixture_id: str) -> dict[str, Any]: ...


@dataclass
class MockPrematchProvider:
    provider_key: str = "mock_provider"
    base_time: datetime | None = None
    unavailable: bool = False
    quota_remaining: int | None = 500

    def _now(self) -> datetime:
        return ensure_utc(self.base_time or utc_now())

    def discover_fixtures(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        if self.unavailable:
            raise TimeoutError("mock provider unavailable")
        start = ensure_utc(start, "start")
        return [
            {
                "fixture_id": "fixture_demo",
                "external_id": "mock-001",
                "competition": "Synthetic League",
                "home_team": "North FC",
                "away_team": "Metro FC",
                "event_time": (start + timedelta(days=1)).isoformat(),
                "status": "SCHEDULED",
                "observed_at": self._now().isoformat(),
            }
        ]

    def refresh_fixture(self, fixture_id: str) -> dict[str, Any]:
        return {"fixture_id": fixture_id, "status": "SCHEDULED", "event_time": (self._now() + timedelta(hours=24)).isoformat(), "observed_at": self._now().isoformat()}

    def refresh_odds(self, fixture_id: str, observed_at: datetime) -> list[dict[str, Any]]:
        observed_at = ensure_utc(observed_at, "observed_at")
        return [
            {"id": f"{fixture_id}:home:{observed_at.timestamp()}", "fixture_id": fixture_id, "selection": "home", "decimal_odds": "2.20", "bookmaker": "MockBook A", "observed_at": observed_at.isoformat(), "bookmaker_count": 3},
            {"id": f"{fixture_id}:draw:{observed_at.timestamp()}", "fixture_id": fixture_id, "selection": "draw", "decimal_odds": "3.40", "bookmaker": "MockBook A", "observed_at": observed_at.isoformat(), "bookmaker_count": 3},
            {"id": f"{fixture_id}:away:{observed_at.timestamp()}", "fixture_id": fixture_id, "selection": "away", "decimal_odds": "3.10", "bookmaker": "MockBook A", "observed_at": observed_at.isoformat(), "bookmaker_count": 3},
        ]

    def refresh_results(self, fixture_id: str) -> dict[str, Any]:
        return {"fixture_id": fixture_id, "status": "FT", "home_goals": 2, "away_goals": 1, "observed_at": self._now().isoformat()}

    def refresh_team_statistics(self, fixture_id: str) -> dict[str, Any]:
        return {"fixture_id": fixture_id, "available": True, "observed_at": self._now().isoformat()}

    def refresh_standings(self, competition_id: str) -> dict[str, Any]:
        return {"competition_id": competition_id, "available": True, "observed_at": self._now().isoformat()}

    def refresh_availability(self, fixture_id: str) -> dict[str, Any]:
        return {"fixture_id": fixture_id, "available": False, "observed_at": self._now().isoformat(), "reason": "mock_no_structured_provider"}

    def refresh_lineups(self, fixture_id: str) -> dict[str, Any]:
        return {"fixture_id": fixture_id, "confirmed": True, "observed_at": self._now().isoformat()}

