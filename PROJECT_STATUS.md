# Statut Oracle Football Bot

## Etat actuel

Oracle Football Bot dispose d'une memoire moderne 2015-2025 avec environ 528066 records regles, des rapports locaux de backtest, pricing, favoris H2H, stabilite, feature matrix, ML leger et laboratoire de datasets externes.

Le projet reste en posture prudente : aucune strategie robuste positive n'est validee a ce stade.

## Modules existants

- `pricing.py` : probabilites implicites, no-vig, marge marche, EV baseline.
- `xgabora_dataset_import.py` : import historique xgabora et enrichissement terrain local.
- `feature_builder.py` : matrice de features, rolling pre-match avg5, exclusion anti-fuite.
- `model_trainer.py` : regression logistique locale, comparaison au marche no-vig, edge simulation validation -> test.
- `backtest_evaluator.py` : backtest temporel, rapports favoris/stabilite/pricing.
- `external_dataset_probe.py` : profilage local de datasets externes.
- `external_join_plan.py` : plan de jointure theorique date/home/away.
- `external_adapters/epl_fbref_lab.py` : adaptateur laboratoire EPL/FBref local.
- `report_runner.py` et `dashboard_builder.py` : rapport central local et dashboard HTML.

## Memoire active recommandee

Conserver la memoire moderne 2015-2025 actuelle. Ne pas reintegrer massivement l'archive ancienne dans les decisions modernes. Le test 2024+ reste la reference finale.

## Resultats importants connus

- Pricing : marge moyenne H2H environ 0.66%, Over/Under environ 1.83%.
- Pricing : ROI marge faible negatif, ROI marge elevee tres negatif.
- V6.1/V6.2 : le modele local ne bat pas le marche no-vig sur test 2024+.
- H2H rolling : validation positive mais test negatif, donc signal invalide.
- Total rolling : validation positive mais test negatif, donc signal invalide.
- External Lab : xgabora/features est riche en cotes et resultats, mais sans xG.

## Valide

- Import historique massif.
- Backtest train/validation/test.
- Pricing no-vig descriptif.
- Feature matrix locale.
- Rolling pre-match sans fuite du match courant.
- Exclusion par defaut des post-match features.
- Lab externe sans API, scraping ni telechargement.
- Rapport central local reproductible.

## Invalide ou non confirme

- Aucune strategie robuste positive.
- Favoris H2H proches du break-even mais non confirmes.
- Edges ML positifs validation invalides sur test.
- Stats post-match interdites pour prediction live du meme match.

## A ne pas faire

- Ne pas redéployer Railway maintenant.
- Ne pas rendre Telegram plus agressif.
- Ne pas transformer un signal validation en pick automatique.
- Ne pas utiliser xG final, tirs finaux ou corners finaux pour predire le meme match.
- Ne pas modifier `oracle_db.json` sans sauvegarde et raison explicite.
- Ne pas scraper FBref/Understat automatiquement.

## Prochaine priorite

Chercher un dataset externe local riche, idealement EPL/FBref ou Kaggle 2024-2025/multi-saisons, avec date, equipes, resultats, xG/xGA, tirs, tirs cadres, lineups horodatees si possible, stats equipes/joueurs et cotes si disponibles. Le profiler avec `external_dataset_probe.py`, evaluer la jointure avec `external_join_plan.py`, puis seulement ensuite tester en train/validation/test.
