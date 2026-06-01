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
