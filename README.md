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
- Historique du chat conservé ; contexte limité au profil, notes et données récentes pertinentes.
- Tests hors réseau et CI. Aucun appel payant automatique.

**À valider avec de vrais comptes** : accès Garmin et autorisation/inférence ChatGPT.
Un fichier de jetons indique une configuration enregistrée ; il ne prouve pas un accès actif.
La mémoire RAG, l’import de conversations, l’import Excel et le suivi muscu ne sont pas encore développés.

## Railway

La configuration Docker et `railway.json` sont incluses. Connecter ce dépôt depuis Railway,
attacher un volume `/data`, définir une clé privée et générer le domaine HTTPS.
Les étapes et vérifications sont dans [docs/railway.md](docs/railway.md).
Garmin nécessite encore une connexion sur le serveur ; ChatGPT local n’est pas encore adapté au cloud.

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

Un navigateur s’ouvre sur OpenAI. Autoriser explicitement l’identité et l’utilisation du
forfait. Le callback doit revenir sur **le même ordinateur**, à `127.0.0.1:1455/auth/callback`.
Si le port est occupé : `coach chatgpt-login --port 1456`.

Dans l’interface, charger les modèles et envoyer une question. Les données de contexte
sont envoyées à OpenAI uniquement lors de cette action. Les jetons ne sont jamais exposés
au frontend. Une réponse n’est enregistrée qu’après `response.completed` ; un quota épuisé
ou un flux interrompu est signalé comme échec. Le flux externe est streamé, mais cette
première UI affiche la réponse complète à la fin.

Pour retirer les jetons locaux : `coach chatgpt-logout`. Révoquer également l’application
 dans les réglages ChatGPT pour retirer l’autorisation distante.

Cette intégration est en preview : ses possibilités et l’éligibilité de ce projet restent
à tester. Elle utilise les limites existantes du forfait. L’accès commercial/hébergé à
distance nécessite une démarche séparée. Elle n’importe aucune mémoire ChatGPT.

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
