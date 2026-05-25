# Politique de promotion des modeles

## Objectif

La gouvernance V6.7 empeche un modele, un segment ou une regle fragile de devenir un signal actif sans preuve temporelle. Elle s'applique au marche no-vig, aux regles Oracle, aux segments historiques, aux modeles ML et aux futurs enrichissements xG.

La politique ne cree aucun pick automatique. Elle decide seulement si un signal peut etre rejete, surveille, observe ou affiche comme aide prudente a la decision.

## Conditions minimales

Un modele ou segment ne peut passer de simple observation a agent actif que si :

- le test 2024+ est positif ;
- la validation est non negative ;
- le sample test est idealement superieur ou egal a 1000, minimum 300 ;
- aucune fuite post-match n'est utilisee ;
- la calibration est acceptable ;
- Brier score et log loss ne sont pas pires que le marche pour un modele probabiliste ;
- la stabilite annuelle est acceptable ;
- le drawdown reste raisonnable ;
- il n'y a pas de degradation forte en 2025 ;
- `project_audit.py` est OK ;
- un rapport central local a ete genere.

## Niveaux de promotion

1. `rejected` : signal invalide, negatif ou a bloquer.
2. `watchlist` : signal fragile a surveiller, sans usage decisionnel.
3. `observation` : signal descriptif interessant, encore non activable.
4. `candidate` : candidat robuste a verifier humainement.
5. `active_shadow_only` : suivi en shadow, sans affichage decisionnel.
6. `active_decision_support` : peut etre affiche comme contexte prudent.
7. `production_allowed` : autorise comme signal explicable, jamais comme pari automatique.

## Regles de blocage

- ROI test 2024+ negatif ou nul : pas de candidat robuste.
- Validation positive mais test negatif : signal invalide.
- Train positif mais validation/test negatifs : suspicion de surapprentissage.
- Test absent : statut maximum fragile.
- Sample test inferieur a 300 : statut maximum echantillon faible.
- Fuite post-match : invalidation immediate.
- 2025 negatif : penalite de degradation recente.

## Modeles probabilistes

Pour un modele ML, la calibration compte davantage que l'accuracy brute. Le modele doit etre compare au marche no-vig avec :

- Brier score ;
- log loss ;
- calibration buckets ;
- ROI des edges choisis sur validation puis mesures sur test ;
- drawdown et volume.

Un modele positif en validation mais negatif sur test 2024+ est invalide.

## Telegram et production

Meme `production_allowed` ne signifie pas pari automatique. Cela signifie seulement que le bot peut afficher le signal comme element de decision, avec explication, limites et prudence.

Tant que le projet n'a aucune strategie robuste positive, Telegram et Railway restent hors scope.
