# Déployer sur Railway

Un service Docker sert React et FastAPI sur le même domaine HTTPS. SQLite, les notes,
le profil et les jetons restent dans un volume privé. Aucun secret à ajouter au dépôt.

## Configuration

1. Dans Railway : New Project → Deploy from GitHub repo → `Billboc31/coach-ai`, branche `main`.
   Garder la racine du dépôt comme Root Directory. Le Dockerfile est détecté automatiquement.
2. Attacher un volume au service avec le chemin de montage **`/data`**.
3. Dans Variables, ajouter **`COACH_ACCESS_KEY`** : une valeur aléatoire privée de 32 caractères
   minimum, générée par un gestionnaire de mots de passe. Elle sert à ouvrir l’interface.
   Ne pas la mettre dans GitHub, les captures ou les logs.
4. Dans Settings → Networking, générer un domaine public Railway et sélectionner le port **8000**.
   Ajouter `PORT=8000` dans Variables. `RAILWAY_PUBLIC_DOMAIN` fournit automatiquement
   l’origine HTTPS autorisée. Pour un domaine personnalisé, définir `COACH_PUBLIC_URL=https://…`.
5. Déployer les modifications. Ne pas ajouter de Start Command : le Dockerfile démarre
   `python -m coach.server`. Garder **une réplique**, sans mise en veille automatique.

Le Dockerfile définit `COACH_ENV=production`, `COACH_DATA_DIR=/data` et le dossier de l’interface.
Le démarrage refuse une clé faible, une origine sans HTTPS ou un volume Railway absent/mal monté.
Le healthcheck `/api/health` accepte le Host Railway `healthcheck.railway.app`.
Le conteneur utilise l’utilisateur root pour pouvoir écrire sur le volume monté par Railway.
Les données du volume ne sont pas servies par l’API statique.

## Vérifier après le déploiement

- Le déploiement doit être Active et `/api/health` doit répondre `status: ok`.
- Ouvrir le domaine sur iPhone : saisir la clé privée, enregistrer le profil et une note.
- Sans connexion, `/api/dashboard` doit répondre 401 ; le cookie doit être Secure et HttpOnly.
- Redéployer puis se reconnecter : profil et note doivent toujours être présents.

Chaque push sur la branche reliée déclenche un nouveau déploiement si l’autodéploiement
GitHub est activé. Un redémarrage impose une nouvelle connexion. Le volume peut entraîner
une courte interruption pendant le remplacement du conteneur. Activer les sauvegardes
Railway avant d’enregistrer des données réelles ; vérifier les coûts dans le compte Railway.

## Connexions sport et IA

L’interface est utilisable dès le déploiement pour le profil et les notes. Elle ne contient
aucune mesure inventée ni réponse IA simulée.

Garmin : dans un terminal **du conteneur déployé** (Railway SSH), exécuter
`coach garmin-login`, puis `coach garmin-sync --days 7`. Le compte et le MFA restent à
valider. `railway run` exécute localement : ce n’est pas le stockage du conteneur.

### Session Garmin déjà validée sur l’ordinateur

Si la connexion directe échoue sur Railway alors qu’elle fonctionne localement, tester la
reprise de cette autorisation avec `coach garmin-transfer`, depuis la racine du dépôt sur
l’ordinateur, environnement Python activé et code à jour (`git pull`). La commande demande
le domaine HTTPS exact de l’app, puis la clé COACH_ACCESS_KEY avec saisie masquée.

Elle envoie uniquement les trois champs DI de `.local/garmin/garmin_tokens.json` directement
à l’app protégée. Aucun mot de passe Garmin n’est transmis à Railway. Ne pas envoyer ce
fichier dans une discussion ou le committer. La commande refuse HTTP et les redirections.

Le serveur contrôle l’accès, l’Origin, le format et la taille du transfert. Il teste une
lecture Garmin avec les jetons dans un dossier temporaire privé avant de remplacer sa
session enregistrée ; un échec conserve la précédente. Toute rotation pendant le test
est enregistrée. La commande lance ensuite une synchronisation depuis Railway et indique
les nombres récupérés. Le bouton Synchroniser de l’app utilisera ensuite cette session.

Ce test ne garantit pas que Garmin autorisera les lectures ou le renouvellement depuis
Railway. Un 403 sur la session réutilisée doit être traité comme un refus ; aucun contournement
de protection ou fallback de connexion automatique n’est ajouté. Après un transfert réussi,
éviter de synchroniser depuis les deux ordinateurs avec la même copie de la session :
le serveur devient responsable du renouvellement. Un redémarrage du serveur suivi d’une
synchronisation permet de vérifier la persistance ; le renouvellement reste à valider dans
la durée. La planification automatique est encore le ticket GARMIN-02.

ChatGPT : la CLI actuelle utilise un callback sur `127.0.0.1` de l’ordinateur local.
Ce parcours ne fonctionne pas directement depuis l’interface Railway. L’éligibilité et
l’authentification d’une application hébergée sont à traiter séparément avant d’activer
le coach en ligne. Aucun appel via API payante n’est activé automatiquement.

## Références

- https://docs.railway.com/services
- https://docs.railway.com/volumes
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/config-as-code/reference

Le build Docker et les vérifications sur un service Railway réel doivent être exécutés
sur l’hébergeur ; un build React et des tests Python seuls ne prouvent pas le déploiement.
