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
- Schéma versionné : v1 tables initiales ; v2 index FTS5 des messages existants et triggers
  insert/update/delete. La migration garde les profils, messages, notes et mesures.
- SQLAlchemy comme couche d’accès. Le SQL initial reste spécifique SQLite ; migration PostgreSQL prévue.
- Historique et notes conservés en texte. FTS5 indexe les messages avec contrôle propriétaire.
  Les embeddings seront un index dérivé reconstruisible.
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

## Mémoire personnelle

L’état durable utilise les records SQLite existants, kind `memory`, clés `state` et `job`.
Il contient les faits confirmés/proposés/archivés/refusés, dates, citations et sources, un
résumé dérivé, une révision et le checkpoint du dernier message traité. Les corrections
incrémentent la révision : une réponse IA commencée avant une correction ne peut pas l’écraser.
Un seul worker de résumé par process, en arrière-plan ; échec sans perte, statut interrompu
après restart, reprise manuelle ou lors d’un prochain échange éligible. Une seule réplique.
L’extraction exige des citations exactes d’un message utilisateur du lot ; aucune proposition
n’est automatiquement confirmée. Le résumé demeure une synthèse historique non vérifiée.
Le chat demande une enveloppe JSON contenant la réponse et au plus trois propositions ancrées
dans le dernier message utilisateur, dans le même appel Responses. La réponse et les suggestions
sont séparées avant stockage ; les propositions invalides sont ignorées sans perdre une réponse
valide. Une sortie JSON mal formée n’est pas enregistrée comme conseil. Les modèles ignorant
l’enveloppe peuvent toujours fournir une réponse texte, sans suggestion. Les cartes possèdent
l’ID du message assistant correspondant et leurs états sont conservés dans la mémoire durable.

Les propositions portent une action add/replace/archive. Un remplacement ou une clôture
référence l’ID et l’empreinte de la version du souvenir d’origine. Ces références sont vérifiées
à la création puis à la confirmation. La confirmation archive l’ancien état et enregistre les
liens et dates dans une seule écriture d’état ; le remplacement devient actif, la clôture prend
le statut applied (événement historique). Une version périmée renvoie 409 sans modification.
Les candidats appartiennent au propriétaire courant et restent bornés à 80, par pertinence
lexicale puis récence. Les changements confirmés sont fournis comme contexte daté ; les
anciens souvenirs archivés ne sont plus des faits actuels. Les propositions restent soumises
à confirmation explicite, y compris celles produites par le résumé périodique.

Le contexte assemble mémoire structurée, résumé, recherche FTS5 sur la question, échanges
récents, profil/notes et Garmin. Les plafonds figurent dans README. Les outils sémantiques,
l’import d’exports et la navigation complète de l’historique restent des évolutions distinctes.
Le modèle choisi pour le chat assure aussi les résumés automatiques ; la mise à jour manuelle
peut utiliser un autre modèle disponible. Le renouvellement OAuth est sérialisé entre threads.

## Suite

PostgreSQL + pgvector, recherche hybride, contexte des extraits, reranking, mémoire datée et
provenance. Évaluer sur des conversations validées avant d’ajouter GraphRAG ou du fine-tuning.
L’IA locale et les paiements sont hors du premier MVP.

## Activités et planification Garmin

Le scheduler démarre et s’arrête avec le lifespan FastAPI. Un tick toutes les 15 secondes
vérifie l’échéance UTC persistée dans records/settings/garmin_schedule. L’import partage les
verrous thread/fichier existants ; un job manuel non terminé n’est jamais remplacé par le
scheduler. Les jobs portent une origine manual/automatic. Une erreur automatique désactive
le planning et conserve le message assaini ; réactiver acquitte ce job et programme une
nouvelle tentative. L’import actif récupère ses checkpoints après restart.
Les fiches utilisent records/activity et un cache séparé records/activity_detail pour les
mesures autorisées du summaryDTO et des lapDTOs. Les tours sont plafonnés ; aucune récupération
massive de détails pendant le backfill. La recherche et les totaux s’effectuent en SQL avec
paramètres et ownership. Les valeurs manquantes restent null. Aucun nouveau schéma ni appel IA.
