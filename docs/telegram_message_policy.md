# Politique Messages Telegram

Les messages Telegram V9.5 sont des lectures privees du laboratoire Oracle.

Formulations autorisees:

- observation shadow ;
- watchlist ;
- non valide ;
- preuve insuffisante ;
- CLV en attente ;
- resultat en attente ;
- aucune mise ;
- laboratoire local.

Formulations bloquees dans les messages:

- bankroll ;
- stake ou staking ;
- Kelly ;
- all-in ;
- promesse de rentabilite ;
- suggestion de mise ;
- activation automatique.

Chaque message doit rappeler que l'information est une observation laboratoire. Une observation avec ROI positif ou CLV positive reste non valide si le sample, la gouvernance, la calibration ou la correction multiple testing ne sont pas satisfaits.

Regles de format V9.5.1:

- les valeurs dynamiques comme `shadow_id`, noms d'equipes et statuts techniques echappent les caracteres Markdown sensibles ;
- les underscores non echappes ne doivent pas etre emis dans les IDs ou champs techniques en mode Markdown ;
- `--plain-text` ou `TELEGRAM_PARSE_MODE=""` supprime `parse_mode` et garde un message lisible ;
- un fallback plain text ne change jamais la decision, ne cree aucun pick et ne peut pas influencer les observations.
