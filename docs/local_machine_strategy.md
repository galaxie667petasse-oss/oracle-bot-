# Strategie machine locale

Le pipeline actuel fonctionne en local sans GPU.

- CPU/RAM/SSD suffisent pour les imports CSV, audits, reports, sklearn leger et dashboards.
- Le GPU/VRAM n'est utile que pour un futur fine-tuning LLM, pas pour le pipeline actuel.
- Commencer leger reste la meilleure strategie : CSV propres, validation, CLV, evidence gate.
- `sklearn` suffit pour les modeles locaux actuels.
- QLoRA ou LoRA peuvent attendre une vraie raison : volume de donnees labellisees, format stable, besoin d'un style d'analyse reproductible.

Priorite materielle :

1. SSD fiable ;
2. RAM suffisante pour CSV volumineux ;
3. sauvegarde Git propre ;
4. pas de secrets dans le depot ;
5. GPU seulement si une phase LLM locale devient necessaire.
