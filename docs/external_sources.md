# External Dataset Lab

Ce document liste des sources candidates pour enrichir Oracle Football Bot. Aucune source n'est integree automatiquement. Toute source doit etre profilee localement, jointe prudemment, puis testee en train/validation/test avant d'influencer une decision.

## 1. xgabora / Football-Data / ClubElo

- Couverture: historique large, plusieurs ligues, 2000-2025 selon le fichier disponible.
- Colonnes utiles: resultats, scores, cotes 1X2, over/under, Elo, formes simples, parfois stats de match.
- Avantages: base principale actuelle, volume massif, cotes disponibles, jointure deja maitrisee.
- Limites: les features terrain restent simples; le marche no-vig reste difficile a battre.
- Complexite integration: faible, deja en place.
- Risque fuite: moyen si stats finales du match sont utilisees pour predire le meme match.
- Priorite: tres haute comme base principale.
- Verdict: base principale actuelle.

## 2. Kaggle / FBref Premier League 2024-2025 riche

- Couverture: souvent une ligue et une saison, par exemple EPL 2024-2025.
- Colonnes utiles: xG, xGA, tirs, tirs cadres, possession, lineups, stats joueurs/equipes si le dataset est riche.
- Avantages: laboratoire prioritaire pour comprendre si xG et stats avancees ajoutent du signal.
- Limites: couverture etroite, noms d'equipes a normaliser, cotes souvent absentes.
- Complexite integration: moyenne; profilage et plan de jointure requis.
- Risque fuite: eleve si xG/tirs finaux sont utilises comme features pre-match.
- Priorite: haute pour laboratoire.
- Verdict: utiliser comme enrichissement ou laboratoire, pas comme remplacement de xgabora.

## 3. StatsBomb Open Data

- Couverture: competitions et saisons limitees, event data tres riche.
- Colonnes utiles: evenements, tirs, xG, positions, joueurs, lineups selon competition.
- Avantages: excellent pour apprendre la structure des event data et tester des concepts avances.
- Limites: pas de couverture marche complete, cotes absentes, competitions limitees.
- Complexite integration: elevee.
- Risque fuite: eleve si les evenements du match servent a predire ce meme match.
- Priorite: moyenne.
- Verdict: utile pour apprendre et prototyper, pas base principale.

## 4. soccerdata Python

- Couverture: depend des backends disponibles: FBref, Understat, ClubElo, Football-Data selon disponibilite.
- Colonnes utiles: xG, stats equipe/joueur, Elo, fixtures, resultats.
- Avantages: peut accelerer des essais locaux si deja installe et conforme aux conditions des sources.
- Limites: risque de casse, dependances externes, scraping possible selon backend.
- Complexite integration: moyenne a elevee.
- Risque fuite: variable; souvent eleve pour stats post-match.
- Priorite: basse tant que le lab doit rester sans scraping.
- Verdict: outil experimental seulement.

## 5. Understat / FBref

- Couverture: xG et stats avancees selon ligues/saisons.
- Colonnes utiles: xG, xGA, tirs, joueurs, lineups, resultats.
- Avantages: tres interessant pour enrichissement xG.
- Limites: blocage possible, conditions d'utilisation, scraping a eviter sans autorisation.
- Complexite integration: elevee si automatisation; moyenne si CSV local fourni.
- Risque fuite: eleve si xG final/tirs finaux sont utilises avant match.
- Priorite: haute seulement sous forme de fichier local fourni.
- Verdict: profiler un export local, ne pas scraper automatiquement.

## 6. Datasets Hugging Face/Kaggle recents

- Couverture: variable selon auteur, competition et saison.
- Colonnes utiles: depend du dataset; rechercher date, equipes, resultats, cotes, xG, lineups, stats joueurs/equipes.
- Avantages: peut contenir des colonnes riches deja nettoyees.
- Limites: schema inconnu, qualite variable, licences a verifier, risque de doublons et fuite.
- Complexite integration: variable.
- Risque fuite: moyen a eleve selon colonnes.
- Priorite: moyenne a haute si coverage 2024+ et schema riche.
- Verdict: profiler avant toute integration.

## Regles de prudence

- Un dataset sans cotes mais avec xG/stats avancees ne remplace pas xgabora.
- Les colonnes post-match doivent rester exclues du modele predictif live.
- Toute jointure doit etre mesuree par date + equipe domicile + equipe exterieure, avec exemples non matches.
- Le test 2024+ reste la verite finale.
- Aucune source externe ne doit influencer les picks sans backtest train/validation/test.
