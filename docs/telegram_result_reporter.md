# V9.8 Telegram Result Reporter

Objectif: publier en lecture seule le resultat d'une observation shadow settled. Le message explique le settlement; il ne cree aucune recommandation.

## Preview

```bash
python telegram_result_reporter.py --ledger reports/shadow_ledger.csv --shadow-id sh_20260617210447_2ee081d9 --dry-run
```

La preview est ecrite dans `reports/telegram_results_preview.md`.

## Envoi reel

```bash
python telegram_result_reporter.py --ledger reports/shadow_ledger.csv --shadow-id sh_20260617210447_2ee081d9 --allow-send --plain-text
```

`--allow-send` est obligatoire. Sans ce flag, le notifier reste en dry-run.

## Message Ghana attendu

```text
📌 ORACLE SHADOW LAB — RÉSULTAT OBSERVATION
Match : Ghana - Panama
Observation : h2h home
Cote prise : 2.26
Near-close : 2.26
CLV : 0.00%
Score final : Ghana 1 - 0 Panama
Résultat shadow : win
Profit shadow : +1.26u
Statut preuve : sample insuffisant
Aucune mise. Laboratoire local uniquement.
```

## Tracking

Le reporter utilise `reports/telegram_published_results.json` pour eviter les doublons. `--force` permet une republication volontaire apres verification humaine.

Une observation sans `result_status` settled n'est pas publiee. Une observation deja publiee n'est pas republiee sans `--force`.

## Garde-fous

- Read-only uniquement.
- Aucun Telegram reel dans les tests.
- Aucun token affiche ou logge.
- Aucun reseau sans `--allow-send`.
- Aucun pick automatique.
- Aucune mise.
- `lab_only=true`.
- `can_influence_picks=false`.
