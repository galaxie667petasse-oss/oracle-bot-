import re
from decimal import Decimal
from typing import Any, Mapping

from .schemas import CanonicalFixtureObservation, CanonicalOddsObservation, NormalizationReport
from .status import canonical_status


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or default


def _external_id(value: Any, fallback: str, warnings: list[str], field: str) -> str:
    text = _text(value)
    if text:
        return text
    warnings.append(f"{field}_external_id_missing_text_fallback")
    return fallback


def _line_from_value(value: str) -> Decimal | None:
    match = re.search(r"(-?\d+(?:[.,]\d+)?)", value)
    if not match:
        return None
    return Decimal(match.group(1).replace(",", "."))


def _map_bet_name(name: str) -> str | None:
    lower = name.strip().lower()
    if lower in {"match winner", "1x2", "winner"}:
        return "match_winner"
    if "over/under" in lower or lower in {"goals over under", "total goals"}:
        return "total_goals"
    if "both teams" in lower or lower in {"btts", "both teams score"}:
        return "both_teams_to_score"
    if "double chance" in lower:
        return "double_chance"
    return None


def _map_selection(market_key: str, value: str, home: str, away: str) -> tuple[str | None, Decimal | None]:
    lower = value.strip().lower()
    if market_key == "match_winner":
        if lower in {"home", home.strip().lower(), "1"}:
            return "home", None
        if lower in {"draw", "nul", "x"}:
            return "draw", None
        if lower in {"away", away.strip().lower(), "2"}:
            return "away", None
    if market_key == "total_goals":
        if lower.startswith("over"):
            return "over", _line_from_value(lower)
        if lower.startswith("under"):
            return "under", _line_from_value(lower)
    if market_key == "both_teams_to_score":
        if lower in {"yes", "oui"}:
            return "yes", None
        if lower in {"no", "non"}:
            return "no", None
    if market_key == "double_chance":
        normalized = lower.replace(" ", "").replace("/", "")
        mapping = {"1x": "1x", "x2": "x2", "12": "12", "homeordraw": "1x", "draworaway": "x2", "homeoraway": "12"}
        return mapping.get(normalized), None
    return None, None


def normalize_fixtures_payload(payload: Mapping[str, Any], observed_at: Any) -> NormalizationReport:
    report = NormalizationReport(provider_key="api_football", endpoint="fixtures")
    response = payload.get("response") if isinstance(payload, Mapping) else None
    if not isinstance(response, list):
        return report.model_copy(update={"errors": ["response list missing"]})
    fixtures = []
    errors = []
    warnings_all = []
    for index, item in enumerate(response):
        try:
            fixture = item.get("fixture") or {}
            league = item.get("league") or {}
            teams = item.get("teams") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            warnings: list[str] = []
            provider_status = _text((fixture.get("status") or {}).get("short") or (fixture.get("status") or {}).get("long"), "UNKNOWN")
            home_name = _text(home.get("name"), "home_unknown")
            away_name = _text(away.get("name"), "away_unknown")
            obs = CanonicalFixtureObservation(
                provider_key="api_football",
                external_fixture_id=_text(fixture.get("id")),
                external_competition_id=_external_id(league.get("id"), _text(league.get("name"), "competition_unknown"), warnings, "competition"),
                competition_name=_text(league.get("name"), "competition_unknown"),
                country=_text(league.get("country")) or None,
                season_external_id=_text(league.get("season")) or None,
                season_name=_text(league.get("season")) or None,
                home_team_external_id=_external_id(home.get("id"), home_name, warnings, "home_team"),
                away_team_external_id=_external_id(away.get("id"), away_name, warnings, "away_team"),
                home_team_name=home_name,
                away_team_name=away_name,
                event_time=fixture.get("date"),
                canonical_status=canonical_status(provider_status),
                provider_status=provider_status,
                venue=_text((fixture.get("venue") or {}).get("name")) or None,
                round_name=_text(league.get("round")) or _text(item.get("round")) or None,
                observed_at=observed_at,
                metadata={"provider_league": league},
                warnings=warnings,
            )
            fixtures.append(obs)
            warnings_all.extend(warnings)
        except Exception as exc:
            errors.append(f"fixture[{index}]: {exc}")
    return NormalizationReport(provider_key="api_football", endpoint="fixtures", fixtures=fixtures, errors=errors, warnings=warnings_all)


def normalize_odds_payload(payload: Mapping[str, Any], observed_at: Any, raw_payload_id: str | None = None) -> NormalizationReport:
    report = NormalizationReport(provider_key="api_football", endpoint="odds")
    response = payload.get("response") if isinstance(payload, Mapping) else None
    if not isinstance(response, list):
        return report.model_copy(update={"errors": ["response list missing"]})
    fixtures_report = normalize_fixtures_payload(payload, observed_at)
    odds = []
    errors = list(fixtures_report.errors)
    warnings_all = list(fixtures_report.warnings)
    for event_index, item in enumerate(response):
        fixture = item.get("fixture") or {}
        teams = item.get("teams") or {}
        home_name = _text((teams.get("home") or {}).get("name"), "home")
        away_name = _text((teams.get("away") or {}).get("name"), "away")
        external_fixture_id = _text(fixture.get("id"))
        for book_index, bookmaker in enumerate(item.get("bookmakers") or []):
            bookmaker_name = _text(bookmaker.get("name") or bookmaker.get("title"), "bookmaker_unknown")
            bookmaker_external_id = _text(bookmaker.get("id") or bookmaker.get("key")) or bookmaker_name
            for bet_index, bet in enumerate(bookmaker.get("bets") or []):
                market_key = _map_bet_name(_text(bet.get("name")))
                if not market_key:
                    warnings_all.append(f"unsupported_bet:{_text(bet.get('name'))}")
                    continue
                for value_index, value in enumerate(bet.get("values") or []):
                    try:
                        selection_key, line_value = _map_selection(market_key, _text(value.get("value")), home_name, away_name)
                        if not selection_key:
                            raise ValueError(f"unsupported selection {value.get('value')}")
                        odds.append(
                            CanonicalOddsObservation(
                                provider_key="api_football",
                                external_fixture_id=external_fixture_id,
                                bookmaker_external_id=bookmaker_external_id,
                                bookmaker_name=bookmaker_name,
                                market_key=market_key,
                                selection_key=selection_key,
                                line_value=line_value,
                                decimal_odds=value.get("odd"),
                                original_odds=_text(value.get("odd")),
                                original_format="decimal",
                                provider_timestamp=None,
                                observed_at=observed_at,
                                raw_payload_id=raw_payload_id,
                            )
                        )
                    except Exception as exc:
                        errors.append(f"odds[{event_index}/{book_index}/{bet_index}/{value_index}]: {exc}")
    return NormalizationReport(
        provider_key="api_football",
        endpoint="odds",
        fixtures=fixtures_report.fixtures,
        odds=odds,
        errors=errors,
        warnings=warnings_all,
    )

