# Elo Model V10

Formule :

```text
expected_home = 1 / (1 + 10 ^ (-(rating_home + home_advantage - rating_away) / scale))
new_rating = old_rating + K * margin_multiplier * (actual - expected)
```

Parametres initiaux :

- rating initial : 1500 ;
- scale : 400 ;
- K : 22 ;
- avantage domicile : 55 points ;
- regression intersaison : 0.75 vers 1500 ;
- marge plafonnee : 1.8.

Conversion 1X2 :

- le modele Elo binaire produit une probabilite home/non-home ;
- la probabilite de nul est une baseline explicite dependant de l'ecart Elo ;
- le reste de la masse est reparti home/away selon l'esperance binaire.

Cette conversion est une baseline documentee, pas une preuve definitive.
