# Operational Shadow Pipeline

Le pipeline Phase 5 orchestre des scans prematch en shadow mode. Il ne publie rien, ne place aucune mise et ne modifie pas les probabilites calculees par Python.

```mermaid
flowchart TD
  A["Railway cron every 5 minutes"] --> B["SchedulerDispatcher"]
  B --> C["v10_scheduled_jobs due queue"]
  C --> D["Provider refresh and raw snapshots"]
  D --> E["Freshness policy"]
  E --> F["Feature and prediction jobs"]
  F --> G["Candidate generation"]
  G --> H["Deterministic gate"]
  H --> I["Experiment arm A: deterministic only"]
  H --> J["LLM mock/replay/paid gated review"]
  J --> K["Experiment arm B: deterministic + LLM"]
  K --> L["Near-close capture"]
  L --> M["Results, settlement, CLV"]
```

Commandes utiles:

```powershell
python app.py fixtures discover --days 3 --dry-run
python app.py fixtures schedule --fixture-id <uuid> --dry-run
python app.py scan prematch --fixture-id <uuid> --mock-llm --dry-run
python app.py scan due --mock-llm --dry-run
python app.py demo operational-shadow-end-to-end --mock --json
```

Toutes les commandes persistantes requierent `--apply`.

