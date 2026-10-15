from datetime import date
from typing import Any, Mapping, Protocol


class FootballDataProvider(Protocol):
    async def get_fixtures(self, target_date: date) -> list[Mapping[str, Any]]:
        ...

    async def get_teams(self, competition_id: str | None = None) -> list[Mapping[str, Any]]:
        ...

    async def get_standings(self, competition_id: str, season: str) -> Mapping[str, Any]:
        ...

    async def get_team_statistics(self, team_id: str, competition_id: str, season: str) -> Mapping[str, Any]:
        ...

    async def get_head_to_head(self, home_team_id: str, away_team_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_injuries(self, fixture_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_lineups(self, fixture_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_results(self, target_date: date) -> list[Mapping[str, Any]]:
        ...


class OddsProvider(Protocol):
    async def get_pre_match_odds(self, fixture_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_live_odds(self, fixture_id: str) -> list[Mapping[str, Any]]:
        ...

    async def get_historical_odds(self, fixture_id: str) -> list[Mapping[str, Any]]:
        ...

