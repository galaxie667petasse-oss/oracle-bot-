import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from .time import utc_iso


NON_DETERMINISTIC_FIELDS = {
    "fetched_at_runtime",
    "local_received_at",
    "request_duration_ms",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return utc_iso(value)
    raise TypeError(f"Unsupported JSON value for canonical hash: {type(value)!r}")


def canonical_json(data: Any, strip_fields: set[str] | None = None) -> str:
    strip_fields = strip_fields or NON_DETERMINISTIC_FIELDS

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(k): clean(v) for k, v in sorted(value.items(), key=lambda item: str(item[0])) if str(k) not in strip_fields}
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, tuple):
            return [clean(item) for item in value]
        return value

    return json.dumps(clean(data), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=_json_default)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


def request_fingerprint(provider_key: str, endpoint: str, parameters: Mapping[str, Any] | None = None) -> str:
    return sha256_text(canonical_json({"provider": provider_key, "endpoint": endpoint, "parameters": parameters or {}}))


def canonical_observation_fingerprint(data: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(data))


def odds_snapshot_fingerprint(
    fixture_id: str,
    bookmaker_id: str,
    market_id: str,
    selection_key: str,
    line_value: Any,
    decimal_odds: Any,
    observed_at: datetime,
    provider_event_timestamp: datetime | None = None,
) -> str:
    return canonical_observation_fingerprint(
        {
            "fixture_id": fixture_id,
            "bookmaker_id": bookmaker_id,
            "market_id": market_id,
            "selection_key": selection_key,
            "line_value": None if line_value is None else str(line_value),
            "decimal_odds": str(decimal_odds),
            "observed_at": utc_iso(observed_at),
            "provider_event_timestamp": utc_iso(provider_event_timestamp) if provider_event_timestamp else None,
        }
    )

