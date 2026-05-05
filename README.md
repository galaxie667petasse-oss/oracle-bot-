# ⚽ Football Oracle Bot

Bot Telegram d'analyse de paris sportifs — 9 agents IA Groq.

## Installation

1. Copier `.env.example` en `.env` et remplir les valeurs
2. `pip install -r requirements.txt`
3. `python bot.py`

## Déploiement Railway

1. Push sur GitHub
2. Connecter Railway à ton repo
3. Ajouter les variables d'environnement dans Railway
4. Deploy !

## Commandes

- `/scan` — Lance le scan du jour
- `/stats` — Statistiques & win rate
- `/resultats` — Paris en attente
- `/bankroll 150` — Changer la bankroll
- `/help` — Aide

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| TELEGRAM_TOKEN | Token du bot (@BotFather) |
| CHAT_ID | Ton chat ID (@userinfobot) |
| GROQ_KEYS | Clés API Groq séparées par virgules |
| SCAN_HOUR | Heure du scan auto (défaut: 9) |
| BANKROLL | Bankroll de départ (défaut: 100) |
