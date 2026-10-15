# Utilisation locale ORACLE V11

État actuel et preuves : [mission 2](V11_MISSION2.md). Configuration sécurisée des API et hébergement : [guide privé](V11_PRIVATE_SETUP.md).

## Installation

Depuis le checkout V11, avec Python 3.12 :

```powershell
python -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt -r requirements-v11.txt
.\.venv312\Scripts\python.exe -m pytest tests/test_v11.py -q
```

Ne pas mélanger l'environnement avec l'ancien checkout. `requirements-v11.txt` est optionnel pour V10 ; les modèles V11 penaltyblog en ont besoin.

Installer `requirements-v11-py312.lock.txt` pour les versions exactes désormais validées sous Windows et sous Linux en CI. Le fichier `requirements-v11-windows-py312.lock.txt` antérieur est conservé.

## Import et analyse

```powershell
python -m v11 --ledger variable/oracle-v11.sqlite3 import-snapshot CHEMIN_SNAPSHOT.json
python -m v11 --ledger variable/oracle-v11.sqlite3 analyze --day 2026-10-16 --penaltyblog
python -m v11 --ledger variable/oracle-v11.sqlite3 history
python -m v11 --ledger variable/oracle-v11.sqlite3 status
```

Le JSON suit `v11/contracts.py` ; toutes les dates doivent avoir un fuseau. Exemple minimal **explicitement synthétique**, à adapter à une date future pour analyser :

```json
{
  "captured_at": "2026-10-15T12:00:00Z",
  "provenance": "synthetic",
  "fixtures": [{
    "fixture_id": "synthetic:example",
    "source": "synthetic",
    "competition": "synthetic",
    "home": "Équipe synthétique A",
    "away": "Équipe synthétique B",
    "kickoff": "2026-10-16T18:00:00Z",
    "observed_at": "2026-10-15T12:00:00Z",
    "status": "SCHEDULED",
    "quotes": []
  }],
  "history": []
}
```

Une ligne d'historique a `match_id`, `competition`, `home`, `away`, `kickoff`, `result_observed_at`, `home_goals`, `away_goals`. Une cote a `source`, `bookmaker`, `market`, `selection`, `odds`, `observed_at`, `provider_updated_at`, et `line` pour totals/handicap. Le minimum courant pour calculer les modèles est 30 résultats, avec les deux équipes présentes ; ce seuil autorise un calcul, **pas une validation statistique**.

Marchés : `match_winner` (home/draw/away), `double_chance` (1x/12/x2), `both_teams_to_score` (yes/no), `total_goals` (over/under), `asian_handicap` (home/away), `correct_score` (par exemple 2:1), `draw_no_bet` (home/away). Ligne AH du point de vue de l'équipe sélectionnée. Lignes multiples de 0,25 ; scores finaux réglementaires seulement. AET/PEN/PST/ABD restent en attente ; pas de remboursement déduit automatiquement d'un report.

Un snapshot est une photographie complète du lot à analyser. L'analyse utilise la dernière photographie importée, sans fusion implicite entre photographies ou identifiants fournisseurs. Pour plusieurs compétitions, préparer un snapshot consolidé vérifié ; ne pas supposer que des collectes successives sont automatiquement agrégées. Les noms doivent être canoniques et identiques entre historique et fixture ; aucune jointure floue n'est autorisée.

## Collecte réelle bornée

Définir les clés existantes par le mécanisme de secrets de l'environnement ; ne jamais les passer dans la ligne de commande ni les enregistrer dans Git.

```powershell
python -m v11 collect --provider the_odds_api --sport soccer_france_ligue_one --allow-network --output variable/odds-unique.json
python -m v11 collect --provider api_football --day 2026-10-16 --allow-network --output variable/fixtures-unique.json
```

- Sans `--allow-network` ou sans clé : refus, aucun appel fournisseur.
- Clés attendues : `THE_ODDS_API_KEY`, `API_FOOTBALL_KEY`.
- The Odds API : uniquement 1N2, cinq clés FR explicites, coût documentaire estimé d'un crédit au maximum par requête. Pas d'historique payant, pas de retry automatique.
- Le normaliseur sait également importer totals/BTTS depuis un payload fourni. Les autres marchés sont acceptés dans les snapshots manuels ; leur collecte live n'est pas encore raccordée.
- Cache V10 persistant de deux minutes, quota connu et réserve critique respectés, verrou fournisseur, une requête maximum par commande, compteurs enregistrés. Un quota épuisé doit être réévalué sur preuve de réinitialisation, pas contourné.
- Les réponses non-200 et erreurs de payload échouent sans afficher clé, URL ou corps fournisseur.
- `--output` doit être un nouveau fichier. Cache isolé : `variable/v11-provider-cache.sqlite3`, quatre migrations historiques réutilisées.
- La collecte des odds crée un snapshot sans historique : elle produit donc une abstention tant qu'un historique vérifié n'est pas consolidé.
- API-Football fixtures est normalisé séparément. Les résultats FT de ses réponses sont consolidables via `build-snapshot` ci-dessous, avec le normaliseur historique réutilisé. Les statistiques enrichies et leur alimentation automatique restent à raccorder.

Aucun abonnement acheté. Coût engagé par cette mission : 0 €. Le client ne souscrit pas à une offre et ne peut vérifier les conditions du compte sans clé. Conserver une offre gratuite ; toute offre payante au-delà du budget ou activation de facturation nécessite une autorisation distincte.

## Consolider des sources réellement observées

Un résultat passé récupéré aujourd'hui est connu aujourd'hui, pas à la date du match. La consolidation préserve `fetched_at` comme date de disponibilité ; elle permet un prochain calcul pré-match et ne crée pas de preuve historique rétroactive.

Préparer un mapping explicite, après vérification des compétitions et des noms :

```json
{"competitions": {"api_football:61": "soccer_france_ligue_one"}, "teams": {}}
```

La clé API-Football et le sport ci-dessus sont un exemple de configuration à vérifier, pas une jointure attestée par cette mission. Les noms identiques sont utilisés tels quels ; remplir `teams` pour chaque différence vérifiée, sans rapprochement flou automatique.

```powershell
python -m v11 build-snapshot --odds-file variable/odds-unique.json --results-file variable/resultats-date1.json --results-file variable/resultats-date2.json --mapping MON_MAPPING.json --output variable/snapshot-consolide-neuf.json --provenance real_provider
```

Les fichiers de résultats sont les enveloppes de collecte API-Football pour des dates passées, obtenues par `collect --provider api_football --day DATE_PASSEE`. La commande ne fait aucun appel réseau, exige un fichier de sortie neuf et importe le snapshot consolidé dans le ledger. Les hashes des payloads et des mappings sont conservés. Seuls les FT réglementaires des compétitions explicitement mappées sont inclus ; AET/PEN ne sont pas reconvertis en scores réglementaires. Ne déclarer `real_provider` que pour de vraies réponses collectées ; utiliser `synthetic` pour les jeux de test.

## Résultats, simulation et validation

```powershell
python -m v11 record-result --prediction-id HASH --home 2 --away 1 --source NOM_SOURCE
python -m v11 apply-results --file variable/resultats-apres-match.json --mapping MAPPING_FIXTURES.json
python -m v11 paper-report --model poisson_independent_v1 --min-ev 0.05
python -m v11 paper-report --model poisson_independent_v1 --min-ev 0.05 --closing-snapshot CLOTURE.json
python -m v11 evaluate SNAPSHOT.json --competition ID_COMPETITION --penaltyblog
python -m v11 evaluate SNAPSHOT.json --competition ID_COMPETITION --quotes-file ARCHIVE_COTES.json --penaltyblog
python -m v11 backup variable/oracle-v11-copie-neuve.sqlite3
```

`record-result` ajoute un événement, y compris une correction ultérieure explicitement sourcée. `apply-results` lit une collecte API-Football après match et un mapping `{"fixtures":{"ID_FIXTURE_ORACLE":"api_football:ID_FOURNISSEUR"},"teams":{}}` ; il exige noms et kickoff cohérents avec les prédictions scellées et n'infère pas le score réglementaire depuis AET/PEN. Un lot rejoué est idempotent. Le dernier événement est utilisé pour la simulation ; tous restent visibles. La simulation choisit la première analyse par fixture et au plus un 1N2 selon la politique fixée ; elle ne transforme jamais une abstention en pari réel. Fenêtre maximale affichée et calculée : les 500 dernières analyses. Ne pas comparer des politiques optimisées sur le même test.

La CLV utilise strictement même source, bookmaker, marché, sélection et ligne ; observation postérieure à la décision mais antérieure au kickoff, timestamp fournisseur proche de la clôture. Elle est définie comme `cote_analyse / cote_cloture - 1`. Pas de CLV calculée à partir d'une cote publiée après kickoff. Les remboursements sont exclus du dénominateur du ROI. Pas d'intervalle bootstrap avant dix jours distincts.

L'évaluation chronologique est par compétition, avec embargo, timestamps de disponibilité des résultats, entraînement/calibration/test séparés, température choisie uniquement sur calibration, fixtures simultanées groupées et test non recouvrant. Baseline marché seulement si trois cotes contemporaines horodatées d'un même bookmaker sont disponibles via l'API Python `archived_quotes` ou `--quotes-file`. Les fixtures de l'archive de cotes doivent avoir les mêmes identifiants que les matchs historiques ; aucune jointure implicite n'est faite. Les deltas modèle/marché portent sur les mêmes matchs. Pas d'ensemble automatique.

`data/Matches.csv` historique ne contient pas les timestamps de disponibilité : ne pas convertir la date du match en preuve d'observation. Le script `scripts/v11_archive_smoke.py` lit cette archive sans la modifier, teste les six modèles et marque explicitement l'absence de preuve temporelle. Ce script ne produit pas de backtest de stratégie.

## Interface privée

Définir `INTERNAL_API_TOKEN` par un mécanisme de secrets, puis :

```powershell
python -m uvicorn v11.api:app --host 127.0.0.1 --port 8000
```

Ouvrir `/v11`. La page publique ne contient aucune donnée ; chaque endpoint `/api/v11/*` exige le jeton, y compris en environnement local. La clé du navigateur reste en mémoire de page, sans stockage persistant. L'import est possible par la CLI ou `POST /api/v11/snapshots` authentifié ; aucun upload n'est proposé dans l'interface actuelle. La case penaltyblog est activée par défaut et conserve les trois baselines V10. Le bouton d'analyse utilise uniquement le snapshot local ; il ne contacte aucun bookmaker ni LLM. `v10.api:app` conserve le montage compatible pour les usages historiques ; le conteneur privé V11 utilise l'application V11 seule.

Le téléphone réel n'a pas été testé sur réseau privé : seul le viewport mobile est vérifié localement. Pour un accès depuis téléphone, préparer un hébergement privé ou un tunnel privé authentifié ; ne pas exposer le port directement sur Internet. Le jeton doit être robuste et transporté via HTTPS dès qu'il sort du loopback.

## Hébergement préparé, non déployé

`Dockerfile.v11` sépare le serveur web du bot historique et utilise un utilisateur non root. Son build, son démarrage, l'authentification, la persistance après redémarrage et la copie/restauration de ledger ont été validés en CI ; voir le bilan mission 2 pour le SHA exact. Persister `/app/variable` dans un volume sauvegardé ; enregistrer le jeton et les clés dans les secrets de l'hébergeur. Le PC personnel peut alors rester éteint, mais la validation de disponibilité nécessite encore un hébergeur choisi et un déploiement privé autorisé.

Architecture proposée : un service web privé, une collecte ponctuelle CLI à quota borné, un volume SQLite et des sauvegardes chiffrées hors machine. Pas de planification ni compte d'hébergement créé. La disponibilité 24/7 sur hébergeur et son tarif restent non vérifiés ; le build et les contrôles du conteneur sont désormais prouvés en CI.
