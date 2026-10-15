def summarize_llm_results(results: list[dict]) -> dict:
    total = len(results)
    schema_errors = sum(bool(row.get("semantic_errors")) for row in results)
    hard_vetoes = sum(bool(row.get("contradictions", {}).get("hard_vetoes")) for row in results)
    accepted = sum(row.get("decision", {}).get("final_status") == "SHADOW_ACCEPTED" for row in results)
    calls = sum(len(row.get("calls", [])) for row in results)
    return {
        "cases": total,
        "schema_or_semantic_error_rate": schema_errors / total if total else 0.0,
        "hard_veto_count": hard_vetoes,
        "shadow_accepted_count": accepted,
        "total_calls": calls,
        "average_calls_per_case": calls / total if total else 0.0,
    }
