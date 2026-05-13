# Stratégie Oracle V4.1

## Pourquoi la V4 sortait zéro pick

La V4 était trop prudente. Elle calculait une value très négative car elle était trop ancrée sur la probabilité bookmaker et pénalisait fortement le danger.

Résultat typique :

```text
Confiance 52%
Danger 43%
Value -19
```

Techniquement propre, mais pas exploitable.

## Ce que V4.1 change

### 1. Scanner plus large

Avant :

```text
12 matchs
```

Maintenant recommandé :

```text
MAX_MATCHES=60
MAX_ANALYZED=20
```

Le bot récupère plus de matchs et plus de marchés.

### 2. Préfiltrer les marchés

Avant :

```text
match -> IA -> 1 pari
```

Maintenant :

```text
match -> tous les marchés -> préfiltre automatique -> IA seulement sur les meilleurs
```

Marchés étudiés :

- victoire domicile
- nul
- victoire extérieur
- over 2.5
- under 2.5
- BTTS oui
- BTTS non

### 3. Moins de biais victoire simple

Le Top limite les H2H avec :

```env
MAX_H2H_TOP=2
```

Donc le bot ne doit plus sortir 5 victoires simples d'affilée.

### 4. Score value plus exploitable

Le score combine :

```text
EV estimée
edge IA vs marché
type de marché
préfiltre
danger
```

La pénalité danger est moins écrasante en `balanced`.

### 5. Modes

- `safe` : qualité stricte, moins de picks
- `balanced` : recommandé
- `aggressive` : plus de picks, plus risqué

## Réglage conseillé maintenant

```env
ORACLE_MODE=balanced
MAX_MATCHES=60
MAX_ANALYZED=20
TOP_PICKS=5
MIN_CONFIDENCE=58
MIN_VALUE_SCORE=-8
MAX_H2H_TOP=2
```

## Si encore pas assez de picks

Passe temporairement à :

```env
ORACLE_MODE=aggressive
MAX_MATCHES=80
MAX_ANALYZED=25
MIN_CONFIDENCE=56
MIN_VALUE_SCORE=-14
```

## Si trop de picks faibles

Passe à :

```env
ORACLE_MODE=safe
MIN_CONFIDENCE=64
MIN_VALUE_SCORE=-2
MAX_H2H_TOP=1
```

## Prochaine vraie amélioration

La prochaine étape n'est pas d'ajouter 20 agents. C'est :

1. collecter les résultats WIN/LOSS
2. mesurer ROI et winrate par marché
3. ajuster les seuils par marché
4. ajouter CLV / closing line value
5. stocker dans SQLite ou Postgres
