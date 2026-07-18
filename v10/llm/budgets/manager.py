from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

from .pricing import PricingTable


@dataclass
class BudgetReservation:
    reservation_id: str
    scope_key: str
    model_name: str
    reserved_usd: Decimal
    actual_usd: Decimal = Decimal("0")
    status: str = "RESERVED"


@dataclass
class BudgetManager:
    daily_budget_usd: Decimal
    scan_budget_usd: Decimal
    fixture_budget_usd: Decimal
    pricing: PricingTable = field(default_factory=PricingTable)
    spent_usd: Decimal = Decimal("0")
    reserved_usd: Decimal = Decimal("0")
    reservations: dict[str, BudgetReservation] = field(default_factory=dict)

    def remaining(self) -> Decimal:
        return max(self.daily_budget_usd - self.spent_usd - self.reserved_usd, Decimal("0"))

    def estimate(self, model_name: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
        return self.pricing.estimate(model_name, input_tokens, output_tokens, cached_input_tokens)

    def reserve(self, scope_key: str, model_name: str, estimated_usd: Decimal) -> BudgetReservation:
        if self.daily_budget_usd <= 0:
            raise ValueError("budget_zero")
        if estimated_usd <= 0:
            raise ValueError("budget_estimate_zero")
        if estimated_usd > self.remaining():
            raise ValueError("budget_exhausted")
        reservation = BudgetReservation(str(uuid4()), scope_key, model_name, estimated_usd)
        self.reservations[reservation.reservation_id] = reservation
        self.reserved_usd += estimated_usd
        return reservation

    def reconcile(self, reservation_id: str, actual_usd: Decimal, status: str = "COMPLETED") -> BudgetReservation:
        reservation = self.reservations[reservation_id]
        if reservation.status != "RESERVED":
            raise ValueError("reservation_already_reconciled")
        self.reserved_usd -= reservation.reserved_usd
        self.spent_usd += actual_usd
        reservation.actual_usd = actual_usd
        reservation.status = status
        return reservation

    def status(self) -> dict:
        return {
            "daily_budget_usd": str(self.daily_budget_usd),
            "scan_budget_usd": str(self.scan_budget_usd),
            "fixture_budget_usd": str(self.fixture_budget_usd),
            "spent_usd": str(self.spent_usd),
            "reserved_usd": str(self.reserved_usd),
            "remaining_usd": str(self.remaining()),
            "reservations": [reservation.__dict__ | {"reserved_usd": str(reservation.reserved_usd), "actual_usd": str(reservation.actual_usd)} for reservation in self.reservations.values()],
        }
