# Feature Engineering V10

Schema : `football_features_v1`.

Regle temporelle : pour une fixture cible, seules les donnees avec `event_time < target.event_time` et disponibles avant `decision_as_of` peuvent entrer dans les features. Le contrat `TemporalContext` porte `fixture_id`, `decision_as_of`, `data_cutoff` et `training_cutoff` pour rendre cette limite explicite.

Features implementees :

- historique global : matchs, points/match, difference de buts/match ;
- forme : points et goal diff sur 5/10 ;
- domicile/exterieur : buts domicile, buts exterieur ;
- repos : jours depuis dernier match ;
- calendrier : matchs dans les 7/14/30 jours ;
- Elo pre-match ;
- H2H faible : count et points moyens, jamais dominant ;
- missingness : indicateurs historique, repos et H2H manquants.

Les tirs, xG, corners ou lineups restent exclus tant qu'ils ne sont pas horodates comme disponibles avant le match.
