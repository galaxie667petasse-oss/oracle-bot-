# Provider Quotas

`ProviderQuotaManager` enregistre uniquement les headers reellement recus. Il n'invente pas de limite.

Priorite en quota faible:

1. resultats et settlement;
2. matchs a moins de 90 minutes;
3. finalistes;
4. near-close odds;
5. fixtures a moins de 24 heures;
6. rafraichissements de fond.

Si le quota est critique, les appels facultatifs sont bloques et une alerte operationnelle est creee en base. Aucun provider reel n'est appele en CI.

