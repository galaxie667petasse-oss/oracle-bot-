# Windows Scheduler Setup V9.6

Les scripts Windows sont prepares dans `scripts/`, mais aucune tache n'est installee automatiquement.

Scripts:

- `scripts/oracle_daily_morning.ps1`
- `scripts/oracle_pre_close.ps1`
- `scripts/oracle_post_match.ps1`
- `scripts/install_windows_tasks.example.ps1`

Variables d'environnement:

- `ORACLE_ALLOW_NETWORK=true` autorise les scans reseau dans les scripts.
- `ORACLE_ALLOW_TELEGRAM_SEND=true` autorise l'envoi Telegram read-only.

Sans ces variables, les scripts restent en dry-run ou en mode local prudent. Les tokens et cles API doivent rester dans l'environnement Windows, jamais dans Git ni dans ces scripts.
