# Calibration V10

Methodes implementees :

- Platt scaling binaire ;
- temperature scaling multiclass.

Regles :

- calibration entrainee sur validation chronologique ;
- test final jamais utilise pour ajuster ;
- fallback non calibre si l'echantillon est trop petit ;
- rejet si la calibration degrade le log loss.

Les intervalles Phase 3 sont heuristiques : ils combinent historique limite, convergence et incertitude simple. Ils ne sont pas presentes comme garanties frequentistes.
