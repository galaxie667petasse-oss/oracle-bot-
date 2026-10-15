# Phase 3 Data Availability

Audit realise le 2026-07-18 sans charger integralement les gros dumps JSON.

## Sources locales

| Source | Format | Taille | Periode | Volume | Scores FT | Scores HT | Cotes | Stats avancees | Utilite |
| --- | --- | ---: | --- | ---: | --- | --- | --- | --- | --- |
| `data/MATCHES.csv` | CSV | 43.6 MB | 2000-07-28 -> 2025-06-01 | 230557 lignes | 230554 | 175977 | 227527 1X2 | tirs/cadres partiels 113929 | Elo, Poisson, calibration, backtest |
| `data/features_modern.csv` | CSV | 207.9 MB | 2015-01-01 -> 2025-06-01 | 528066 lignes | labels deja derives | non source brute | oui | features V9 | evaluation descriptive, pas source brute Phase 3 |
| `oracle_db*.json` | JSON | 46 MB -> 1.94 GB | 2000/2015 -> 2025 selon fichier | non charge | probablement derive de CSV | inconnu | picks/scans | non verifie | replay futur avec parser streaming |
| `external_data/epl_fbref_2024_2025/match_reports.jsonl` | JSONL | 2.98 MB | 2024-2025 probable | non compte ici | rapports locaux | inconnu | non | FBref potentiel | utile seulement apres horodatage fiable |
| `external_data/soccerdata_cache/*.json` | JSON | ~0.45-0.55 MB par fichier | 2020-2024 | cache ligues | probable | inconnu | non | non confirme | import futur prudent |
| `reports/api_football_*` | JSON/CSV | quelques Ko -> 11.7 MB | Juin 2026 | scans/replays | resultats partiels | non | odds API | non | replay provider V10 |
| `tests/fixtures/providers/*` | JSON | < 2 KB | synthetique/anonymise | petit | fixtures/odds | non | oui | non | tests V10 |

## Champs confirmes dans `data/MATCHES.csv`

- Competition : `Division`, 38 codes.
- Date : `MatchDate`, aucun manquant observe.
- Equipes : `HomeTeam`, `AwayTeam`, aucun manquant observe.
- Score final : `FTHome`, `FTAway`, 3 lignes manquantes.
- Resultat : `FTResult`, 3 lignes manquantes.
- Mi-temps : `HTHome`, `HTAway`, 54580 manquants.
- Cotes 1X2 : `OddHome`, `OddDraw`, `OddAway`, 3030 manquants.
- Statistiques de match : tirs, tirs cadres, fautes, corners, cartons, mais elles sont post-match et interdites comme features pre-match directes.

## Risques

- `features_modern.csv` contient deja des labels et features V9 : utile pour audit, mais risque de melange post-traitement si utilise comme source brute.
- Les JSON `oracle_db*.json` sont volumineux ; import futur uniquement streaming.
- Les reports contiennent des artefacts de runs et ne doivent pas etre commites.
- Les stats avancees ne sont pas horodatees comme observees avant match ; elles restent exclues des features Phase 3.
- Les xG ne sont pas confirmes comme donnees historiques fiables dans les sources auditees.

## Utilite par modele

- Elo : `data/MATCHES.csv` suffit avec date, equipes, score, competition.
- Poisson : `data/MATCHES.csv` suffit avec score final et domicile/exterieur.
- Dixon-Coles : `data/MATCHES.csv` suffit pour correction scores faibles, echantillon large.
- Calibration : `data/MATCHES.csv` + cotes 1X2 permettent validation temporelle ; calibrateurs par ligue exigent un seuil minimal futur.
- Backtest : possible chronologiquement, mais les cotes doivent etre utilisees selon disponibilite pre-match documentee.
