# Sources gratuites ou peu couteuses de cotes

## CSV manuel

Le CSV manuel est la voie la plus sure pour demarrer gratuitement :

- l'utilisateur note la cote prise ;
- l'utilisateur note un snapshot near-close si disponible ;
- le pipeline verifie que les valeurs sont des cotes decimales plausibles ;
- le matching vers le shadow ledger reste local.

## API-Football

API-Football peut fournir des cotes selon le plan disponible. Dans Oracle Bot :

- l'adaptateur ne fait aucun reseau sans `--allow-network` ;
- la cle vient de l'environnement ;
- la cle n'est jamais affichee ;
- les tests utilisent une fixture locale.

Cette source peut aider a tester la couverture quotidienne, mais elle ne garantit pas une closing historique parfaite.

## The Odds API

The Odds API est utile pour snapshots courants et tests multi-bookmakers :

- aucun reseau sans `--allow-network` ;
- credits limites sur les plans gratuits ;
- historique souvent payant ;
- prudence sur la notion de closing.

## Sources historiques

Pour une CLV robuste, chercher une source documentee :

- Pinnacle closing ;
- Bet365 closing si schema clair ;
- Football-Data closing si les colonnes sont documentees et valides ;
- The Odds API historical odds si budget ;
- datasets Kaggle avec closing odds documentees.

Sans closing fiable, le projet reste un centre d'analyse et de preuve shadow, pas un systeme valide.
