# Evaluation LLM V10

Le benchmark mock compare :

- A : aucun LLM ;
- B : Luna seulement ;
- C : Terra panels ;
- D : cascade complete ;
- E : agents separes, benchmark couteux seulement.

Mesures :

- schema valide ;
- preuves valides ;
- hallucinations ;
- hard veto respecte ;
- candidats rejetes ;
- candidats acceptes ;
- appels ;
- cout estime ;
- latence.

Commande :

```bash
python app.py llm evaluate --dataset tests/fixtures/llm_eval --mock --ablation
python app.py llm benchmark-routing --dataset tests/fixtures/llm_eval --mock
```

Le dataset synthetique couvre EV negative, cote perimee, bookmaker unique, modeles en desaccord, calibration faible, prompt injection, preuve inventee, future leakage, fixture reportee, mapping incorrect et budget epuise.

