SPECIALIST_AGENT_IDS = [
    "statistical_model_auditor",
    "market_pricing_analyst",
    "recent_form_analyst",
    "home_away_specialist",
    "squad_availability_analyst",
    "tactical_matchup_analyst",
    "schedule_fatigue_analyst",
    "competition_context_analyst",
    "news_source_reliability_analyst",
    "data_quality_anomaly_analyst",
    "devils_advocate",
    "portfolio_correlation_analyst",
]

PANEL_ROLES = {
    "quantitative_integrity": ["statistical_model_auditor", "market_pricing_analyst"],
    "match_context": ["recent_form_analyst", "home_away_specialist", "schedule_fatigue_analyst", "competition_context_analyst"],
    "fresh_information": ["squad_availability_analyst", "tactical_matchup_analyst", "news_source_reliability_analyst"],
}
