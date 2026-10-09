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

Garmin : essayer **Plus → Connexions → Garmin → Connecter Garmin ici**. Le formulaire privé
transmet e-mail/mot de passe au serveur pour une seule tentative ; saisir le code MFA si
Garmin le demande. Aucun mot de passe/code enregistré. Délai cinq minutes, annulation,
maximum trois tentatives par compte en dix minutes. La session précédente est conservée
jusqu'à validation de la nouvelle. Un 403 depuis Railway reste possible ; le formulaire ne
change pas le réseau d'origine et n'ajoute ni proxy ni contournement. Ce parcours réel doit
être testé par la personne. ChatGPT conserve son parcours local/import actuel.

Autre possibilité Garmin : dans un terminal **du conteneur déployé** (Railway SSH), exécuter
`coach garmin-login`, puis `coach garmin-sync --days 7`. Le compte et le MFA restent à
valider. `railway run` exécute localement : ce n’est pas le stockage du conteneur.

### Session Garmin déjà validée sur l’ordinateur

Si la connexion directe échoue sur Railway alors qu’elle fonctionne localement, tester la
reprise de cette autorisation avec `coach garmin-transfer`, depuis la racine du dépôt sur
l’ordinateur, environnement Python activé et code à jour (`git pull`). La commande demande
le domaine HTTPS exact de l’app, puis ta clé personnelle avec saisie masquée (COACH_ACCESS_KEY uniquement pour le propriétaire historique).

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

### Import historique depuis l’interface

Dans Connexions → Garmin, choisir 7/30/90/365 jours, une période personnalisée ou tout
l’historique accessible. Le bouton démarre un travail en arrière-plan ; les compteurs,
la date traitée, les erreurs et la fin de synchronisation sont visibles. La page peut
être fermée. Arrêter et Reprendre permettent de conserver les résultats déjà enregistrés.

Le mode complet récupère les activités par pages jusqu’à épuisement. Les données santé
commencent à la première activité trouvée ; une date explicite permet d’importer les
mesures antérieures. Il n’existe pas de date de première mesure fiable utilisée par ce
lot : pour une montre utilisée avant les premières activités, préciser cette date.

Sources santé : résumé quotidien, sommeil, FC, VFC, readiness, stress, Body Battery,
respiration, SpO2 et composition corporelle si accessibles. Chaque source garde son état
et sa date de lecture. Une absence ne devient pas zéro ; une ancienne lecture conservée
ne devient pas fraîche. L’historique visible est paginé par 50 activités. Les agrégats
mensuels par sport sont disponibles dans le contexte du coach (120 groupes maximum),
sans transmettre l’intégralité des réponses Garmin au modèle.

Les checkpoints sont enregistrés dans SQLite après chaque page et journée ; un import
en cours est repris au prochain démarrage du serveur. Une page d’activités peut être rejouée
sans doublon. En cas de 429, pauses progressives de 60/120/240 secondes puis état En pause ;
un 403 ou une erreur d’authentification arrête le travail. Un verrou de fichier sérialise
la session avec les opérations CLI. Garder une seule réplique et désactiver la mise en veille.

Le premier import peut prendre plusieurs heures selon la profondeur et les réponses Garmin.
Ce n’est pas une sauvegarde intégrale du compte Garmin : les fichiers FIT/GPX, courbes et
splits détaillés des activités, équipements, nutrition et autres domaines ne sont pas
importés par ce lot. Les limites de conservation du fournisseur restent applicables.

### Session ChatGPT autorisée sur le poste

Après mise à jour du dépôt, lancer `coach chatgpt-transfer` depuis le poste où la connexion
ChatGPT a réussi. Saisir le domaine HTTPS puis la clé d’accès de l’app. Aucun jeton ne doit
être copié dans GitHub, les variables Railway ou une discussion. Après validation du serveur,
la session locale est retirée pour laisser Railway gérer seul les rotations du refresh token.

L’interface Connexions permet aussi d’importer `.local/chatgpt.json`, de tester une vraie
réponse neutre et de déconnecter l’app. Après l’import par navigateur, ne plus utiliser la
copie source sur le poste ; le navigateur ne peut pas la supprimer. Un import périmé est
refusé : renouveler localement avant de réessayer. Aucun conseil ni donnée Garmin envoyé
lors de ce test. Le test utilise le forfait/crédits ChatGPT. Les messages du coach utilisent
ensuite le contexte santé décrit précédemment.

Le runtime crée/conserve son propre host ID sur le volume ; un ID du poste n’est jamais
importé. Vérification de la signature JWT, issuer/audience, identité liée au token d’accès,
client ID, scope du forfait et catalogue avant remplacement atomique. Un refus conserve
le compte précédent. Les renouvellements sont sérialisés entre CLI/API sur ce runtime.

Ce parcours reprend la documentation officielle pour une application open source exécutée
sur un serveur personnel. Le callback initial reste local. La commercialisation ou le
service hébergé destiné à d’autres comptes nécessite une démarche séparée. Aucun fallback
API payant. Le transfert et l’inférence réels sur Railway restent à valider par le propriétaire.

## Références

- https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
- https://docs.railway.com/services
- https://docs.railway.com/volumes
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/config-as-code/reference

Le build Docker et les vérifications sur un service Railway réel doivent être exécutés
sur l’hébergeur ; un build React et des tests Python seuls ne prouvent pas le déploiement.

## Comptes sur invitation

Aucune nouvelle variable ni service requis. Conserver COACH_ACCESS_KEY comme clé de
l'administrateur et le volume /data. Après déploiement, créer un lien dans Connexions →
Inviter une personne. Ne pas partager la clé administrateur : chaque inscrit reçoit sa propre clé.
Les bases et sessions des membres résident sous /data/users/<identité>, et accounts.json à
la racine. Sauvegarder tout le volume, pas seulement coach.db.
Chaque personne peut essayer Garmin dans le formulaire privé ; si nécessaire, elle autorise
Garmin/ChatGPT localement puis transfère ses sessions avec sa clé
personnelle vers le même domaine. Les autorisations fournisseurs restent à valider pour ce
compte ; ces invitations ne constituent pas un nouveau parcours OAuth cloud.
