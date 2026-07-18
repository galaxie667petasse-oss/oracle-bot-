from __future__ import annotations

from v10.llm.routing import LLMRoutePlan


def planned_steps(plan: LLMRoutePlan) -> list[dict]:
    steps: list[dict] = []
    if plan.run_luna:
        steps.append({"tier": "FAST", "panel_or_agent": "luna_triage"})
    for panel in plan.terra_panels:
        steps.append({"tier": "SPECIALIST", "panel_or_agent": panel})
    if plan.run_devils_advocate:
        steps.append({"tier": "SPECIALIST", "panel_or_agent": "devils_advocate"})
    if plan.run_portfolio:
        steps.append({"tier": "SPECIALIST", "panel_or_agent": "portfolio_correlation_analyst"})
    if plan.run_sol:
        steps.append({"tier": "FINAL", "panel_or_agent": "final_judge"})
    return steps
