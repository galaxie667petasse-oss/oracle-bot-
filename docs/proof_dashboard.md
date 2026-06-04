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
