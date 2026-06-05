# Evidence Gate Policy V8.2

## Principe

`evidence_gate.py` repond a une question simple : avons-nous assez de preuve pour aller plus loin ? La reponse reste negative tant que CLV, sample, qualite ledger et validation historique ne sont pas suffisants.

Le statut maximum est `ready_for_deep_review`. Il n'existe pas de statut qui autorise une mise automatique.

## Statuts

- `not_started` : aucun rapport exploitable.
- `collecting_evidence` : collecte en cours.
- `insufficient_evidence` : sample, CLV ou resultats insuffisants.
- `promising_but_unvalidated` : signal interessant mais non valide.
- `blocked` : qualite invalide, CLV negative ou blocage majeur.
- `ready_for_deep_review` : assez d'elements pour une revue humaine approfondie.

## Blockers principaux

- CLV absente ;
- CLV coverage < 80% ;
- sample shadow < 1000 ;
- CLV moyenne <= 0 ;
- ROI shadow <= 0 ;
- ledger quality `invalid` ;
- results missing ;
- closing missing ;
- Big5 sans CLV ;
- multiple testing non confirme ;
- pas de validation live suffisante.

## Regles strictes

- sample < 1000 : non valide ;
- CLV absente : non valide ;
- CLV moyenne non positive : bloque ;
- ROI positif avec CLV absente ou negative : bruit possible ;
- CLV positive avec ROI court terme negatif : observation seulement ;
- meme avec tout positif, analyse approfondie requise avant toute decision.

Le gate ne conseille aucune mise et ne publie rien.

## Sources de cotes V8.3

L'evidence gate peut etre informe par les rapports odds, mais ses seuils ne changent pas :

- snapshots sans near-close : preuve CLV absente ;
- near-close partiel : diagnostic seulement ;
- CLV sample < 1000 : non valide ;
- CLV moyenne non positive : bloque ;
- source mal documentee : analyse approfondie requise.

Les adaptateurs de cotes ne court-circuitent jamais la gouvernance.

## V8.4 Intake QA

L'audit intake peut ameliorer la qualite du ledger, mais il ne remplace pas les gates :

- `taken_without_near_close` indique une CLV manquante ;
- `near_close_without_taken` indique une capture non exploitable ;
- `ledger_without_closing` garde le statut non valide ;
- `ledger_without_result` empeche l'analyse ROI.

Un intake propre permet de continuer la collecte, pas de conclure.

## V8.8 API odds

Le scanner The Odds API, la selection shadow et le workflow near-close alimentent les rapports de preuve, mais ne changent pas les seuils :

- une selection API sans near-close reste non valide ;
- une near-close sans taken odds correspondant est inutilisable ;
- `--scope ledger` dans le guard verifie les observations retenues ;
- sample < 1000 et CLV non robuste bloquent toute promotion.

## V8.9 lifecycle

`evidence_gate.py --lifecycle reports/event_lifecycle.json` ajoute :

- blocker si `near_close_overdue` ;
- blocker si `result_overdue` ;
- warning si near-close due soon ;
- warning si trop de pending closing par rapport aux observations completes.

Un pending closing futur en pre-match reste une insuffisance normale, pas une preuve ni une erreur dure.

## Lien V8.5

`llm_analyst_contract.py` doit respecter ce gate. Si `evidence_gate.py` ne renvoie pas `ready_for_deep_review`, la restitution maximale reste `non valide` ou `observation shadow`. Le schema `restitution_schema.py` force les actions interdites a rester visibles.
## V9.1 Historical Evidence

`evidence_gate.py` accepte maintenant `--historical-clv` et `--proof-dashboard`.

Nouveau statut possible: `historical_evidence_only`. Il signifie qu'une preuve historique existe, mais que la preuve live shadow reste insuffisante. Ce statut ne permet aucune activation automatique.

Regles maintenues: sample shadow < 1000, CLV absente, CLV moyenne <= 0, ROI <= 0 ou ledger de mauvaise qualite bloquent la promotion.
## Telegram read-only

V9.5 ajoute deux champs de gouvernance:

- `telegram_read_only_allowed=true` pour autoriser une lecture privee du laboratoire ;
- `telegram_live_pick_allowed=false` pour interdire toute activation de signal via Telegram.

Un message Telegram ne peut pas lever les blockers. Si CLV, sample, resultats, calibration ou multiple testing sont insuffisants, le statut reste `non valide`.
