# Closing Odds Forensics

## Pourquoi le nom d'une colonne ne suffit pas

Une colonne nommee `C_*`, `close` ou `closing` peut ressembler a une cote closing, mais son nom ne prouve rien. Elle peut contenir une probabilite, un identifiant, un code bookmaker, un score, une valeur normalisee ou une donnee mal documentee. Oracle Football Bot refuse donc de calculer une CLV tant que les valeurs ne ressemblent pas clairement a des cotes decimales.

## Reconnaître une cote decimale

Une cote decimale exploitable est numerique, strictement superieure a 1.01, et se trouve presque toujours dans un intervalle raisonnable comme `1.01-20`. Des valeurs entre `0` et `1`, des `0/1`, des textes, des dates ou des nombres tres grands ne doivent pas etre convertis en cotes sans preuve externe.

## Regle V7.8

`closing_odds_probe.py` profile les colonnes suspectes avant toute recommandation. Une colonne est utilisable seulement si le verdict est `decimal_odds_plausible`. Si une colonne est detectee par nom mais classee `numeric_but_not_odds`, `mostly_empty`, `text_or_code` ou `unknown`, `features_closing_enricher.py` la rejette et ecrit la raison dans la preview.

Cette phase ne modifie ni `data/MATCHES.csv`, ni `data/features_modern.csv`, ni la DB. Elle produit uniquement des rapports locaux dans `reports/`.

## Sources closing a chercher ensuite

- Pinnacle closing documente et stable.
- Bet365 closing documente.
- Football-Data closing si les colonnes sont documentees et si la periode post-2025-07-23 est verifiee.
- The Odds API historical odds si un budget est accepte.
- Donnees historiques OddsPortal seulement si l'usage est legalement et techniquement exploitable.
- Datasets Kaggle avec closing odds documentees et schema clair.

Sans closing fiable, le projet reste un outil d'analyse prudent. Il ne devient pas un systeme valide de picks.
