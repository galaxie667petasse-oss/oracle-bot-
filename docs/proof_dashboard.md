# V9.1 Proof Dashboard

Objectif: regrouper shadow, evidence gate, Big 5, CLV historique, quality audit et intake dans un seul rapport local.

Commande:

```powershell
python proof_dashboard.py --shadow reports/shadow_clv_report.json --evidence reports/evidence_gate.json --big5 reports/big5_xg_summary.json --historical-clv reports/historical_clv_backtest.json --output reports/proof_dashboard.json --html reports/proof_dashboard.html
```

Le proof dashboard affiche:

- sample shadow;
- coverage CLV;
- CLV moyenne;
- ROI si disponible;
- statut evidence gate;
- preuve historique;
- blockers;
- prochaines actions.

Conclusion attendue tant que CLV/sample live sont insuffisants: preuve insuffisante.
## V9.4 Sections operations

Le proof dashboard peut afficher les signaux V9.4 quand les rapports existent:

- future intake;
- near-close window;
- post-match results;
- free historical data;
- subscription/quota status.

Ces sections ne changent pas la politique de promotion. Elles aident seulement a comprendre pourquoi la preuve reste insuffisante.

## V9.8 Completed cycle

Le proof dashboard affiche maintenant dans la section shadow:

- `completed_cycles`;
- `pending_closing`;
- `pending_results`;
- `profit_units_total`;
- `result_coverage`;
- `clv_coverage`;
- `first_complete_cycle`.

`first_complete_cycle=true` signifie qu'au moins une observation possede une closing/near-close et un resultat final. Ce signal est utile pour verifier le workflow, mais il ne valide pas le modele.

Conclusion attendue avec un seul cycle Ghana - Panama: preuve insuffisante, aucune activation, aucune mise.

## V10 proof fields

Les futures integrations dashboard doivent afficher:

- `data_quality_status`;
- `candidate_count`;
- `rejected_count`;
- `llm_calls_used`;
- `completed_cycles`;
- `clv_odds_pct`;
- `clv_probability_points`;
- `paper_only=true`.

Ces champs sont informatifs. Le dashboard ne doit pas transformer une demo ou un faible sample en validation.
