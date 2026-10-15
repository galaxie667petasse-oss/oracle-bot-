from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from v10.db.models import OperationalAlert, ProviderQuotaUsage
from v10.time import ensure_utc, utc_now


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    priority_order: list[str]
    reason: str
    estimated_remaining: int | None


class ProviderQuotaManager:
    priority_order = [
        "results_and_settlement",
        "fixtures_under_90_minutes",
        "finalists",
        "near_close_odds",
        "fixtures_under_24_hours",
        "background_refresh",
    ]

    def record_headers(self, session: Session | None, provider_key: str, request_type: str, headers: dict[str, Any] | None, failures: int = 0, observed_at: datetime | None = None) -> dict:
        observed_at = ensure_utc(observed_at or utc_now(), "observed_at")
        headers = {str(k).lower(): str(v) for k, v in (headers or {}).items() if "authorization" not in str(k).lower() and "key" not in str(k).lower()}
        remaining = None
        for key in ("x-ratelimit-remaining", "x-requests-remaining", "ratelimit-remaining"):
            if key in headers:
                try:
                    remaining = int(headers[key])
                except Exception:
                    remaining = None
        if session is not None:
            session.add(
                ProviderQuotaUsage(
                    provider_key=provider_key,
                    request_type=request_type,
                    quota_headers_json=headers,
                    calls=1,
                    failures=failures,
                    estimated_remaining_quota=remaining,
                    observed_at=observed_at,
                )
            )
            if remaining is not None and remaining <= 5:
                session.add(OperationalAlert(severity="WARNING", source="provider_quota", code="quota_low", message=f"Quota faible pour {provider_key}", provider_key=provider_key))
            session.flush()
        return {"provider": provider_key, "request_type": request_type, "estimated_remaining": remaining, "headers_recorded": sorted(headers)}

    def allow_request(self, estimated_remaining: int | None, request_class: str) -> QuotaDecision:
        if estimated_remaining is None:
            return QuotaDecision(True, self.priority_order, "quota_unknown_provider_did_not_report_limit", None)
        if estimated_remaining <= 0:
            return QuotaDecision(False, self.priority_order, "quota_exhausted", estimated_remaining)
        if estimated_remaining <= 5 and request_class not in {"results_and_settlement", "fixtures_under_90_minutes", "near_close_odds"}:
            return QuotaDecision(False, self.priority_order, "quota_critical_degrade_optional_calls", estimated_remaining)
        return QuotaDecision(True, self.priority_order, "quota_available", estimated_remaining)

