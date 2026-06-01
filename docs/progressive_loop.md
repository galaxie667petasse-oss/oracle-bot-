# Boucle progressive

La progression Oracle suit une boucle courte :

1. collecter une donnee propre ;
2. tester la validation locale ;
3. mesurer les effets ;
4. corriger les erreurs ;
5. documenter la decision.

`progress_loop.py` sert de journal local :

```bash
python progress_loop.py --init
python progress_loop.py --add --phase collecter --title "Ajout snapshot manuel" --status done --notes "source manuelle"
python progress_loop.py --summary
```

Le journal reste dans `reports/`. Il ne modifie pas `data/`, `oracle_db.json`, Telegram ou Railway.

La boucle ne cherche pas a forcer un signal. Elle sert surtout a refuser plus proprement, corriger plus vite et accumuler une preuve mesurable.
