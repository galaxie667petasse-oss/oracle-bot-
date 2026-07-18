from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from v10.hashing import content_hash

from .features import TemporalFeatureGenerator
from .types import DatasetRow, HistoricalMatch


@dataclass(frozen=True)
class DatasetBuildReport:
    rows_seen: int
    rows_included: int
    rows_excluded: int
    competitions: list[str]
    min_date: str | None
    max_date: str | None
    dataset_fingerprint: str
    warnings: list[str]
    dry_run: bool
    lab_only: bool = True
    can_influence_picks: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


class TemporalDatasetBuilder:
    def __init__(self, min_history_matches: int = 0):
        self.min_history_matches = min_history_matches

    def build(self, matches: Iterable[HistoricalMatch], start: datetime | None = None, end: datetime | None = None) -> tuple[list[DatasetRow], DatasetBuildReport]:
        clean = []
        rows_seen = 0
        warnings: list[str] = []
        for match in matches:
            rows_seen += 1
            if end and match.event_time > end:
                continue
            if match.status != "FINISHED":
                warnings.append(f"excluded_not_finished:{match.match_id}")
                continue
            clean.append(match)
        clean.sort(key=lambda item: (item.event_time, item.match_id))
        generator = TemporalFeatureGenerator()
        dataset_rows: list[DatasetRow] = []
        for match, features, _missing, feature_warnings, completeness in generator.build_snapshots(clean):
            if start and match.event_time < start:
                continue
            labels = labels_for_match(match)
            exclusion = None
            if features["home_team_matches"] < self.min_history_matches or features["away_team_matches"] < self.min_history_matches:
                exclusion = "insufficient_team_history"
            dataset_rows.append(DatasetRow(match=match, features=features, labels=labels, data_completeness=completeness, exclusion_reason=exclusion))
            warnings.extend(f"{match.match_id}:{warning}" for warning in feature_warnings)
        included = [row for row in dataset_rows if row.exclusion_reason is None]
        fingerprint = dataset_fingerprint(included)
        dates = [row.match.event_time.date().isoformat() for row in included]
        report = DatasetBuildReport(
            rows_seen=rows_seen,
            rows_included=len(included),
            rows_excluded=len(dataset_rows) - len(included),
            competitions=sorted({row.match.competition for row in included})[:100],
            min_date=min(dates) if dates else None,
            max_date=max(dates) if dates else None,
            dataset_fingerprint=fingerprint,
            warnings=warnings[:200],
            dry_run=True,
        )
        return included, report


def labels_for_match(match: HistoricalMatch) -> dict[str, int | float | str]:
    return {
        "home_goals": match.home_goals,
        "away_goals": match.away_goals,
        "home_win": int(match.home_goals > match.away_goals),
        "draw": int(match.home_goals == match.away_goals),
        "away_win": int(match.home_goals < match.away_goals),
        "result": match.result_key,
        "over_1_5": int(match.total_goals > 1.5),
        "over_2_5": int(match.total_goals > 2.5),
        "over_3_5": int(match.total_goals > 3.5),
        "btts_yes": int(match.home_goals > 0 and match.away_goals > 0),
    }


def dataset_fingerprint(rows: list[DatasetRow]) -> str:
    payload = [
        {
            "match_id": row.match.match_id,
            "event_time": row.match.event_time.isoformat(),
            "home": row.match.home_team,
            "away": row.match.away_team,
            "score": [row.match.home_goals, row.match.away_goals],
            "features": row.features,
            "labels": row.labels,
        }
        for row in rows
    ]
    return content_hash(payload)


def load_matches_csv(path: str | Path, limit: int | None = None) -> list[HistoricalMatch]:
    source = Path(path)
    matches: list[HistoricalMatch] = []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for idx, row in enumerate(reader):
            if limit is not None and len(matches) >= limit:
                break
            try:
                match = match_from_row(row, idx)
            except Exception:
                continue
            matches.append(match)
    return matches


def match_from_row(row: dict[str, str], idx: int) -> HistoricalMatch:
    date_raw = row.get("MatchDate") or row.get("date") or row.get("Date")
    if not date_raw:
        raise ValueError("missing date")
    event_time = datetime.fromisoformat(date_raw.strip()).replace(tzinfo=UTC)
    home_goals = int(float(row.get("FTHome") or row.get("home_goals") or ""))
    away_goals = int(float(row.get("FTAway") or row.get("away_goals") or ""))
    home = (row.get("HomeTeam") or row.get("home") or "").strip()
    away = (row.get("AwayTeam") or row.get("away") or "").strip()
    if not home or not away:
        raise ValueError("missing teams")
    ht_home = parse_optional_int(row.get("HTHome"))
    ht_away = parse_optional_int(row.get("HTAway"))
    odds_home = parse_optional_float(row.get("OddHome") or row.get("odds_home"))
    odds_draw = parse_optional_float(row.get("OddDraw") or row.get("odds_draw"))
    odds_away = parse_optional_float(row.get("OddAway") or row.get("odds_away"))
    competition = (row.get("Division") or row.get("league") or row.get("competition") or "unknown").strip()
    season = str(event_time.year)
    return HistoricalMatch(
        match_id=f"{competition}:{date_raw}:{home}:{away}:{idx}",
        event_time=event_time,
        competition=competition,
        season=season,
        home_team=home,
        away_team=away,
        home_goals=home_goals,
        away_goals=away_goals,
        halftime_home_goals=ht_home,
        halftime_away_goals=ht_away,
        odds_home=odds_home,
        odds_draw=odds_draw,
        odds_away=odds_away,
        observed_at=event_time,
    )


def parse_optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(float(value))


def parse_optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "."))
