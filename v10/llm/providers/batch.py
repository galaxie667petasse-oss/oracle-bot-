from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from v10.llm.evidence.models import stable_hash


@dataclass(frozen=True)
class BatchItem:
    custom_id: str
    model: str
    payload: dict[str, Any]


class OpenAIBatchEvaluationService:
    """Offline-first helper for non-urgent LLM evaluations.

    The class deliberately does not upload files. A future paid path must require
    OPENAI_BATCH_ENABLED, budget reservation, and an explicit CLI allow flag.
    """

    endpoint = "/v1/responses"

    def create_jsonl(self, items: list[BatchItem]) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for item in items:
            if item.custom_id in seen:
                raise ValueError(f"duplicate custom_id: {item.custom_id}")
            seen.add(item.custom_id)
            body = {"model": item.model, "input": item.payload.get("input", []), "max_output_tokens": item.payload.get("max_output_tokens", 500)}
            lines.append(json.dumps({"custom_id": item.custom_id, "method": "POST", "url": self.endpoint, "body": body}, ensure_ascii=False, sort_keys=True))
        return "\n".join(lines) + ("\n" if lines else "")

    def validate_jsonl(self, text: str) -> dict[str, Any]:
        errors = []
        count = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            count += 1
            try:
                row = json.loads(line)
            except Exception as exc:
                errors.append({"line": line_no, "error": str(exc)})
                continue
            if not row.get("custom_id") or row.get("method") != "POST" or row.get("url") != self.endpoint:
                errors.append({"line": line_no, "error": "invalid_batch_row"})
        return {"valid": not errors, "line_count": count, "errors": errors, "content_hash": stable_hash(text)}

    def reconcile_results(self, requests_jsonl: str, results_jsonl: str) -> dict[str, Any]:
        requests = {json.loads(line)["custom_id"] for line in requests_jsonl.splitlines() if line.strip()}
        matched = 0
        errors = []
        for line_no, line in enumerate(results_jsonl.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception as exc:
                errors.append({"line": line_no, "error": str(exc)})
                continue
            custom_id = row.get("custom_id")
            if custom_id in requests:
                matched += 1
            else:
                errors.append({"line": line_no, "error": "unknown_custom_id", "custom_id": custom_id})
        return {"requested": len(requests), "matched": matched, "partial_errors": errors, "upload_executed": False}
