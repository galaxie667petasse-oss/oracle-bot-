# Real Matchday Workflow

V8.6 separe les demonstrations et la collecte reelle.

Routine recommandee :

1. Archiver les tests si le workspace contient des lignes demo/test/fictives.
2. Creer un pack matchday.
3. Remplir les taken odds reelles.
4. Remplir les near-close reelles 5-10 minutes avant kickoff.
5. Lancer un full-dry-run.
6. Appliquer seulement apres verification humaine.
7. Importer les resultats.
8. Lire `shadow_clv_report.py` et `evidence_gate.py`.

Commandes :

```bash
python test_archive_manager.py --archive-and-reset --label before_real_june
python matchday_pack.py --date 2026-06-01 --output-dir reports/matchday_2026_06_01
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-apply
```

Tout reste en observation shadow. Une near-close sans taken odds correspondant est un blocage, pas une preuve.

## V8.7 phases

Le workflow est maintenant phase-aware :

- `pre_match` : remplir seulement les taken odds. Near-close absente = normal.
- `near_close` : remplir les near-close reelles et relancer le dry-run.
- `post_match` : remplir les resultats et generer les rapports.

Le full-dry-run utilise un staging temporaire. Il montre ce qui serait ecrit dans le store odds et le ledger sans modifier les fichiers reels.

```bash
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase pre_match
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase near_close
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase post_match
```

## V8.8 scope ledger

Pour une collecte reelle alimentee par API, le store `reports/odds_snapshots.csv` peut contenir beaucoup de cotes non selectionnees. Le guard doit donc verifier le ledger quand on veut savoir si les observations retenues ont une near-close :

```bash
python real_observation_guard.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --phase pre_match --scope ledger --output reports/real_observation_guard.json --html reports/real_observation_guard.html
```

Le scope snapshots reste utile pour auditer un store complet, mais il ne doit pas bloquer les observations shadow non selectionnees.
