# V8.4 Odds E2E Demo

`odds_e2e_demo.py` cree un scenario synthetique complet dans un sous-dossier `reports/`.

Commande :

```bash
python odds_e2e_demo.py --output-dir reports/odds_e2e_demo
```

La demo cree :

- `manual_odds_snapshot_demo.csv` ;
- `odds_snapshots_demo.csv` ;
- `shadow_ledger_demo.csv` ;
- `manual_results_demo.csv` ;
- rapports JSON/HTML de qualite, intake, shadow CLV et evidence gate.

Le scenario :

1. cree une cote taken ;
2. cree une cote near-close ;
3. convertit la taken en observation shadow ;
4. matche la near-close comme closing ;
5. importe un resultat synthetique ;
6. genere les rapports.

Cette demo ne prouve rien sur le marche. Elle sert seulement a tester le workflow local sans reseau.
