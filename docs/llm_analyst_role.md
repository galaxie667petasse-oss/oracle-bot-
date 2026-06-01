# Role du LLM analyste

Le LLM analyste explique, il ne prouve pas.

- Le modele statistique mesure les probabilites, le Brier, le log loss, la CLV et le ROI.
- Les donnees alimentent le pipeline.
- Le RAG peut actualiser un contexte si une source fiable existe.
- Un futur SFT peut apprendre le format de restitution.
- LoRA ou QLoRA restent des pistes tardives si un besoin reel apparait.
- L'agent orchestre les outils.
- Le LLM explique les mesures et les limites.

Regles fixes :

- ne jamais inventer une cote ;
- ne jamais calculer un edge non fourni ;
- ne jamais transformer une observation en conseil de mise ;
- ne jamais produire une decision plus forte que `evidence_gate.py` ;
- si CLV absente, dire que la CLV est absente ou insuffisante ;
- si sample < 1000, dire que le sample est insuffisant.
