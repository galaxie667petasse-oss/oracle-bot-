# Architecture V10

V10 separe la collecte, les calculs deterministes, les agents LLM et la publication.

```mermaid
flowchart TD
    A["External football APIs"] --> B["Raw ingestion"]
    B --> C["Raw payload archive and replay"]
    C --> D["Canonical normalization"]
    D --> E["Data quality gate"]
    E --> F["Feature engineering"]
    F --> G["Statistical probability models"]
    G --> H["Market odds normalization"]
    H --> I["Candidate generation"]
    I --> J["Deterministic filters"]
    J --> K["LLM specialist agents"]
    K --> L["Contradiction and veto engine"]
    L --> M["Final reasoning judge"]
    M --> N["Signal ledger"]
    N --> O["Telegram preview or publisher"]
    N --> P["Settlement, CLV and evaluation"]
```

## Frontieres

- `v10.odds` : cotes decimales, probabilites implicites, no-vig proportionnel, EV, CLV.
- `v10.data_quality` : statut PASS, PASS_WITH_WARNINGS, FAIL, STALE, CONFLICTING.
- `v10.candidates` : filtrage deterministe avant tout LLM.
- `v10.risk` : paper betting uniquement, caps conservateurs, aucune action bookmaker.
- `v10.settlement` : resultat officiel par marche, sans LLM.
- `v10.agents` : schema et mocks agents.
- `v10.final_judge` : juge deterministe de demo, refuse ou WATCH sans inventer.
- `app.py` : CLI additive, separee du `main.py` historique.

## Etat actuel

La couche V10 est additive et offline. La persistance relationnelle initiale est disponible sous `v10/db`, avec Alembic, repositories, replay provider et requetes temporelles. L'API interne, le scheduler distribue, les modeles statistiques reels et les agents LLM reels restent a construire dans les phases suivantes.

## Persistence Phase 2

```mermaid
flowchart LR
    A["Replay file or provider payload"] --> B["v10_raw_api_payloads"]
    B --> C["Pydantic input models"]
    C --> D["Canonical observations"]
    D --> E["Providers, competitions, seasons, teams, fixtures"]
    D --> F["Bookmakers, markets, selections"]
    F --> G["v10_odds_snapshots append-only"]
    G --> H["Temporal repositories as_of"]
    H --> I["Future features and candidate engine"]
```

Responsabilites :

- `v10.config` masque les secrets et refuse la configuration production dangereuse.
- `v10.db.models` declare les tables relationnelles V10 et les contraintes.
- `v10.db.repositories` concentre l'idempotence, les upserts et les requetes temporelles.
- `v10.replay.engine` stocke le raw payload puis reconstruit les entites canoniques.
- `v10.normalization` mappe API-Football et The Odds API depuis des payloads locaux.
- `v10.quality_db` reconstruit un rapport de qualite depuis la base.

## Statistical Engine Phase 3

```mermaid
flowchart TD
    A["Historical fixtures and results"] --> B["TemporalDatasetBuilder"]
    B --> C["football_features_v1 snapshots"]
    C --> D["Elo models"]
    C --> E["Poisson independent model"]
    C --> F["Dixon-Coles experimental model"]
    D --> G["Market probabilities"]
    E --> H["Score distribution"]
    F --> H
    H --> G
    G --> I["Calibration"]
    I --> J["Ensemble"]
    J --> K["Market comparison and EV"]
    K --> L["Candidates dry-run / paper-only"]
```

Responsabilites :

- `v10.statistics.types` definit `TemporalContext`, fixtures historiques, rows dataset, distributions et predictions.
- `v10.statistics.dataset` construit les lignes d'apprentissage en ordre chronologique et exclut les donnees futures.
- `v10.statistics.features` genere forme, repos, H2H limite, Elo pre-match et missingness.
- `v10.statistics.elo`, `poisson` et `dixon_coles` produisent des probabilites sans LLM.
- `v10.statistics.markets` derive 1X2, double chance, draw no bet, totals et BTTS depuis la matrice de scores.
- `v10.statistics.calibration`, `ensemble` et `backtest` separent validation, combinaison et evaluation walk-forward.

Les tables Phase 3 `v10_model_versions`, `v10_feature_snapshots`, `v10_score_distributions`, `v10_statistical_predictions`, `v10_calibration_models` et `v10_evaluation_runs` permettent de versionner les predictions. Le chemin CLI reste additif: `app.py dataset`, `app.py model`, `app.py predict`, `app.py backtest` et `app.py demo statistical-end-to-end`.

## LLM Shadow Orchestration Phase 4

```mermaid
flowchart TD
    A["Candidates deterministic filters"] --> B["CandidateEvidencePacket"]
    B --> C["Luna FAST triage"]
    C --> D["Terra Quantitative Integrity panel"]
    C --> E["Terra Match Context panel"]
    C --> F["Fresh Information skipped without evidence"]
    D --> G["Devil's Advocate"]
    E --> G
    G --> H["Portfolio panel if multiple candidates"]
    H --> I["Sol FINAL rare judge"]
    I --> J["ContradictionEngine"]
    J --> K["gate deterministe"]
    K --> L["Shadow decision only"]
```

Luna filtre le volume avec reasoning low. Terra regroupe les roles compatibles en panels. Sol est reserve aux finalistes top K et ne modifie aucun chiffre deterministe. Le gate deterministe bloque toute ineligibilite, cote perimee, EV non positive, preuve invalide ou hard veto. Le mode par defaut reste `LLM_ENABLED=false`, `LLM_ALLOW_PAID_CALLS=false`, budgets a zero.
## V10 Phase 5 - Operations

```mermaid
flowchart TD
  A["Railway cron tick"] --> B["SchedulerDispatcher"]
  B --> C["PostgreSQL due jobs"]
  C --> D["Provider adapters and replay"]
  D --> E["Temporal snapshots"]
  E --> F["Statistical predictions"]
  F --> G["Candidate engine"]
  G --> H["Deterministic gate"]
  H --> I["Shadow experiment: deterministic"]
  H --> J["Shadow experiment: deterministic + LLM"]
  J --> K["Near-close, settlement, CLV"]
  K --> L["Read-only API and dashboard"]
```

Le web service `v10.api:app` est read-only. Le scheduler est un processus court, appele toutes les cinq minutes, qui quitte apres son tick. Aucun worker permanent ni Redis n'est requis dans cette phase.
