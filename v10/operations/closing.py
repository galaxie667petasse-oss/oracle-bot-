from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from v10.time import ensure_utc


@dataclass(frozen=True)
class NearCloseLine:
    decimal_odds: Decimal | None
    observed_at: datetime | None
    seconds_before_kickoff: int | None
    quality: str
    source_snapshot_id: str | None = None
    bookmaker_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "decimal_odds": str(self.decimal_odds) if self.decimal_odds is not None else None,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "seconds_before_kickoff": self.seconds_before_kickoff,
            "quality": self.quality,
            "source_snapshot_id": self.source_snapshot_id,
            "bookmaker_count": self.bookmaker_count,
        }


def classify_near_close(event_time: datetime, observed_at: datetime | None) -> tuple[str, int | None]:
    event_time = ensure_utc(event_time, "event_time")
    if observed_at is None:
        return "MISSING", None
    observed_at = ensure_utc(observed_at, "observed_at")
    delta = int((event_time - observed_at).total_seconds())
    if delta < 0:
        return "REJECTED_FUTURE_ODDS", delta
    if delta <= 5 * 60:
        return "EXACT_OR_VERY_NEAR", delta
    if delta <= 15 * 60:
        return "ACCEPTABLE", delta
    return "STALE", delta


def select_near_close(event_time: datetime, snapshots: list[dict[str, Any]]) -> NearCloseLine:
    valid = []
    for row in snapshots:
        observed_at = row.get("observed_at")
        if isinstance(observed_at, str):
            from v10.time import parse_utc

            observed_at = parse_utc(observed_at)
        if observed_at is None:
            continue
        quality, delta = classify_near_close(event_time, observed_at)
        if quality == "REJECTED_FUTURE_ODDS":
            continue
        valid.append((delta if delta is not None else 10**12, row, observed_at))
    if not valid:
        return NearCloseLine(None, None, None, "MISSING")
    _, row, observed_at = min(valid, key=lambda item: item[0])
    quality, delta = classify_near_close(event_time, observed_at)
    return NearCloseLine(
        decimal_odds=Decimal(str(row.get("decimal_odds"))),
        observed_at=observed_at,
        seconds_before_kickoff=delta,
        quality=quality,
        source_snapshot_id=str(row.get("id", "")) or None,
        bookmaker_count=int(row.get("bookmaker_count", 1) or 1),
    )
