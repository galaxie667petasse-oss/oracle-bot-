from __future__ import annotations

import json
from pathlib import Path

from v10.llm.contracts import StructuredRequest, StructuredResponse


class ReplayLLMProvider:
    provider_key = "replay"

    def __init__(self, path: str):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.responses = payload if isinstance(payload, list) else [payload]
        self.index = 0

    async def health_check(self) -> dict:
        return {"provider": self.provider_key, "status": "OK", "remaining": max(len(self.responses) - self.index, 0)}

    async def generate_with_tools(self, request: StructuredRequest) -> StructuredResponse:
        return await self.generate_structured(request)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        if self.index >= len(self.responses):
            raise RuntimeError("replay_exhausted")
        payload = self.responses[self.index]
        self.index += 1
        if "request_id" not in payload:
            payload = {
                "request_id": request.request_id,
                "provider": self.provider_key,
                "requested_model": request.model,
                "used_model": request.model,
                "status": "OK",
                "output": payload,
            }
        return StructuredResponse(**payload)
