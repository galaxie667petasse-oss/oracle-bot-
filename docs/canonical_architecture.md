# Architecture canonique Oracle Football Bot

V8.5 fige la structure du projet en blocs mesurables. Le principe central est simple : les donnees alimentent, les modules mesurent, l'agent orchestre et le LLM explique.

## 1. Sources de donnees

Sources attendues : matchs, equipes, joueurs, cotes, calendrier, forme recente, actualites, xG, resultats et near-close odds. Les sources actuelles sont xgabora/Football-Data/ClubElo, Understat Big 5, snapshots odds manuels, adaptateurs API optionnels et shadow ledger.

## 2. Collecte & nettoyage

Cette couche normalise les noms, controle les cotes, detecte les colonnes douteuses, audite la jointure et refuse les donnees fragiles. Les modules importants sont `team_name_normalizer.py`, `odds_normalizer.py`, `manual_odds_import.py`, `odds_source_quality_report.py` et `odds_intake_audit.py`.

## 3. Base de donnees & versioning

`oracle_db.json`, `data/MATCHES.csv` et `data/features_modern.csv` restent proteges. Les rapports, snapshots locaux et exports externes restent dans `reports/` ou `external_data/`, ignores par Git.

## 4. Moteur de signaux

Le moteur mesure pricing, no-vig, EV, xG rolling, Elo, forme, backtests, calibration, CLV et evidence gate. Il peut refuser un signal, mais ne doit pas produire d'action automatique.

## 5. LLM analyste

Le LLM n'est jamais source de verite. Il recoit des mesures et produit une explication prudente. Il ne calcule pas d'edge, ne cree pas de cote et ne depasse jamais `decision_policy.py` ou `evidence_gate.py`.

## 6. Restitution

La restitution standardise JSON, HTML, dashboard et preview texte privee sans envoi. Elle affiche l'observation, les risques, les limites, la decision prudente et la prochaine action.

## 7. Boucle de progression

La boucle est : collecter, tester, mesurer, corriger, documenter. `progress_loop.py` journalise cette iteration dans `reports/`, sans toucher a `data/`.
