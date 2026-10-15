# Import Legacy V9

L'import legacy est volontairement prudent. Il decouvre les sources historiques, affiche leur taille et leur type probable, puis permet un dry-run cible par fichier. Il ne lance aucun import global aveugle.

## Decouverte

```powershell
python app.py legacy discover
python app.py legacy discover --root . --max-bytes 20000000
```

Les dossiers inspectes sont limites au depot courant. Les dossiers sensibles ou volumineux sont signales, pas charges integralement.

## Dry-run

```powershell
python app.py legacy import --source tests/fixtures/providers/api_football/odds_sample.json --dry-run
```

Le dry-run affiche :

- type detecte ;
- taille ;
- nombre d'objets ;
- fixtures normalisables ;
- cotes valides ;
- erreurs ;
- estimation d'espace.

## Application

Application explicite seulement :

```powershell
python app.py legacy import --source tests/fixtures/providers/api_football/odds_sample.json --provider api_football --apply
```

Sans `--apply`, aucune ecriture DB n'est effectuee. Les fichiers sources V9 ne sont jamais modifies.

## Limites Phase 2

- pas d'import massif automatique de `oracle_db*.json` ;
- pas de lecture integrale d'un gros JSON ;
- pas de mapping approximatif uniquement par nom d'equipe ;
- les formats inconnus restent documentes comme `unknown`.
