# V4.2 - auto-settle et apprentissage

## Boucle quotidienne

1. Le bot verifie les picks encore ouverts.
2. Il cherche le score final avec API-Football.
3. Si API-Football ne trouve rien, il tente football-data.org.
4. Il marque WIN ou LOSS si le match est termine.
5. Il recalcule les statistiques.
6. Il ajuste les scores futurs par marche, tranche de cote et type de ligue.

## Ce que le bot apprend

- marche : h2h, draw, total, btts
- tranche de cote : low, mid, high, very_high
- groupe de ligue : major, volatile, other
- ROI et winrate de chaque groupe

## Quand l apprentissage devient utile

- 10 picks : signal faible
- 30 picks : premiers signes
- 50 picks : ajustements utilisables
- 100 picks : calibration plus serieuse

Si les noms des equipes ne correspondent pas entre les APIs, le bot laisse le pick en pending au lieu d inventer un resultat.
