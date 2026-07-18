# Evaluation V10

## Metriques obligatoires

- Brier score.
- Log loss.
- Expected Calibration Error.
- Calibration par bins.
- ROI et yield shadow.
- Profit units.
- CLV odds pct.
- CLV probability points.
- Drawdown maximum.
- Resultats par marche, ligue, tranche de cote et niveau de confiance.

## Regles methodologiques

- Split chronologique uniquement.
- Pas de shuffle temporel.
- Pas de feature observee apres la decision.
- Pas de cote de cloture en entree pre-match.
- Pas de promotion avec sample faible.
- Zero signal est un resultat valide.

## Etat actuel

V9.x contient deja calibration, statistical validation et CLV. V10 foundation ajoute les primitives deterministes a tester avant le backtest walk-forward complet.

