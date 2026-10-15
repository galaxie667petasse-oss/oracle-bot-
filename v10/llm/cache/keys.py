from __future__ import annotations

from v10.llm.evidence.models import stable_hash


def llm_cache_key(
    provider: str,
    model: str,
    reasoning: str,
    prompt_version: str,
    schema_name: str,
    panel_or_agent: str,
    packet_hash: str,
    tool_policy_version: str = "read_only_tools_v1",
) -> str:
    return stable_hash(
        {
            "provider": provider,
            "model": model,
            "reasoning": reasoning,
            "prompt_version": prompt_version,
            "schema_name": schema_name,
            "panel_or_agent": panel_or_agent,
            "packet_hash": packet_hash,
            "tool_policy_version": tool_policy_version,
        }
    )
