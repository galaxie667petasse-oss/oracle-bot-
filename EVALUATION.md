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

## Phase 3

La premiere evaluation V10 statistique compare des probabilites, pas des slogans de performance. Les fonctions `v10.statistics.metrics` couvrent log loss multiclass, Brier multiclass, Brier/log loss binaires et ECE/MCE par bins.

Splits supportes :

- holdout chronologique simple dans `train_model`;
- walk-forward minimal dans `walk_forward_backtest`;
- validation separee pour calibration et ensemble.

Modeles compares :

- Elo multiclass;
- Poisson independant;
- Dixon-Coles experimental;
- ensemble sans prior marche;
- baseline marche via no-vig quand les cotes `as_of` sont disponibles.

Une amelioration observee sur sample faible reste un diagnostic. Elle ne valide aucun signal, aucun ROI et aucune publication.
