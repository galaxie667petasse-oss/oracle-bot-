# Configuration privée et préparation des API

## État constaté

Les clés `API_FOOTBALL_KEY` et `THE_ODDS_API_KEY` sont absentes des environnements Process/User/Machine contrôlés. Aucun `.env` n'est présent dans les deux checkouts inspectés. Aucun secret n'a été affiché. Le contenu éventuel des secrets GitHub n'est pas lisible par cette inspection : ne pas en déduire qu'ils existent ou sont absents.

Aucune requête fournisseur réelle n'a été exécutée pendant ces deux missions. Budget engagé pour les données : **0 €**. Plafond demandé : **15 € TTC/mois**, sans souscription payante autorisée.

## Saisie sécurisée dans un processus PowerShell autorisé

Ouvrir un terminal privé dans le checkout, puis définir les secrets sans les écrire dans la commande, dans Git ou dans le chat :

```powershell
function Set-OracleProcessSecret([string]$Name) {
    $oracleSecret = Read-Host $Name -AsSecureString
    $oracleSecretPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($oracleSecret)
    try {
        [Environment]::SetEnvironmentVariable($Name, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($oracleSecretPointer), 'Process')
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($oracleSecretPointer)
    }
}
Set-OracleProcessSecret 'API_FOOTBALL_KEY'
Set-OracleProcessSecret 'THE_ODDS_API_KEY'
```

Les commandes enfants héritent de ces variables ; aucun stockage User/Machine n'est créé. Fermer ce terminal après usage. Pour `INTERNAL_API_TOKEN`, employer le même mécanisme et un jeton aléatoire d'au moins 32 octets, conservé dans un gestionnaire de secrets.

## Secrets GitHub

Dans le dépôt : **Settings → Environments → New environment**, créer un environnement dédié, par exemple `oracle-v11-live`, avec un approbateur requis et la seule branche de développement autorisée. Ajouter **Environment secrets** nommés exactement `API_FOOTBALL_KEY` et `THE_ODDS_API_KEY`. Ne pas les mettre dans des variables publiques.

La CI publiée reste **hors réseau fournisseur** et ne référence aucun de ces secrets. Leur configuration ne déclenche donc pas un test réel. Un futur job protégé devra déclarer l'environnement et injecter explicitement `secrets.API_FOOTBALL_KEY` / `secrets.THE_ODDS_API_KEY`, sur déclenchement contrôlé. Aucun job sur push/PR ne doit consommer ces clés. La présence d'un nouveau workflow `workflow_dispatch` sur une branche ne suffit pas à rendre son lancement manuel disponible : GitHub exige sa présence sur la branche par défaut. Ne pas fusionner dans main pour contourner ce prérequis dans cette mission.

Sources : [secrets GitHub](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [environnements protégés](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow), [lancement manuel](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Premier échantillon réel, lorsque les clés sont disponibles

Après vérification de l'offre gratuite et des crédits disponibles, limiter la session initiale à **une requête fixtures API-Football** et **une requête 1N2 The Odds API**, chacune en commande séparée :

```powershell
python -m v11 collect --provider api_football --day DATE_UTC --allow-network --output variable/probe-fixtures-neuf.json
python -m v11 collect --provider the_odds_api --sport SPORT_SOCCER_VERIFIE --allow-network --output variable/probe-odds-neuf.json
```

Remplacer les paramètres par une date et une compétition vérifiées ; aucun scan automatique de tous les sports. Une commande est bornée à une requête réseau, sans retry. Le cache peut réduire ce nombre à zéro. Les fichiers doivent être neufs et restent hors Git.

La requête odds cible exactement `betclic_fr`, `winamax_fr`, `unibet_fr`, `pmu_fr`, `netbet_fr` et `h2h`. Coût documentaire attendu : un crédit odds, pas une garantie de couverture. Vérifier le coût déclaré `x-requests-last`, le restant et les erreurs avant toute autre requête. Si le quota est absent ou incohérent, suspendre la session et demander une vérification du compte ; ne pas lancer de boucle.

Le rapport de couverture contient les clés effectivement observées. Relever les timestamps fournisseur et de réception, l'âge par rapport à la décision, les marchés réellement présents et les bookmakers manquants. Ne pas confondre clé documentée et présence dans la réponse. Ne pas publier le payload brut, les headers d'authentification ou les URLs contenant une clé.

Les autres marchés restent **BLOCKED pour la collecte live** tant que leur présence et leur coût ne sont pas constatés sur le fournisseur et les bookmakers concernés. Les moteurs de règlement et les imports existants restent utilisables hors réseau. Ne pas acheter une offre historique ou supplémentaire pour rendre un test vert.

Sources : [coûts et paramètres The Odds API](https://the-odds-api.com/liveapi/guides/v4/), [bookmakers documentés](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html).

## Architecture d'hébergement retenue pour préparation

Choix technique : **un petit hôte Linux privé, Docker Compose, volume persistant et accès HTTPS sur réseau privé**. Réutiliser de préférence un hôte déjà autorisé et suffisamment dimensionné. La V10 garde son application et sa base existantes ; aucun port V10 ni bot Telegram n'est démarré par le service V11.

Un service à disque éphémère exigerait de déplacer le ledger, ce que cette mission n'entreprend pas. Une VM avec volume persistant correspond directement à l'architecture actuelle. Dimensionnement exact, fournisseur et tarif restent à approuver après mesure sur la charge réelle ; le site tarifaire consulté n'a pas fourni de devis exploitable, donc aucun montant d'hébergement n'est annoncé comme vérifié.

`compose.v11.yml` prépare un port publié uniquement sur `127.0.0.1`, un utilisateur non root, un volume nommé, un système de fichiers racine en lecture seule, aucune capability Linux et `no-new-privileges`. Pour un futur hôte autorisé :

L'image de base V11 est fixée au digest observé dans le build CI réussi, en complément du lock Python. Une mise à jour de ce digest ou des dépendances demande une nouvelle CI ; cela ne constitue pas une validation de toute architecture matérielle ou de tout hébergeur.

```sh
docker compose -f compose.v11.yml up -d --build
```

Cette commande est fournie comme procédure ; aucun hôte n'a été créé et aucun déploiement distant n'a été exécuté. Ne pas lancer `docker compose config` dans un journal public : la substitution peut afficher le jeton.

Un proxy **Tailscale Serve** peut ensuite donner un accès HTTPS aux seuls appareils du réseau privé, selon ses ACL ; conserver également l'authentification applicative. HTTPS, l'enrôlement des appareils et les ACL nécessitent encore une configuration réelle autorisée. Aucun Funnel public, ouverture Internet, compte, domaine ou abonnement n'a été créé.

Sources : [Tailscale Serve privé et ACL](https://tailscale.com/docs/features/tailscale-serve), [volumes Docker persistants](https://docs.docker.com/engine/storage/volumes/).

## Sauvegarde et restauration

1. Dans le conteneur, `python -m v11 backup variable/NOUVELLE_COPIE.sqlite3` crée une copie cohérente et la rouvre pour contrôler intégrité, références et hashes.
2. Copier ce nouveau fichier vers un stockage privé chiffré hors machine ; le dossier de sauvegarde doit rester hors dépôt. Une seconde copie dans le même volume n'est pas une sauvegarde hors machine.
3. Pour restaurer, garder la base courante et le volume d'origine. Déposer la copie sous un nouveau nom dans le volume, définir `ORACLE_V11_LEDGER` vers cette copie, puis recréer uniquement le service V11 et vérifier `status`/historique.
4. Ne pas supprimer de volume ni remplacer la base historique. Un exercice de reprise complet sur un vrai hébergeur reste **NOT TESTED**.
