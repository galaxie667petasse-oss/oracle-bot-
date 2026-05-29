# Politique de promotion des modeles

## Objectif

La gouvernance V7.0 empeche un modele, un segment ou une regle fragile de devenir un signal actif sans preuve temporelle, CLV positive, calibration acceptable et validation statistique robuste.

La politique ne cree aucun pick automatique. Elle decide seulement si un signal peut etre rejete, surveille, observe ou affiche comme aide prudente a la decision.

## Niveaux de promotion

1. `rejected` : signal invalide, negatif ou bloque par un gate.
2. `watchlist` : signal fragile a surveiller, sans usage decisionnel.
3. `observation` : signal descriptif interessant, encore non activable.
4. `candidate` : candidat robuste a verifier humainement.
5. `active_shadow_only` : suivi en shadow, sans affichage decisionnel.
6. `active_decision_support` : peut etre affiche comme contexte prudent.
7. `production_allowed` : autorise comme signal explicable, jamais comme pari automatique.

## Conditions minimales

Un modele ou segment ne peut passer candidat que si :

- ROI test 2024+ strictement positif ;
- CLV disponible et positive ;
- validation non negative ;
- sample test superieur ou egal a 1000 ;
- aucune fuite post-match ;
- Brier/log loss non pires que le marche si le signal est probabiliste ;
- ECE et MCE acceptables ;
- bootstrap ROI 5e percentile strictement positif ;
- intervalle de confiance ROI ne contient pas 0 si disponible ;
- p-value ajustee par multiple testing significative quand plusieurs strategies sont testees ;
- absence de degradation recente 2025 ;
- seuil non choisi sur le test.

## Regles de blocage

- ROI test negatif ou nul : jamais candidat.
- CLV absente ou negative : jamais candidat.
- Validation positive mais test negatif : rejected.
- Sample test inferieur a 300 : preuve insuffisante.
- Sample test inferieur a 1000 : observation maximum.
- Calibration ECE trop elevee : rejected ou watchlist maximum.
- Bootstrap ROI p05 inferieur ou egal a 0 : rejected ou watchlist maximum.
- Correction multiple testing echouee : rejected ou watchlist maximum.
- Fuite post-match : rejected.
- Seuil choisi sur test : rejected.

## Pourquoi ROI court terme ne suffit pas

Le marche football pre-match est efficient. Un ROI positif sur quelques centaines de picks peut venir du bruit, d'un segment choisi apres coup ou d'un calendrier favorable. Meme 1000 picks peuvent etre insuffisants si l'edge attendu est de 0.5% a 1%.

## Pourquoi CLV est prioritaire

La Closing Line Value mesure si le prix pris etait meilleur que le prix final du marche. Avoir pris 2.10 quand la closing line finit a 2.00 est positif. Avoir pris 1.90 quand elle finit a 2.00 est negatif. Sans CLV positive, le ROI court terme n'est pas une preuve robuste.

## Multiple testing

Tester 67 strategies augmente fortement la chance de faux positif. Les p-values non corrigees sont insuffisantes. La gouvernance V7.0 applique Benjamini-Hochberg quand plusieurs strategies disposent de p-values.

## Bootstrap et Monte Carlo

Le bootstrap ROI donne une distribution plausible du ROI sous re-echantillonnage. Si le percentile 5% est inferieur ou egal a 0, le signal reste observation. Monte Carlo sert a visualiser la dispersion et le drawdown, pas a promettre une rentabilite.

## Kelly

Kelly ne cree pas d'edge. Il ne fait que dimensionner une mise si l'edge existe deja. Dans ce projet, Kelly reste reserve a la simulation et ne peut pas promouvoir un signal.

## Telegram et production

Meme `production_allowed` ne signifie pas pari automatique. Cela signifie seulement que le bot peut afficher un signal comme element de decision, avec explication, limites et prudence.

Tant que le projet n'a aucun signal robuste active, Telegram et Railway restent hors scope.

## V7.2 Understat xG quality gate

Un signal xG Understat reste `lab_only` tant que toutes les conditions suivantes ne sont pas reunies :

- quality verdict `exploitable_rolling_xg` ;
- saisons attendues presentes et completeness suffisante ;
- rolling features calculees sans utiliser le match courant ;
- Brier et log loss avec xG non pires que le marche no-vig ;
- ROI edge test strictement positif ;
- sample edge test suffisant ;
- CLV positive disponible ;
- bootstrap ROI p05 strictement positif ;
- correction multiple testing reussie ;
- aucune degradation recente et aucun seuil choisi sur test.

Le nouvel export EPL 2020-2025 a vocation a corriger l'ancien export 1520 lignes incomplet, mais un dataset propre ne suffit pas a promouvoir un signal. Meme si le xG ameliore legerement la probabilite, il reste observation si le ROI test est negatif ou si la CLV est absente.

## V7.3 Jointure multi-ligues

La promotion est bloquee si la jointure externe est insuffisante. Un dataset Understat complet mais mal joint peut produire des features sur les mauvais matchs ou reduire le test a un sous-echantillon non representatif.

Seuils :

- `excellent` : join rate >= 90% ;
- `exploitable_prudent` : 75% a 90% ;
- `fragile` : 50% a 75% ;
- `insuffisant` : moins de 50%, modeling bloque.

Pour La Liga, un join rate autour de 39.89% impose `join_quality=insuffisant`, `modeling_allowed_by_join_quality=false` et `join_blocks_promotion=true`. Les alias peuvent ameliorer la jointure, mais ils doivent etre documentes et audites. Une suggestion fuzzy ne suffit pas a promouvoir un signal.

## V7.5 Big Five xG et CLV readiness

La gouvernance Big Five ajoute deux garde-fous :

- `multi_league_xg_aggregator.py` resume les ligues disponibles, la quality, la jointure, le Brier/log loss marche vs xG, le ROI edge test, le sample et les raisons de rejet.
- `clv_readiness_report.py` dit si les closing odds necessaires sont presentes dans la feature matrix.

Regles supplementaires :

- Big 5 xG positif sans CLV calculable = observation/watchlist maximum.
- Join quality inferieure a 75% = modele bloque ou observation stricte.
- Sample edge test inferieur a 1000 = pas de promotion.
- Brier/log loss legerement meilleurs sans ROI test robuste = observation technique.
- ROI positif avec sample faible = bruit possible, pas preuve.
- CLV readiness `indisponible` bloque tout candidat robuste.

Les aliases Serie A et Ligue 1 servent uniquement a fiabiliser la jointure future. Ils ne creent aucun signal. Un statut `production_allowed`, s'il existe un jour, resterait une aide decisionnelle explicable, jamais un pari automatique.

## V7.6 Closing odds recovery

La recuperation closing odds devient un gate explicite :

- `closing_odds_probe.py` peut confirmer si le CSV source contient des colonnes closing, sans calculer de CLV ;
- `clv_readiness_report.py --closing-probe` distingue la CLV calculable maintenant de la CLV calculable apres enrichissement ;
- `features_closing_enricher.py` ne peut produire qu'une preview dans `reports/`, jamais remplacer `data/features_modern.csv` ;
- si la source closing est absente, douteuse ou non mappee au marche pris, toute promotion reste bloquee.

Un xG qui ameliore legerement Brier/log loss peut etre utile pour la calibration, mais il ne prouve pas un edge betting. Sans CLV positive fiable, ROI test positif, sample suffisant, bootstrap favorable, calibration correcte, correction multiple testing et stabilite annuelle, le statut maximum reste observation/watchlist. Telegram, Railway et tout pick automatique restent exclus.

## V7.7 Partial CLV pipeline

Les colonnes `C_LTH` et `C_LTA` permettent seulement une CLV partielle H2H home/away. Cette CLV est utile pour diagnostiquer le prix pris contre la closing line, mais elle ne valide pas :

- les draws si `C_LTD` est absent ;
- les totals si les colonnes Over/Under closing sont absentes ;
- BTTS si les colonnes exactes sont absentes ;
- les strategies globales multi-marches.

Une strategie H2H couverte peut etre mieux observee avec cette CLV, mais elle reste bloquee si le sample CLV est inferieur a 1000, si la CLV moyenne est non positive, si la couverture est faible, ou si les autres gates statistiques echouent. La CLV partielle ne peut jamais etre extrapolee a un marche non couvert.

## V7.8 Closing Column Forensics

Une colonne closing detectee par nom ne suffit pas pour passer le gate CLV. `closing_odds_probe.py` doit classer la colonne `decimal_odds_plausible` apres profil des valeurs. Les verdicts `numeric_but_not_odds`, `mostly_empty`, `text_or_code` et `unknown` bloquent le calcul CLV.

Si `C_LTH` ou `C_LTA` existent mais contiennent des valeurs non plausibles comme cotes decimales, `features_closing_enricher.py` doit les rejeter et `clv_readiness_report.py` doit exposer le bloqueur. Aucun signal ne peut etre promu sur une colonne closing seulement nommee, non validee.

## V8.0 Shadow Mode & Manual CLV Capture

Le shadow mode est un journal de preuve live, pas un systeme d'activation. Un signal shadow peut etre ajoute avec une cote prise et une raison, puis complete plus tard avec une closing odds manuelle fiable. La CLV est calculee uniquement si cette closing odds est une cote decimale > 1.01.

Regles de promotion :

- sample shadow < 1000 : promotion impossible ;
- CLV shadow absente ou non positive : promotion impossible ;
- ROI shadow positif sans CLV robuste : observation seulement ;
- CLV shadow positive avec ROI court terme negatif : observation seulement ;
- aucune strategie shadow ne peut devenir recommandation active sans gouvernance historique complete et revue humaine.

## V8.1 Shadow UX, Daily Workflow & Evidence Dashboard

V8.1 rend le shadow mode utilisable au quotidien, mais ne change pas les gates de promotion :

- `shadow_workflow.py` orchestre init, templates, rapport et benchmark ;
- `shadow_ledger.py --add-csv` permet d'ajouter plusieurs observations en une fois ;
- `shadow_templates.py` cree les CSV candidats, closing et resultats ;
- `results_manual_import.py` complete les resultats sans toucher aux closing odds ;
- `shadow_clv_report.py` ajoute ROI unite, profit, max drawdown et splits par ligue, marche, side, strategie, bookmaker et mois ;
- `dashboard_builder.py` affiche la section Shadow Mode Evidence.

Regles V8.1 :

- sample shadow inferieur a 1000 : `not_validated` ou `observation_only` ;
- CLV absente : `not_validated` ;
- CLV moyenne non positive : promotion bloquee ;
- ROI shadow non positif : promotion bloquee ;
- drawdown eleve : analyse humaine obligatoire ;
- meme si CLV et ROI deviennent positifs avec un gros sample, le statut maximum est `candidat a analyse approfondie`.

Le workflow quotidien ne cree aucune mise, n'utilise pas Kelly et ne publie rien sur Telegram.

## V8.2 Evidence Gate

V8.2 ajoute `evidence_gate.py` comme couche de decision centrale. Elle ne promeut rien automatiquement. Elle classe la preuve en :

- `not_started` ;
- `collecting_evidence` ;
- `insufficient_evidence` ;
- `promising_but_unvalidated` ;
- `blocked` ;
- `ready_for_deep_review`.

Regles :

- `ready_for_deep_review` signifie seulement analyse humaine approfondie ;
- sample shadow < 1000 bloque toute promotion ;
- CLV coverage < 80% bloque toute conclusion ;
- CLV moyenne <= 0 bloque ;
- ROI shadow <= 0 bloque ;
- ledger quality `invalid` bloque ;
- Big 5 xG sans CLV reste observation.

Aucun statut V8.2 ne declenche Telegram, Railway, staking ou mise automatique.
