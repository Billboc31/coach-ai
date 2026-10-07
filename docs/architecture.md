# Architecture initiale

## Flux

Frontend React → API FastAPI protégée → stockage SQLite.
La CLI partage le même dossier COACH_DATA_DIR que le serveur et gère les connexions externes.
Le mot de passe Garmin n’entre pas dans le navigateur de l’application. Les jetons Garmin
et ChatGPT sont des fichiers locaux distincts, jamais des champs du profil ni des données RAG.

## Décisions

- Backend Python : intégration native du connecteur Garmin, API typée et tests isolés.
- React/TypeScript : interface mobile avec actions de saisie et navigation simple.
- SQLite pour démarrer immédiatement sans infrastructure. Chaque enregistrement porte user_id.
  Le propriétaire `local` est fixe dans ce lot ; il ne constitue pas un système multi-utilisateur.
- Schéma initial versionné à 1. Les migrations suivantes doivent être explicites et préserver les données.
- SQLAlchemy comme couche d’accès. Le SQL initial reste spécifique SQLite ; migration PostgreSQL prévue.
- Historique et notes conservés en texte. Les embeddings seront un index dérivé reconstruisible.
- Le coach reçoit un contexte limité, avec dates et unités ; pas de traces GPS ou données de compte.
- Les indicateurs manquants sont null, et non zéro. Pas de calcul de charge improvisé.
- La source de vérité reste le stockage ; le modèle ne mémorise pas les mesures dans ses poids.

## Accès et confidentialité

Application locale par défaut, accès par clé aléatoire et session HttpOnly valable 8 heures.
Sessions en mémoire : redémarrer le serveur exige une nouvelle connexion. Contrôle Origin
sur les mutations, contrôle Host et limitation des tentatives de connexion. HTTP et cookie
sans Secure uniquement sur loopback. En production : origine HTTPS exacte, Host autorisé,
cookie Secure et clé COACH_ACCESS_KEY (32 caractères minimum). Railway termine TLS.
Une seule réplique/un seul worker ; les redémarrages invalident les sessions. Le stockage
SQLite et les jetons résident dans le volume /data. La clé locale s’affiche via `coach init`.

Secrets écrits atomiquement avec permissions 0600 sur Unix, dossier privé. Sur Windows,
les permissions dépendent du compte et des ACL locales. Ne pas synchroniser `.local` vers git.

## Suite

PostgreSQL + pgvector, recherche hybride, contexte des extraits, reranking, mémoire datée et
provenance. Évaluer sur des conversations validées avant d’ajouter GraphRAG ou du fine-tuning.
L’IA locale et les paiements sont hors du premier MVP.
