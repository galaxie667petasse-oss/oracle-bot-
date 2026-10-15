# Poisson et Dixon-Coles V10

## Poisson independent

Le modele estime :

```text
lambda_home = avg_home_goals * home_attack * away_defence_weakness
lambda_away = avg_away_goals * away_attack * home_defence_weakness
```

Les forces sont shrinkees vers la moyenne de ligue avec un pseudo-echantillon configurable.

La matrice de score est :

```text
P(i,j) = Poisson(lambda_home, i) * Poisson(lambda_away, j)
```

Elle est calculee jusqu'a `max_goals=10`, puis renormalisee avec une `tail_mass` documentee.

## Dixon-Coles

La correction tau agit seulement sur :

- 0-0 ;
- 0-1 ;
- 1-0 ;
- 1-1.

Le parametre `rho` est recherche sur une grille bornee `[-0.20, 0.20]`. Le modele est marque convergent seulement si la log-vraisemblance reste finie.

Dixon-Coles est experimental dans cette phase : il est compare a Poisson, jamais suppose meilleur.
