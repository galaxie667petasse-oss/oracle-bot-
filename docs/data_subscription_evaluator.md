# V9.4 - Data Subscription Evaluator

`data_subscription_evaluator.py` estime si un abonnement data est utile pour la couverture operationnelle.

Il ne recommande jamais un abonnement comme preuve d'edge. Le message central reste:

> un abonnement augmente la couverture et l'automatisation, pas la preuve d'edge.

La recommandation reste `no_paid_needed_yet` tant que le workflow n'a pas au moins 30 observations completes, sauf blocage de quota evident.

Commande:

```bash
python data_subscription_evaluator.py --usage-reports reports --output reports/data_subscription_evaluator.json --html reports/data_subscription_evaluator.html
```
