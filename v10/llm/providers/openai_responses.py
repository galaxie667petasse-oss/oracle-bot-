from __future__ import annotations

from time import perf_counter

from v10.llm.config import LLMRuntimeConfig
from v10.llm.contracts import LLMUsage, StructuredRequest, StructuredResponse


STRICT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
}


class OpenAIResponsesProvider:
    provider_key = "openai_responses"

    def __init__(self, config: LLMRuntimeConfig, api_key: str = "", timeout_seconds: float = 30.0):
        self.config = config
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def health_check(self) -> dict:
        try:
            import openai  # type: ignore

            sdk_version = str(getattr(openai, "__version__", "unknown"))
        except Exception:
            sdk_version = "not_installed"
        return {
            "provider": self.provider_key,
            "configured": bool(self.api_key),
            "paid_calls_enabled": self.config.can_call_paid(False),
            "sdk_version": sdk_version,
            "responses_api": True,
            "structured_outputs": True,
            "function_calling_prepared": True,
        }

    async def generate_with_tools(self, request: StructuredRequest) -> StructuredResponse:
        return await self.generate_structured(request)

    def build_responses_payload(self, request: StructuredRequest, tools: list[dict] | None = None) -> dict:
        payload = {
            "model": request.model,
            "reasoning": {"effort": request.reasoning_effort},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Return only compact JSON matching the requested schema. "
                        "Use only provided evidence. Do not calculate odds, EV, CLV, Kelly, stake, or results."
                    ),
                },
                {"role": "user", "content": str(request.input_payload)},
            ],
            "max_output_tokens": request.max_output_tokens,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "strict": True,
                    "schema": STRICT_JSON_SCHEMA,
                }
            },
        }
        if tools:
            payload["tools"] = tools
        return payload

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
        response = await client.responses.create(**self.build_responses_payload(request))
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
