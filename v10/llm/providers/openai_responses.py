from __future__ import annotations

from time import perf_counter

from v10.llm.config import LLMRuntimeConfig
from v10.llm.contracts import LLMUsage, StructuredRequest, StructuredResponse


class OpenAIResponsesProvider:
    provider_key = "openai_responses"

    def __init__(self, config: LLMRuntimeConfig, api_key: str = "", timeout_seconds: float = 30.0):
        self.config = config
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def health_check(self) -> dict:
        return {
            "provider": self.provider_key,
            "configured": bool(self.api_key),
            "paid_calls_enabled": self.config.can_call_paid(False),
            "sdk_import_lazy": True,
        }

    async def generate_with_tools(self, request: StructuredRequest) -> StructuredResponse:
        return await self.generate_structured(request)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        if not self.config.can_call_paid(request.allow_paid):
            raise PermissionError("OpenAI call blocked: LLM flags, budget and --allow-paid are required")
        if not self.api_key:
            raise PermissionError("OpenAI call blocked: OPENAI_API_KEY absent")
        start = perf_counter()
        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"OpenAI SDK unavailable: {exc}") from exc
        client = AsyncOpenAI(api_key=self.api_key, timeout=self.timeout_seconds)
        response = await client.responses.create(
            model=request.model,
            reasoning={"effort": request.reasoning_effort},
            input=[
                {"role": "system", "content": "Return only strict JSON matching the requested schema. Use only provided evidence."},
                {"role": "user", "content": str(request.input_payload)},
            ],
            max_output_tokens=request.max_output_tokens,
        )
        output_text = getattr(response, "output_text", "{}")
        import json

        output = json.loads(output_text)
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cached = int(getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0)
        return StructuredResponse(
            request_id=request.request_id,
            provider=self.provider_key,
            requested_model=request.model,
            used_model=str(getattr(response, "model", request.model)),
            status="OK",
            output=output,
            response_id=str(getattr(response, "id", "")),
            usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens, cached_input_tokens=cached),
            latency_ms=int((perf_counter() - start) * 1000),
        )
