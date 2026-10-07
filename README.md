# Coach AI

Un coach conversationnel qui croise tous tes sports, tes activités Garmin, tes objectifs
et les informations que tu lui racontes. Première version personnelle, utilisable localement ou déployable sur Railway.

## Premier lot

- Interface responsive : vue d’ensemble, activités, profil, notes, chat et connexions.
- Base SQLite persistante avec propriétaire utilisateur et schéma initial versionné.
- Accès par clé et cookie HttpOnly (Secure en production). Les données ne sont pas publiques.
- Connexion Garmin dans le terminal, MFA et session persistante ; synchronisation manuelle
  des 100 activités récentes et de 1 à 30 jours de santé (7 jours depuis l’interface).
- Parcours officiel Sign in with ChatGPT pour applications locales : PKCE, state, nonce,
  vérification JWT, autorisation du forfait, catalogue de modèles, renouvellement et inférence.
- Historique du chat conservé, mémoire durable éditable, résumés datés et recherche lexicale.
- Contexte : 20 activités récentes, agrégats mensuels et sélection par sport/période.
- Tests hors réseau et CI. Aucun appel payant automatique.

**À valider avec de vrais comptes** : accès Garmin et autorisation/inférence ChatGPT.
Un fichier de jetons indique une configuration enregistrée ; il ne prouve pas un accès actif.
La recherche vectorielle, l’import de conversations, l’import Excel et le suivi muscu ne sont pas encore développés.

## Railway

La configuration Docker et `railway.json` sont incluses. Connecter ce dépôt depuis Railway,
attacher un volume `/data`, définir une clé privée et générer le domaine HTTPS.
Les étapes et vérifications sont dans [docs/railway.md](docs/railway.md).
Les sessions locales Garmin et ChatGPT peuvent être importées dans Connexions.
Pour ChatGPT : autorisation locale, puis transfert privé vers le serveur personnel.

## Démarrer (Mac, Linux ou WSL)

Python 3.12+, Node 22+. Depuis la racine du dépôt :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e 'backend[dev]'
npm --prefix frontend ci
coach init
```

La commande `coach init` affiche une clé à saisir dans l’interface. Elle reste dans
`.local/app.json` et ne doit pas être publiée. Le dossier `.local` contient les données
et les jetons personnels, il est exclu de git.

Terminal 1, à la racine avec l’environnement activé :

```bash
uvicorn coach.api:app --host 127.0.0.1 --port 8000
```

Terminal 2, à la racine :

```bash
npm --prefix frontend run dev
```

Ouvrir **http://127.0.0.1:5173** et saisir la clé. Sur Windows natif, activer l’environnement
avec `.venv\Scripts\Activate.ps1` ; WSL suit les commandes Linux.

### Connecter Garmin

Dans un terminal à la racine, environnement activé :

```bash
coach garmin-login
coach garmin-sync --days 7
```

Le mot de passe et le code MFA sont saisis localement. La session reste dans `.local/garmin`.
Relancer `coach garmin-login` pour vérifier sa réutilisation. En cas de session périmée,
utiliser `coach garmin-login --reauth`. Le connecteur est non officiel et peut casser
lors d’une évolution Garmin. Les mesures accessibles dépendent de la montre et du compte.

### Connecter ChatGPT

```bash
coach chatgpt-login
```

Pour tester une vraie réponse dans le terminal : `coach chatgpt-test`.
Le test choisit le premier modèle du catalogue ; aucun profil, historique ni donnée Garmin
n’est envoyé. Il utilise uniquement l’autorisation ChatGPT déjà enregistrée.

Un navigateur s’ouvre sur OpenAI. Autoriser explicitement l’identité et l’utilisation du
forfait. Le callback doit revenir sur **le même ordinateur**, à `127.0.0.1:1455/auth/callback`.
Si le port est occupé : `coach chatgpt-login --port 1456`.

Dans l’interface, charger les modèles et envoyer une question. Les données de contexte
sont envoyées à OpenAI uniquement lors de cette action. L’API ne renvoie jamais les jetons au frontend. Lors d’un import manuel,
le navigateur lit le fichier choisi et le transmet directement à l’app privée. Une réponse n’est enregistrée qu’après `response.completed` ; un quota épuisé
ou un flux interrompu est signalé comme échec. Le flux externe est streamé, mais cette
première UI affiche la réponse complète à la fin.

Pour retirer les jetons locaux : `coach chatgpt-logout`. Révoquer également l’application
 dans les réglages ChatGPT pour retirer l’autorisation distante.

Cette intégration est en preview : ses possibilités et l’éligibilité de ce projet restent
à tester. Elle utilise les limites existantes du forfait. L’accès commercial/hébergé à
distance nécessite une démarche séparée. Elle n’importe aucune mémoire ChatGPT.

### Transférer ChatGPT vers Railway

Après `git pull`, dans l’environnement Python déjà activé : `coach chatgpt-transfer`.
Saisir le domaine HTTPS de l’app puis sa clé privée. La session est validée côté serveur
(signature et identité, autorisation du forfait, accès au catalogue) avant enregistrement.
Après succès, la copie locale est supprimée : Railway possède les prochains renouvellements.
En cas d’échec, la session locale est conservée. Aucun test d’inférence automatique au transfert.

Autre possibilité : dans **Connexions → ChatGPT → Importer la session**, choisir
`.local/chatgpt.json`. Le navigateur ne peut pas supprimer le fichier source : ne plus
utiliser cette copie sur le poste après un import réussi. Si la session est trop ancienne,
relancer `coach chatgpt-test` sur le poste puis réimporter le fichier mis à jour.
Le bouton **Tester la connexion** demande une réponse neutre sans profil ni Garmin et
consomme le forfait/crédits connectés. **Déconnecter ChatGPT** retire les jetons de l’app ;
la révocation distante reste dans les réglages ChatGPT.

Dans l’interface **locale**, **Autoriser ChatGPT sur ce poste** permet de démarrer OAuth
sans saisir la commande de login : suivre le lien OpenAI dans le navigateur de ce poste.
Sur Railway ce bouton est remplacé par l’import ; son callback loopback ne peut pas être
redirigé vers le serveur. Garmin propose l’import de `.local/garmin/garmin_tokens.json` ;
la première authentification Garmin/MFA reste locale dans ce lot.

### Mémoire durable

L’onglet **Mémoire** permet d’ajouter, confirmer, corriger, archiver et supprimer les
informations utiles au coach. Catégories : objectif, contrainte, préférence, décision et
contexte santé. Une date de fin facultative empêche un souvenir périmé d’être considéré
comme actuel. Les faits proposés automatiquement restent à confirmer ; leur citation et
l’identifiant/date du message source sont visibles.

Le résumé est généré en arrière-plan après 10 nouveaux messages (5 échanges réussis),
avec le modèle de la discussion. L’actualisation manuelle permet de traiter les échanges
existants immédiatement. Chaque appel traite au maximum 30 messages, avance un checkpoint
seulement après validation et consomme le forfait/crédits ChatGPT. L’option automatique est
activée par défaut pour ce projet personnel et désactivable dans Mémoire. Aucun fallback payant.
Un échec conserve les souvenirs et le résumé précédents ; le chat terminé reste enregistré.
Le bouton manuel sert également à reprendre une mise à jour interrompue par un redéploiement.

Le contexte comprend jusqu’à 40 souvenirs actifs (pertinence lexicale puis récence), un
résumé historique limité à 4000 caractères, jusqu’à 6 extraits d’anciens messages recherchés
avec SQLite FTS5, les 20 derniers messages non masqués, le profil/notes et Garmin. Ce premier
moteur ne comporte pas d’embeddings : recherche sémantique/reranking restent au backlog.
Un résumé peut omettre des détails ou se tromper ; les corrections du propriétaire et le
message actuel priment. Un résumé n’est pas un ensemble de faits confirmés.

Corriger/refuser/archiver/supprimer un souvenir invalide le résumé potentiellement obsolète
et masque ses messages sources dans le contexte automatique. Les discussions originales
restent conservées : retirer un souvenir n’efface pas l’historique ni toutes ses autres
mentions. Une correction pendant la génération empêche le résultat concurrent de l’écraser.

Le coach reçoit 20 activités récentes sélectionnées par leur date, jamais par leur ID Garmin.
Les questions contenant une date ISO, une année, un mois français + année, « semaine dernière »
ou un sport reconnu peuvent ajouter une sélection : totaux de toutes les activités correspondantes,
et détails des 30 plus récentes. L’interprétation est limitée à ces formats, pas un outil SQL libre.
Les détails envoyés n’incluent ni coordonnées GPS ni courbes/FIT. Le contexte de récupération
reste les 7 dernières journées synchronisées ; il ne constitue pas une analyse santé historique.

## Vérifier

```bash
ruff check backend
ruff format --check backend
pytest backend/tests
npm --prefix frontend run build
```

Les tests simulés couvrent les accès privés, CSRF, persistance, déduplication, valeurs
manquantes, validation OAuth/JWT et interruptions de réponse. Ils n’utilisent aucun compte réel.

Pour servir la version construite sans Vite : construire le frontend, puis démarrer Uvicorn
avec les mêmes paramètres ; ouvrir http://127.0.0.1:8000.

## Limites de ce lot

Le démarrage local reste sur loopback. Pour un accès iPhone par HTTPS, suivre
[le déploiement Railway](docs/railway.md). Le conteneur sert l’interface et l’API ensemble.
L’authentification est personnelle ; elle ne constitue pas un accès multi-utilisateur.

La base actuelle utilise SQLite et des migrations SQL locales ; PostgreSQL/pgvector est
une évolution prévue, pas une compatibilité déjà validée. Pas de diagnostic médical.
Les recommandations IA demandent une évaluation sur de vrais cas multisport.

Voir [le backlog](docs/backlog.md), [l’architecture](docs/architecture.md) et
[les contrats d’intégration](docs/integrations.md).
