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

## V9.2 Same-Day Evidence Inputs

Les odds API-Football enrichies peuvent accelerer la creation d'observations shadow, mais elles ne changent pas la politique de preuve:

- une taken odds enrichie n'est pas une CLV;
- une near-close doit etre capturee separement;
- le resultat peut etre matche par `source_event_id`;
- sample, CLV moyenne, ROI, drawdown et audit qualite restent obligatoires;
- statut maximum avant preuve suffisante: observation ou watchlist.

Le proof dashboard accepte `--same-day` et `--near-close-today` pour afficher ce qui a ete trouve aujourd'hui.
## V9.4

L'acceleration de preuve passe par trois boucles:

1. collecter des observations futures via next-days;
2. capturer near-close dans la bonne fenetre;
3. importer les resultats post-match.

Les donnees Football-Data gratuites peuvent accelerer les tests ROI historiques, mais pas la CLV si aucune closing explicite plausible n'est presente.
