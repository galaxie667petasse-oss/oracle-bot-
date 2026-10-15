# Model Versioning V10

Tables ajoutees :

- `v10_model_definitions` ;
- `v10_model_versions` ;
- `v10_feature_snapshots` ;
- `v10_score_distributions` ;
- `v10_statistical_predictions` ;
- `v10_calibration_models` ;
- `v10_evaluation_runs`.

Chaque model version conserve :

- code version ;
- dataset fingerprint ;
- periode d'entrainement ;
- competitions ;
- marches ;
- hyperparametres ;
- metriques ;
- artefact JSON limite ;
- statut.

`--apply` persiste une version en `DRAFT`. L'activation demande `model activate --apply` et refuse les echantillons trop petits.
