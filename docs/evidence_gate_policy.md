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
