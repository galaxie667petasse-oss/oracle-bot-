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

## V8.0 : capture manuelle en shadow mode

Comme `data/MATCHES.csv` ne fournit pas actuellement de cotes closing decimales exploitables, la voie prudente est de collecter les preuves live en shadow mode :

1. noter la cote prise avec `shadow_ledger.py` ;
2. attendre la closing line reelle ;
3. importer cette closing line avec `closing_manual_import.py` ;
4. relire le rapport `shadow_clv_report.py`.

Cette capture manuelle ne recommande aucune mise. Elle permet seulement de savoir si les observations Oracle prenaient de meilleurs prix que le marche final. Meme une CLV positive reste insuffisante avec un petit sample.

## V8.1 : workflow quotidien et durcissement securite

V8.1 ajoute un workflow plus simple autour de cette capture :

1. initialiser `reports/shadow_ledger.csv` avec `shadow_workflow.py --init` ;
2. remplir un template d'observations shadow ;
3. importer les observations avec `shadow_ledger.py --add-csv` ;
4. generer un template de closing odds ;
5. importer uniquement des closing odds decimales reelles ;
6. importer les resultats manuels ;
7. lire le rapport CLV shadow et le dashboard evidence.

Le rapport distingue les observations sans closing, sans resultat, avec CLV positive ou negative, et les segments trop petits. Les seuils restent stricts : sous 1000 observations shadow, la preuve est insuffisante. Une CLV moyenne positive peut justifier une analyse plus profonde, pas une activation automatique.
