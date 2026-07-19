# Near-Close and CLV

La near-close line est la derniere cote valide observee avant `event_time`.

Qualite:

- `EXACT_OR_VERY_NEAR`: 0 a 5 minutes avant kickoff;
- `ACCEPTABLE`: 5 a 15 minutes;
- `STALE`: plus de 15 minutes;
- `MISSING`: aucune cote valide;
- `REJECTED_FUTURE_ODDS`: cote observee apres kickoff, jamais utilisee.

CLV odds:

```text
clv_odds_pct = decimal_odds_taken / decimal_odds_closing - 1
```

La cote de cloture ne doit jamais entrer dans une decision prematch.

