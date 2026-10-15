# Material Changes

`MaterialChangeDetector` compare deux fingerprints de candidat/fixture et decide si un rescan ou une revue LLM est utile.

Evenements materiels:

- report ou changement d'heure;
- changement de statut;
- mouvement de cote significatif;
- mouvement de probabilite fair;
- changement de probabilite modele;
- incertitude modifiee;
- lineup confirmee;
- qualite qui passe a `FAIL`;
- hard veto apparu.

Seuils par defaut:

- `MATERIAL_ODDS_RELATIVE_CHANGE=0.03`
- `MATERIAL_FAIR_PROBABILITY_CHANGE_PP=0.015`
- `MATERIAL_MODEL_PROBABILITY_CHANGE_PP=0.02`
- `MATERIAL_UNCERTAINTY_CHANGE=0.10`

Un changement non materiel ne relance pas le LLM.

