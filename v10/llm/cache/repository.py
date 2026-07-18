from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class CacheEntry:
    cache_key: str
    response: dict[str, Any]
    created_at: datetime
    packet_hash: str


@dataclass
class InMemoryLLMCache:
    entries: dict[str, CacheEntry] = field(default_factory=dict)

    def get(self, cache_key: str) -> dict[str, Any] | None:
        entry = self.entries.get(cache_key)
        return entry.response if entry else None

    def put(self, cache_key: str, response: dict[str, Any], packet_hash: str) -> None:
        self.entries[cache_key] = CacheEntry(cache_key, response, datetime.now(UTC), packet_hash)

    def invalidate_packet(self, packet_hash: str) -> int:
        keys = [key for key, entry in self.entries.items() if entry.packet_hash == packet_hash]
        for key in keys:
            del self.entries[key]
        return len(keys)

    def status(self) -> dict:
        return {"entries": len(self.entries), "cache_type": "in_memory", "lab_only": True, "can_influence_picks": False}
