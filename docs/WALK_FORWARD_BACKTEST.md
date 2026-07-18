# Walk-Forward Backtest V10

Le backtest `walk-forward` est la methode principale d'evaluation chronologique V10.

Commande :

```powershell
python app.py backtest run --from 2024-01-01 --to 2024-12-31 --markets 1x2,ou25,btts --dry-run
```

Principe :

- train chronologique ;
- test sur la fenetre suivante ;
- pas de shuffle ;
- features construites avant le match cible ;
- aucun agent LLM ;
- aucun Telegram ;
- paper-only.

La version initiale mesure log loss et Brier sur 1X2. Les marches derives sont produits par la matrice de score, mais le settlement paper complet reste a enrichir.
