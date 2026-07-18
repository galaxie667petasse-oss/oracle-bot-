# Agents V10

Les agents V10 ne calculent pas les probabilites, les edges, l'EV, le ROI ou la CLV. Ces valeurs viennent des modules Python et du ledger.

## Regles communes

- Entree compacte, horodatee et deja filtree.
- Sortie stricte `schema_version=1.0`.
- Aucune cote, blessure, composition ou source inventee.
- La confiance d'un agent n'est pas une probabilite de gain.
- Un veto peut refuser un candidat, jamais le promouvoir seul.
- Les agents ne publient jamais sur Telegram.

## Agents specialises

1. `statistical_model_auditor`
2. `market_pricing_analyst`
3. `recent_form_analyst`
4. `home_away_specialist`
5. `squad_availability_analyst`
6. `tactical_matchup_analyst`
7. `schedule_fatigue_analyst`
8. `competition_context_analyst`
9. `news_source_reliability_analyst`
10. `data_quality_anomaly_analyst`
11. `devils_advocate`
12. `portfolio_correlation_analyst`

La premiere implementation concrete est `v10.agents`, avec validation pure Python et agents mock pour la demo offline. Pydantic v2 reste la cible quand la dependance sera ajoutee proprement.

