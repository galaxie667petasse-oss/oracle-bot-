# V9.1 Evidence Acceleration Strategy

V9.1 ajoute une boucle de preuve plus rapide sans rendre le bot plus agressif.

Les leviers:

- catalogue des sources externes;
- detection de schemas historiques opening/closing;
- import CLV historique si les cotes sont plausibles;
- collecte near-close batch en dry-run;
- resultats API-Football optionnels;
- proof dashboard central.

Blocages maintenus:

- sample shadow < 1000;
- CLV live absente ou faible;
- closing odds non fiables;
- resultats manquants;
- multiple testing;
- Big 5 xG sans CLV.

Statut maximum sans live shadow suffisant: `historical_evidence_only` ou `insufficient_evidence`.

Commande principale:

```powershell
python report_runner.py --proof --skip-dashboard
```

Cette commande ne lance pas de reseau et ne modifie pas `data/`.
