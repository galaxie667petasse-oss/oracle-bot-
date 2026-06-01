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
