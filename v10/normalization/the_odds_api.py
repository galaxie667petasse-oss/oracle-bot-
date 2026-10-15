from decimal import Decimal
from typing import Any, Mapping

from .schemas import CanonicalFixtureObservation, CanonicalOddsObservation, NormalizationReport


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or default


def _market_key(value: str) -> str | None:
    mapping = {"h2h": "match_winner", "totals": "total_goals", "btts": "both_teams_to_score"}
    return mapping.get(value.strip().lower())


def _selection(market_key: str, outcome: Mapping[str, Any], home: str, away: str) -> tuple[str | None, Decimal | None]:
    name = _text(outcome.get("name")).lower()
    if market_key == "match_winner":
        if name == home.lower():
            return "home", None
        if name == away.lower():
            return "away", None
        if name == "draw":
            return "draw", None
    if market_key == "total_goals":
        point = outcome.get("point")
        if name == "over":
            return "over", Decimal(str(point))
        if name == "under":
            return "under", Decimal(str(point))
    if market_key == "both_teams_to_score":
        if name == "yes":
            return "yes", None
        if name == "no":
            return "no", None
    return None, None


def normalize_odds_payload(payload: Any, observed_at: Any, raw_payload_id: str | None = None) -> NormalizationReport:
    response = payload if isinstance(payload, list) else payload.get("response") if isinstance(payload, Mapping) else None
    if not isinstance(response, list):
        return NormalizationReport(provider_key="the_odds_api", endpoint="odds", errors=["event list missing"])
    fixtures = []
    odds = []
    errors = []
    warnings = []
    for event_index, event in enumerate(response):
        try:
            event_id = _text(event.get("id"))
            home = _text(event.get("home_team"), "home_unknown")
            away = _text(event.get("away_team"), "away_unknown")
            sport_key = _text(event.get("sport_key") or event.get("sport_title"), "competition_unknown")
            warnings.append("team_external_id_missing_text_fallback")
            fixtures.append(
                CanonicalFixtureObservation(
                    provider_key="the_odds_api",
                    external_fixture_id=event_id,
                    external_competition_id=sport_key,
                    competition_name=_text(event.get("sport_title"), sport_key),
                    country=None,
                    season_external_id=None,
                    season_name=None,
                    home_team_external_id=home,
                    away_team_external_id=away,
                    home_team_name=home,
                    away_team_name=away,
                    event_time=event.get("commence_time"),
                    canonical_status="SCHEDULED",
                    provider_status="commence_time",
                    observed_at=observed_at,
                    metadata={"sport_key": sport_key},
                    warnings=["team_external_id_missing_text_fallback"],
                )
            )
            for bookmaker in event.get("bookmakers") or []:
                bookmaker_name = _text(bookmaker.get("title") or bookmaker.get("key"), "bookmaker_unknown")
                bookmaker_external_id = _text(bookmaker.get("key")) or bookmaker_name
                for market in bookmaker.get("markets") or []:
                    market_key = _market_key(_text(market.get("key")))
                    if not market_key:
                        warnings.append(f"unsupported_market:{_text(market.get('key'))}")
                        continue
                    for outcome in market.get("outcomes") or []:
                        try:
                            selection_key, line_value = _selection(market_key, outcome, home, away)
                            if not selection_key:
                                raise ValueError(f"unsupported selection {outcome.get('name')}")
                            odds.append(
                                CanonicalOddsObservation(
                                    provider_key="the_odds_api",
                                    external_fixture_id=event_id,
                                    bookmaker_external_id=bookmaker_external_id,
                                    bookmaker_name=bookmaker_name,
                                    market_key=market_key,
                                    selection_key=selection_key,
                                    line_value=line_value,
                                    decimal_odds=outcome.get("price"),
                                    original_odds=_text(outcome.get("price")),
                                    original_format="decimal",
                                    provider_timestamp=bookmaker.get("last_update") or market.get("last_update"),
                                    observed_at=observed_at,
                                    raw_payload_id=raw_payload_id,
                                    warnings=[],
                                )
                            )
                        except Exception as exc:
                            errors.append(f"odds[{event_index}]: {exc}")
        except Exception as exc:
            errors.append(f"event[{event_index}]: {exc}")
    return NormalizationReport(provider_key="the_odds_api", endpoint="odds", fixtures=fixtures, odds=odds, errors=errors, warnings=warnings)

