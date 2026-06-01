# Politique archive test/demo

Avant une collecte reelle, archiver les artefacts de test dans `reports/test_archive_*`.

`test_archive_manager.py` deplace les fichiers de travail puis recree un ledger et un store snapshots vides.

```bash
python test_archive_manager.py --status
python test_archive_manager.py --archive-and-reset --label before_real_june
python test_archive_manager.py --list-archives
```

Regles :

- ne jamais effacer sans archive ;
- ne jamais modifier `data/` ;
- garder `reports/` ignore par Git ;
- ne pas melanger test, demo, fictif et reel dans le meme ledger.
