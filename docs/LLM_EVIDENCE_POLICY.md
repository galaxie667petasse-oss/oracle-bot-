# Politique des preuves LLM V10

Toute information transmise au LLM devient une preuve typee.

Champs principaux :

- `evidence_id`
- `candidate_id`
- `fixture_id`
- `type`
- `source_reference`
- `observed_at`
- `effective_at`
- `valid_as_of`
- `reliability`
- `content_hash`
- `content`

## Validation semantique

Un JSON conforme au schema ne suffit pas. Le validateur rejette :

- preuve inconnue ;
- preuve d'une autre fixture ;
- preuve observee apres `as_of` ;
- agent Fresh Information sans preuve squad/tactical/news ;
- juge qui ignore un hard veto ;
- tentative de modifier probabilite, cote, EV ou stake.

Les preuves futures et les injections de prompt sont traitees comme hard veto.

