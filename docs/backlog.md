# Backlog Coach AI

Ce fichier est la base de reprise par AI Dev Factory. Aucun ticket GitHub créé automatiquement.
Chaque ticket doit produire un comportement utilisable et ses validations. Personnel d’abord,
commercialisable à terme ; conserver les interfaces remplaçables et la propriété des données.

## Livré dans le bootstrap

| ID | Résultat | État |
|---|---|---|
| INIT-01 | Structure Python/React, conventions agents | Implémenté |
| INIT-02 | Environnement reproductible, configuration et secrets locaux | Implémenté |
| INIT-03 | Stockage local, schéma v1, profil, ownership et dates UTC | Implémenté, PostgreSQL différé |
| INIT-04 | Lint, tests et build dans CI | Implémenté |
| INIT-05 | UI responsive, accès privé, API réelle | Local et configuration Railway livrés ; utilisateur signale déploiement réussi |
| GARMIN-01 | Auth/MFA, session et lectures | Utilisateur confirme connexion locale et sync 100 activités/7 jours ; login Railway refusé 403. Transfert privé de session implémenté, test Railway requis |
| AI-01 | Connexion officielle ChatGPT locale et première inférence | Code et mocks livrés ; validation réelle requise |

## Prochain lot : valider et accéder depuis l’iPhone

### VALID-01 — Tests réels Garmin et ChatGPT (P0)
Dépendances : GARMIN-01, AI-01. Faire les tests décrits dans integrations.md avec le compte
propriétaire. Critères : session persistante après redémarrage, données comparées à Garmin,
réponse ChatGPT terminée et consommation forfait vérifiée ; erreurs/quota/refus visibles.
Le code ne doit pas être marqué « connecté » sur la seule présence d’un fichier de jetons.

### LOCAL-02 — Accès iPhone sécurisé (P0)
Dépendances : VALID-01. Choisir tunnel privé ou hébergement avec HTTPS, sessions Secure,
authentification adaptée et configuration Origin/Host stricte. Conserver les secrets côté serveur.
Le callback ChatGPT local reste sur l’ordinateur hôte : ne pas ouvrir l’autorisation sur l’iPhone
comme si son 127.0.0.1 pointait vers le serveur. Critères : accès mobile autorisé, refus sans
session, déconnexion, démarrage documenté, aucune fuite de jeton. Pas de déploiement public implicite.

### GARMIN-02 — Synchronisation planifiée et backfill (P1)
Livré : périodes et historique d’activités paginé, dix sources santé, progression persistante,
reprise/arrêt, verrou CLI/API, backoff borné, provenance et pagination UI. Import complet réel
à valider sur Railway. Restent : planification récurrente et détails/FIT d’activités.
Dépendances : VALID-01. Import historique paginé et reprise incrémentale, planning configurable,
backoff sur limite, verrou partagé CLI/API. Critères : pas de doublon après reprise ; source
manquante signalée, dernier succès/échec, déconnexion propre, tests de panne.

### HEALTH-02 — Provenance et récupération (P1)
Partiellement livré : état et date de lecture par source pour les nouveaux imports ; le contexte
coach exclut les anciennes valeurs dont une nouvelle lecture a échoué. Normalisation/tendances
approfondies et conversion des anciens enregistrements restent à faire.
Dépendances : GARMIN-02. Enregistrer la date de lecture et validité par source ; normaliser FC,
sommeil, VFC, readiness selon la montre. Éviter qu’une ancienne source conservée paraisse fraîche.
Critères : unités explicites, null distingué de zéro, tendances vérifiables, dates/fuseaux testés.

## Coach et mémoire

### MEM-01 — Import sélectif des conversations (P1)
Dépendances : INIT-03. Import export ChatGPT ou texte, sélection des discussions sportives,
prévisualisation avant validation ; conserver originaux, dates, roles, provenance. Critères :
déduplication, correction, suppression/export ; aucun fichier personnel dans le dépôt.

### MEM-02 — Profil et mémoire temporelle (P1)
Dépendances : MEM-01. Extraire objectifs, contraintes et décisions proposés au propriétaire ;
statuts actif/remplacé/terminé et dates de validité. Critères : ancienne course terminée ne reste
pas objectif actif, contradiction visible, mémoire corrigeable et chaque fait sourcé.

### RAG-01 — PostgreSQL et recherche hybride (P1)
Dépendances : MEM-01. Migration préservant les données ; pgvector + recherche lexicale,
filtrage utilisateur/sport/date et extraits avec contexte de conversation. Critères : résultats
corrects sur un jeu d’évaluation, aucune fuite inter-utilisateurs, index reconstruisible.

### RAG-02 — Reranking et outils du coach (P1)
Dépendances : RAG-01, HEALTH-02. Reranker interchangeable, choix des outils de recherche/SQL,
budget de contexte, références vers mesures et messages. Calculs réalisés en code. Critères :
répondre à une question datée, signaler données absentes, aucune mesure inventée, coût/latence mesurés.

### COACH-02 — Évaluation multisport (P0 avant diffusion)
Dépendances : MEM-02, RAG-02. Scénarios validés : déplacer un footing après un match, prendre
la muscu en compte, conserver les priorités, gérer les sensations et douleurs sans diagnostic.
Critères : réponses évaluées par le propriétaire, références correctes, questions utiles,
aucune affirmation de causalité tirée d’une simple corrélation Garmin.

## Musculation et planning

### GYM-01 — Import Excel du vrai programme (P1)
Dépendances : fichier utilisateur. Mapping feuilles/exercices/séries/réps/charges/repos,
prévisualisation et corrections. Critères : conservation de la structure du programme,
unités et consignes ; gérer cellules vides/fusionnées sans inventer de prescription.

### GYM-02 — Saisie pendant la séance (P1)
Dépendances : GYM-01. Poids/réps par série, précédente performance, minuteur, difficulté et
notes. Autosave et reprise après fermeture ; mode hors ligne avec synchronisation. Critères :
pas de perte/duplication, saisie mobile rapide et distinction prévu/réalisé.

### GYM-03 — Progression et contexte coach (P1)
Dépendances : GYM-02, COACH-02. Progression par exercice, proposition prochaine séance sans
écraser programme source ; associer Garmin et saisie si même séance. Critères : gestion charges,
réps, RPE et déduplication de la charge multisport.

### PLAN-01 — Semaine multisport (P1)
Dépendances : COACH-02. Agenda des séances/matchs, priorités, disponibilités et adaptations
expliquées ; suggestions soumises à validation. Critères : déplacement cohérent, historique des
changements, contraintes respectées et distinction séance planifiée/réalisée.

### OPS-01 — Export, sauvegarde, budgets et suppression (P1)
Export/restauration des données sans credentials, sauvegarde chiffrée, suivi requêtes/tokens,
plafonds applicatifs, effacement. Aucun fallback payant automatique. Critères : restauration
vérifiée, quotas affichés sans les inventer, arrêt propre et contrôle du propriétaire.

## Commercialisation : après MVP personnel

BIZ-01 : vérifier accès/licences Garmin et voie ChatGPT pour service commercial ; prévoir API
classique configurable. BIZ-02 : identité multi-utilisateur, isolation systématique et migrations.
BIZ-03 : consentements, politique de conservation, hébergement adapté aux données et revue juridique.
Paiement, abonnement, modèle local, fine-tuning et GraphRAG : seulement après besoin mesuré.
