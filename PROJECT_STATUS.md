# Statut Oracle Football Bot

## Version actuelle

V6.8 External xG Rolling Features Lab.

Le projet reste une release candidate locale prudente. V6.8 ajoute un pipeline laboratoire qui transforme le xG externe post-match en rolling features pre-match. Aucun signal n'est branche aux picks Telegram.

## Etat general

- Memoire moderne recommandee : 2015-2025.
- Volume connu : environ 528066 records regles.
- Rapports locaux disponibles : backtest, favoris, stabilite, pricing, ML, External Dataset Lab, dashboard central.
- Lab xG externe disponible pour profiler un dataset fourni manuellement.
- Rolling xG externe disponible en laboratoire local.
- Benchmark scientifique et registre modele disponibles.
- Aucun signal robuste positif n'est valide a ce stade.
- Aucun changement local V6.x ne doit rendre Telegram plus agressif.

## Etat des modules

- `pricing.py` : stable pour probabilites implicites, no-vig, marge marche et EV baseline.
- `xgabora_dataset_import.py` : import historique local et enrichissement terrain depuis CSV.
- `feature_builder.py` : feature matrix, rolling pre-match avg5, marquage des post-match features.
- `model_trainer.py` : regression logistique locale, sklearn optionnel, comparaison au marche no-vig.
- `benchmark_governance.py` : consolidation marche/regles/segments/ML/lab xG et scoring prudent.
- `decision_policy.py` : politique testable de classification et promotion.
- `backtest_evaluator.py` : split temporel, rapports modern/recent/favoris/stabilite/pricing.
- `external_dataset_probe.py` : profilage local de datasets externes sans telechargement.
- `external_join_plan.py` : jointure theorique date/home/away sans ecriture.
- `external_xg_lab.py` : profilage xG, jointure theorique, evaluation et preview dans `reports/`.
- `external_xg_features.py` : generation de rolling xG pre-match depuis un dataset externe.
- `xg_model_lab.py` : evaluation descriptive des rolling xG contre le marche no-vig.
- `team_name_normalizer.py` : normalisation prudente des noms d'equipes et suggestions de mapping manuel.
- `external_adapters/epl_fbref_lab.py` : adaptateur laboratoire EPL/FBref local.
- `report_runner.py` : execution reproductible des rapports locaux.
- `dashboard_builder.py` : dashboard HTML local et `summary.json`.
- `project_audit.py` : audit release candidate local.
- `COMMANDS.md` : fiche de commandes pour developpeur.
- `model_registry.json` : metadonnees agregees des strategies/modeles evalues.

## Resultats connus

- Aucune strategie robuste positive n'est validee.
- Le ML local ne bat pas encore le marche no-vig sur test 2024+.
- Les marges elevees sont dangereuses et degradent fortement le ROI.
- Les signaux favoris H2H restent proches du break-even mais non confirmes.
- Les edges ML positifs en validation ont ete invalides sur test dans les essais V6.1/V6.2.
- Les rolling pre-match ajoutent du contexte mais ne suffisent pas encore a battre le marche.
- V6.6 ne valide aucune strategie : il prepare seulement le test d'un dataset xG externe.
- V6.7 ne valide aucune strategie : elle formalise la gouvernance, les refus et les conditions de promotion.
- V6.8 ne valide aucune strategie : elle teste seulement si le xG rolling peut ameliorer les probabilites en laboratoire.
- Dataset EPL/FBref-Kaggle 2024-2025 teste localement : 380 matchs, 2024-08-16 -> 2025-05-25, jointure environ 89.47%, 340 matchs joints avec xG + cotes xgabora.

## Ce qui est valide

- Import historique massif local.
- Pricing no-vig descriptif.
- Backtest train/validation/test.
- Feature matrix locale reproductible.
- Exclusion par defaut des post-match features.
- Rolling features pre-match sans usage du match courant.
- Rapports locaux qui ne modifient pas `oracle_db.json`.
- Lab externe sans API, scraping ni telechargement automatique.
- Lab xG externe sans API, scraping ni telechargement automatique.
- Preview xG limite a `reports/`, non utilisable comme dataset d'entrainement production.
- Rolling xG calcule uniquement avec matchs strictement anterieurs.
- Scoring de robustesse prudent, avec invalidation si test 2024+ contredit la validation.
- Registre modele sans secrets, sans predictions individuelles et sans gros dataset.

## Ce qui est invalide ou non confirme

- Transformer un edge validation en pick conseille.
- Utiliser les stats finales du match pour predire ce meme match en live.
- Considerer les favoris H2H comme strategie jouable.
- Redeployer Railway sans signal robuste.
- Augmenter l'agressivite Telegram.
- Utiliser un xG final post-match pour predire le meme match.
- Exporter `home_xg` ou `away_xg` directs comme features predictives.
- Considerer un preview de jointure comme dataset final.
- Promouvoir une strategie validation-positive mais test-negative.
- Confondre `production_allowed` avec pari automatique.

## Ce qu'il ne faut pas faire

- Ne pas modifier `main.py` ou `Dockerfile` sans bug bloquant prouve.
- Ne pas toucher a `oracle_db.json`, aux backups ou a `data/MATCHES.csv` pour stabiliser la release.
- Ne pas scraper FBref, Understat ou Kaggle automatiquement.
- Ne pas utiliser Railway maintenant.
- Ne pas transformer un rapport local en mecanisme de picks.
- Ne pas brancher un dataset xG externe aux picks Telegram.
- Ne pas utiliser l'accuracy brute comme critere principal du ML.

## Difference avec un bot de pronostics classique

- Pas de picks forces.
- Pas de promesses de profit.
- Backtest temporel train/validation/test.
- Anti-fuite de donnees explicite.
- Pricing no-vig pour comparer au marche.
- Calibration probabiliste avant toute lecture de ROI.
- ML evalue contre le marche, pas contre une intuition.
- External data lab avant integration.
- Gouvernance modele avant activation.

## Prochaine vraie priorite

1. Lire le rapport `xg_model_lab.py` sur le CSV rolling xG.
2. Verifier si les rolling xG battent le marche no-vig sur test interne 2025.
3. Si le signal reste faible, chercher un dataset xG multi-saisons pour augmenter le volume.
4. Relancer train/validation/test puis benchmark gouvernance.
5. Maintenir Railway et Telegram en attente tant qu'aucune strategie robuste positive n'est validee.
