# Oracle Football Bot V4

Bot Telegram cloud pour analyser des matchs de football avec vraies cotes, IA Groq et scoring prudent.

## Fonctionnement

```text
Telegram -> Railway worker -> The Odds API -> Agents Groq -> Score confiance/danger/value -> Top picks Telegram
```

Fallback info-only : API-Football et football-data.org peuvent trouver des fixtures, mais la V4 refuse de créer des picks sans vraies cotes.

## Variables Railway

Obligatoires :

```env
TELEGRAM_TOKEN=
CHAT_ID=
GROQ_KEYS=
ODDSPAPI_KEY=
```

Optionnelles :

```env
FOOTBALL_KEY=
FOOTBALL_DATA_KEY=
BANKROLL=100
SCAN_HOUR=9
MAX_MATCHES=12
MAX_ANALYZED=10
```

## Commandes Telegram

```text
/start
/scan
/scan force
/resultats
/stats
```

## Déploiement Railway

Le fichier `railway.json` lance :

```bash
python oracle_bot_v4.py
```

Railway doit avoir **1 replica seulement**, sinon Telegram peut renvoyer une erreur 409 Conflict.

## Stratégie V4

- pas de cotes inventées
- score danger
- confiance plafonnée
- ligues secondaires pénalisées
- cotes hautes pénalisées
- value ajustée par danger
- moins de biais victoire domicile
