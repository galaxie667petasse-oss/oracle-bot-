# Human Intake Guardrails

La saisie manuelle est utile seulement si elle reste stricte.

Garde-fous V8.6 :

- notes contenant test/demo/fictif/simulation/synthetic signalees ;
- `source=demo` bloque une collecte reelle ;
- near-close sans taken correspondant bloque ;
- taken sans near-close reste incomplet ;
- bookmaker absent bloque ou demande revue ;
- captured_at absent bloque ;
- resultats fictifs dans le ledger bloquent ;
- cotes identiques partout demandent une verification humaine.

Commande :

```bash
python real_observation_guard.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --output reports/real_observation_guard.json --html reports/real_observation_guard.html
```

Le guard ne prouve rien. Il empeche surtout une mauvaise collecte de contaminer les observations reelles.
## V8.7 phase-aware guardrails

Les controles humains dependent maintenant de la phase :

- en `pre_match`, une taken odds sans near-close correspondante est un warning normal ;
- en `near_close`, la near-close devient attendue ;
- en `post_match`, les resultats deviennent attendus ;
- une near-close sans taken odds correspondant reste un blocage ;
- les lignes demo/test/fictives doivent rester archivees avant une vraie collecte.

Commande utile :

```bash
python real_observation_guard.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --phase pre_match --output reports/real_observation_guard.json --html reports/real_observation_guard.html
```

Le guard ne valide aucune performance. Il protege seulement la qualite de collecte.

## V8.8 API snapshots

Avec The Odds API, un store peut contenir plusieurs bookmakers, marches et issues. Les garde-fous humains deviennent :

- selectionner peu d'observations via `odds_shadow_selector.py` ;
- garder `is_near_close=true` pour le matching closing seulement ;
- utiliser `real_observation_guard.py --scope ledger` pour la collecte reelle ;
- ne pas confondre un snapshot disponible avec une observation shadow retenue.
