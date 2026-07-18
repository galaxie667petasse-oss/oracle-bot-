from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean
from typing import Iterable

from .elo import EloModel
from .types import FEATURE_SCHEMA_VERSION, HistoricalMatch


@dataclass
class TeamRollingState:
    matches: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    home_matches: int = 0
    away_matches: int = 0
    home_goals_for: int = 0
    away_goals_for: int = 0
    last_match_time: datetime | None = None
    recent_points: deque[int] = field(default_factory=lambda: deque(maxlen=10))
    recent_goal_diff: deque[int] = field(default_factory=lambda: deque(maxlen=10))
    recent_match_times: deque[datetime] = field(default_factory=lambda: deque(maxlen=30))


class TemporalFeatureGenerator:
    schema_version = FEATURE_SCHEMA_VERSION

    def __init__(self):
        self.team_states: dict[str, TeamRollingState] = defaultdict(TeamRollingState)
        self.h2h: dict[tuple[str, str], deque[HistoricalMatch]] = defaultdict(lambda: deque(maxlen=10))
        self.elo = EloModel()

    def features_before(self, match: HistoricalMatch) -> tuple[dict[str, float | int | str | None], dict[str, int], list[str], float]:
        home_state = self.team_states[match.home_team]
        away_state = self.team_states[match.away_team]
        pre_probs = self.elo.probabilities_1x2(match.home_team, match.away_team)
        features: dict[str, float | int | str | None] = {
            "schema_version": self.schema_version,
            "home_team_matches": home_state.matches,
            "away_team_matches": away_state.matches,
            "home_points_per_match": points_per_match(home_state),
            "away_points_per_match": points_per_match(away_state),
            "home_goal_diff_per_match": per_match(home_state.goals_for - home_state.goals_against, home_state.matches),
            "away_goal_diff_per_match": per_match(away_state.goals_for - away_state.goals_against, away_state.matches),
            "home_form5_points": recent_mean(home_state.recent_points, 5),
            "away_form5_points": recent_mean(away_state.recent_points, 5),
            "home_form10_points": recent_mean(home_state.recent_points, 10),
            "away_form10_points": recent_mean(away_state.recent_points, 10),
            "home_form5_goal_diff": recent_mean(home_state.recent_goal_diff, 5),
            "away_form5_goal_diff": recent_mean(away_state.recent_goal_diff, 5),
            "home_home_goals_for_per_match": per_match(home_state.home_goals_for, home_state.home_matches),
            "away_away_goals_for_per_match": per_match(away_state.away_goals_for, away_state.away_matches),
            "home_days_since_last_match": days_between(home_state.last_match_time, match.event_time),
            "away_days_since_last_match": days_between(away_state.last_match_time, match.event_time),
            "home_matches_last_7d": count_since(home_state.recent_match_times, match.event_time, 7),
            "away_matches_last_7d": count_since(away_state.recent_match_times, match.event_time, 7),
            "home_matches_last_14d": count_since(home_state.recent_match_times, match.event_time, 14),
            "away_matches_last_14d": count_since(away_state.recent_match_times, match.event_time, 14),
            "home_matches_last_30d": count_since(home_state.recent_match_times, match.event_time, 30),
            "away_matches_last_30d": count_since(away_state.recent_match_times, match.event_time, 30),
            "home_elo_pre": self.elo.rating(match.home_team),
            "away_elo_pre": self.elo.rating(match.away_team),
            "elo_diff_pre": self.elo.rating(match.home_team) - self.elo.rating(match.away_team),
            "elo_home_probability_pre": pre_probs["home"],
            "elo_draw_probability_pre": pre_probs["draw"],
            "h2h_count": h2h_count(self.h2h, match.home_team, match.away_team),
            "h2h_home_points_per_match": h2h_home_ppm(self.h2h, match.home_team, match.away_team),
            "month": match.event_time.month,
        }
        missing = {
            "home_history_missing": int(home_state.matches == 0),
            "away_history_missing": int(away_state.matches == 0),
            "home_rest_missing": int(home_state.last_match_time is None),
            "away_rest_missing": int(away_state.last_match_time is None),
            "h2h_missing": int(features["h2h_count"] == 0),
        }
        warnings = [key for key, value in missing.items() if value]
        completeness = 1.0 - sum(missing.values()) / max(len(missing), 1)
        return features, missing, warnings, round(completeness, 6)

    def update_after(self, match: HistoricalMatch) -> None:
        update_team_state(self.team_states[match.home_team], match, is_home=True)
        update_team_state(self.team_states[match.away_team], match, is_home=False)
        self.h2h[(match.home_team, match.away_team)].append(match)
        self.h2h[(match.away_team, match.home_team)].append(match)
        self.elo.update(match)

    def build_snapshots(self, matches: Iterable[HistoricalMatch]) -> list[tuple[HistoricalMatch, dict, dict, list[str], float]]:
        rows = []
        for match in sorted(matches, key=lambda item: item.event_time):
            features, missing, warnings, completeness = self.features_before(match)
            rows.append((match, features, missing, warnings, completeness))
            self.update_after(match)
        return rows


def update_team_state(state: TeamRollingState, match: HistoricalMatch, is_home: bool) -> None:
    gf = match.home_goals if is_home else match.away_goals
    ga = match.away_goals if is_home else match.home_goals
    points = 3 if gf > ga else 1 if gf == ga else 0
    state.matches += 1
    state.wins += int(points == 3)
    state.draws += int(points == 1)
    state.losses += int(points == 0)
    state.goals_for += gf
    state.goals_against += ga
    if is_home:
        state.home_matches += 1
        state.home_goals_for += gf
    else:
        state.away_matches += 1
        state.away_goals_for += gf
    state.recent_points.append(points)
    state.recent_goal_diff.append(gf - ga)
    state.recent_match_times.append(match.event_time)
    state.last_match_time = match.event_time


def points_per_match(state: TeamRollingState) -> float:
    return per_match(3 * state.wins + state.draws, state.matches)


def per_match(value: float, matches: int) -> float:
    return float(value) / matches if matches else 0.0


def recent_mean(values: deque[int], n: int) -> float:
    subset = list(values)[-n:]
    return float(mean(subset)) if subset else 0.0


def days_between(previous: datetime | None, current: datetime) -> float | None:
    if previous is None:
        return None
    return max(0.0, min(60.0, (current - previous).total_seconds() / 86400.0))


def count_since(times: deque[datetime], current: datetime, days: int) -> int:
    return sum(1 for value in times if 0 <= (current - value).total_seconds() <= days * 86400)


def h2h_count(h2h: dict[tuple[str, str], deque[HistoricalMatch]], home: str, away: str) -> int:
    return len(h2h.get((home, away), []))


def h2h_home_ppm(h2h: dict[tuple[str, str], deque[HistoricalMatch]], home: str, away: str) -> float:
    rows = h2h.get((home, away), [])
    if not rows:
        return 0.0
    points = []
    for match in rows:
        if match.home_team == home:
            gf, ga = match.home_goals, match.away_goals
        else:
            gf, ga = match.away_goals, match.home_goals
        points.append(3 if gf > ga else 1 if gf == ga else 0)
    return float(mean(points))
