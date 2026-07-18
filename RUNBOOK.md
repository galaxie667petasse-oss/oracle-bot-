# Runbook V10

## Provider indisponible

Utiliser replay ou fixtures locales. Ne pas crasher toute l'application si `API_FOOTBALL_KEY` manque.

## 429 ou rate limit

Arreter le job, journaliser le provider et respecter `Retry-After` dans le futur adaptateur HTTP.

## Telegram en panne

Conserver preview local. Aucun envoi sans `--allow-send` et sans configuration valide.

## Mode LLM indisponible

Basculer deterministic-only ou mock-agent. Marquer la decision comme non validee par LLM.

## Budget atteint

Stopper les appels LLM, garder les candidats deterministes, ne pas promouvoir de signal.

## Donnees incoherentes

Retourner FAIL ou CONFLICTING dans data quality. Le juge final doit refuser.

## Commandes utiles

```bash
python app.py doctor
python app.py config validate
python app.py db upgrade
python app.py db status
python app.py db doctor
python app.py demo end-to-end
python app.py demo end-to-end --json
python app.py demo postgres-end-to-end
python app.py replay provider --file tests/fixtures/providers/api_football/fixtures_sample.json --provider api_football --dry-run
python app.py legacy discover
python scripts/secret_scan.py --root .
```

## Migration echouee

Verifier `DATABASE_URL`, puis relancer :

```bash
python app.py db status
python app.py db doctor
```

Si la base Railway est nouvelle, appliquer `python app.py db upgrade`. Ne pas lancer de downgrade sur une base contenant des donnees utiles sans sauvegarde.

## Replay bloque

Le replay utilise un lock deterministe pour eviter deux imports concurrents. Si un job echoue, relancer le meme fichier : raw payloads et odds snapshots sont dedupliques par hash.

## Donnees temporelles

Toute erreur de datetime naive doit etre traitee comme bug de normalisation. Les requetes de decision doivent passer par les fonctions `as_of`, jamais par la derniere cote globale.

## Modele statistique non convergent

Pour Poisson ou Dixon-Coles, conserver le modele en DRAFT ou FAILED. Ne pas activer automatiquement une version non convergente.

Commandes utiles :

```bash
python app.py model train --model poisson_independent_v1 --from 2024-01-01 --to 2024-12-31 --dry-run
python app.py model train --model dixon_coles_v1 --from 2024-01-01 --to 2024-12-31 --dry-run
python app.py demo statistical-end-to-end --json
```

## Incident LLM

Verifier l'etat :

```bash
python app.py llm doctor
python app.py llm budget status
python app.py llm cache status
python app.py llm prompts validate
```

Si le budget est epuise, le systeme doit retourner `UNREVIEWED`, `WATCH` ou `NO_BET`, jamais `SHADOW_ACCEPTED` automatiquement.

Si une preuve est rejetee, relancer en mock/replay :

```bash
python app.py llm analyze --candidate-id cand_shadow_accept --mock --shadow
python app.py demo llm-shadow-end-to-end --mock --json
```

Ne jamais activer `LLM_ALLOW_PAID_CALLS=true` en production sans budget, smoke FAST et verification de la disponibilite modele.

## Fuite temporelle suspectee

Verifier que la commande utilise bien `--as-of` ou une fenetre chronologique. Rejouer le dataset avec un `--to` plus ancien et comparer le fingerprint. Les features doivent venir de `TemporalDatasetBuilder` et non d'une lecture directe de la derniere ligne disponible.

## Calibration degradee

Si Platt ou temperature scaling degrade la log loss hors echantillon, conserver la probabilite brute. Le calibrateur Phase 3 applique deja un fallback prudent sur echantillon faible.
