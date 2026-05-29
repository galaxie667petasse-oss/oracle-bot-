# Backtest train/test Oracle Bot

`backtest_evaluator.py` vérifie si les règles apprises sur l'historique se comportent encore correctement sur une période plus récente.

Il ne lance pas Telegram, n'appelle aucune API externe et ne sauvegarde pas la mémoire. Il lit seulement la DB via `load_db()`.

## Pourquoi train/test est indispensable

Un ROI global historique peut donner une impression trompeuse. Si les mêmes résultats servent à créer les règles et à les évaluer, le bot risque seulement de mémoriser le passé.

Le découpage train/test force une séparation :

- le train construit la calibration et les segments ;
- le test mesure ce qui se serait passé ensuite ;
- les résultats test ne sont jamais utilisés pour fabriquer la calibration.

Le ROI sur le test compte donc davantage que le ROI train.

## Commandes

Par défaut :

```bash
python backtest_evaluator.py
```

Équivaut à :

```bash
python backtest_evaluator.py --train-to 2023-12-31 --test-from 2024-01-01
```

Autre découpage :

```bash
python backtest_evaluator.py --train-to 2022-12-31 --test-from 2023-01-01
```

Sortie JSON :

```bash
python backtest_evaluator.py --train-to 2022-12-31 --test-from 2023-01-01 --json out/backtest.json
```

Presets modernes :

```bash
python backtest_evaluator.py --preset modern
python backtest_evaluator.py --preset recent
python backtest_evaluator.py --preset long
python backtest_evaluator.py --preset archive-check
```

Rapport par période :

```bash
python backtest_evaluator.py --period-report
```

## Stratégies évaluées

- `baseline_all` : tous les records test.
- `no_blocked_segments` : exclut les segments bloqués par le train.
- `totals_only` : seulement les marchés Over/Under.
- `totals_low` : seulement Over/Under en cote low.
- `totals_low_mid` : seulement Over/Under avec cotes low ou mid.
- `strict_oracle` : applique les seuils de calibration et les segments appris sur train.
- `favorites_only` : cotes inférieures à 2.0.
- `avoid_outsiders` : exclut les cotes à partir de 3.0.
- `modern_weighted_oracle` : Oracle strict limité aux périodes modernes/récentes/test.
- `recent_only_oracle` : Oracle strict limité au récent et au test final.

## Lire les résultats

Pour chaque stratégie, le rapport affiche :

- nombre de picks ;
- gagnés ;
- winrate observé ;
- ROI ;
- profit en unités ;
- cote moyenne ;
- max drawdown ;
- détail par marché ;
- détail par tranche de cote.

Si une stratégie a moins de 100 picks, le rapport affiche `échantillon faible`. Ce n'est pas assez solide pour conclure.

Si aucune stratégie n'est positive sur le test, c'est une information utile : le bot doit refuser davantage et ne pas chercher à forcer des paris.

Même si une stratégie est légèrement positive, ce n'est pas une preuve définitive. Il faut vérifier plusieurs découpages temporels et surveiller le comportement hors échantillon.
## Diagnostic et strategies intermediaires

```bash
python backtest_evaluator.py --preset modern --debug-strategies
```

Ce mode affiche, pour chaque strategie, le nombre de records rejetes, les principales raisons de rejet, des exemples de segments bloques, le nombre de records sans segment trouve et les records retenus par marche.

Les strategies Oracle sont maintenant separees en trois niveaux :

- `oracle_relaxed` : refuse seulement very_high, outsiders forts et segments tres negatifs.
- `oracle_balanced` : ajoute le risque marche, tranche de cote et ROI segment train.
- `oracle_strict` / `strict_oracle` : conserve les seuils les plus durs.

Le rapport isole aussi `draw_high_watchlist`, `favorites_h2h_only`, les favoris H2H par seuil de cote, les favoris domicile/exterieur, le cas Elo favorable si disponible et `total_low` par annee de test.

## Threshold sweep

Le threshold sweep teste des regles candidates sur train + validation, puis les verifie sur test final. Le test ne sert jamais a choisir les seuils.

Les dimensions comparees sont :

- maximum de cote ;
- marche (`h2h`, `draw`, `total`) ;
- tranche de cote (`low`, `mid`, `high`, `very_high`) ;
- exclusion des outsiders ou very_high ;
- ROI train minimum ;
- volume minimum.

Une regle positive sur train mais negative sur test est marquee fragile. Elle ne doit pas devenir une selection activee.

## Conclusion prudente

La conclusion locale reste volontairement conservatrice : aucune regle jouable si le ROI test est negatif ou si l'echantillon est trop faible ; regle candidate seulement si le test final est positif, avec au moins 300 picks et un drawdown raisonnable.
