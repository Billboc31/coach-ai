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
| GARMIN-01 | Auth/MFA, session et lectures | Utilisateur confirme connexion locale et sync 100 activités/7 jours ; login Railway refusé 403. Transfert privé confirmé par l’utilisateur sur Railway ; import de session dans l’interface livré |
| AI-01 | Connexion officielle ChatGPT locale et première inférence | Utilisateur confirme autorisation locale, 4 modèles et inférence Astra ; utilisateur confirme également transfert, test et réponse du coach sur Railway ; renouvellement à valider dans la durée |

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
reprise/arrêt, verrou CLI/API, backoff borné, provenance, planification persistante configurable,
tableau par sport filtrable et fiches avec récupération/cache de résumé détaillé et tours.
Les erreurs automatiques suspendent la planification ; les checkpoints manuels gardent la priorité.
Import complet, planification et détails réels à valider sur Railway. Restent : courbes, GPS/FIT
et séries/exercices détaillés.
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
Livré pour les conversations de l’app : souvenirs manuels et propositions sourcées, validation,
correction, suppression/archive/refus, expiration, cartes Confirmer/Corriger/Ignorer dans le chat
dès la réponse (sans appel IA supplémentaire), séparation des fins JSON dans les réponses
en prose et nettoyage des anciens affichages sans changer les originaux, résumé daté
avec checkpoint, contrôle des
révisions concurrentes, option automatique et UI. Propositions de remplacement/clôture avec
ancien/nouveau état, archive datée et liens entre versions, confirmation atomique et rejet des
propositions périmées (409) livrés. La qualité de détection reste à évaluer. Les anciens objectifs ne sont pas automatiquement
confirmés. Validation réelle et qualité des résumés à évaluer ; import ChatGPT reste MEM-01.
Dépendances : MEM-01. Extraire objectifs, contraintes et décisions proposés au propriétaire ;
statuts actif/remplacé/terminé et dates de validité. Critères : ancienne course terminée ne reste
pas objectif actif, contradiction visible, mémoire corrigeable et chaque fait sourcé.

### RAG-01 — PostgreSQL et recherche hybride (P1)
Première recherche lexicale livrée : SQLite FTS5 sur les messages avec filtrage propriétaire,
extraits pertinents et plafonds de contexte. Pas d’embeddings, de PostgreSQL ni de reranking.
Dépendances : MEM-01. Migration préservant les données ; pgvector + recherche lexicale,
filtrage utilisateur/sport/date et extraits avec contexte de conversation. Critères : résultats
corrects sur un jeu d’évaluation, aucune fuite inter-utilisateurs, index reconstruisible.

### RAG-02 — Reranking et outils du coach (P1)
Première sélection déterministe d’activités par sport/période et totaux SQL, avec 20 activités
récentes par date et 30 détails maximum pour une période. Interprétation de dates limitée ;
pas encore de boucle d’outils choisie par le modèle ni de détails FIT.
Dépendances : RAG-01, HEALTH-02. Reranker interchangeable, choix des outils de recherche/SQL,
budget de contexte, références vers mesures et messages. Calculs réalisés en code. Critères :
répondre à une question datée, signaler données absentes, aucune mesure inventée, coût/latence mesurés.

### COACH-02 — Évaluation multisport (P0 avant diffusion)
Livré : données documentaires séparées des consignes, dernier message prioritaire,
conversation naturelle par défaut, analyses proportionnées à la demande, relances courtes,
propositions mémoire/planning indépendantes du ton. Contrats d’inputs et régressions testés ;
qualité réelle à évaluer avec les scénarios dans docs/coach-conversation.md.
Dépendances : MEM-02, RAG-02. Scénarios validés : déplacer un footing après un match, prendre
la muscu en compte, conserver les priorités, gérer les sensations et douleurs sans diagnostic.
Critères : réponses évaluées par le propriétaire, références correctes, questions utiles,
aucune affirmation de causalité tirée d’une simple corrélation Garmin.

## Musculation et planning

### GYM-01 — Import Excel du vrai programme (P1)
Livré : aperçu XLSX, association de colonnes, cellules fusionnées, séparation cycles/semaines/
séances, conservation des sources et fichier original, consignes/tempos/repos/commentaires,
performances historiques séparées, X de réussite avec maintien de charge sur la ligne,
sélection des feuilles avec espaces, restauration des consignes jour/mois et multilignes,
réparation des anciens programmes sans modifier les logs, déduplication et dates ambiguës. Parser
essayé sur le fichier fourni. Gestion livrée : corrections d’exercice, renommage programme/
feuille/séance, suppression réversible à chaque niveau, réanalyse du fichier stocké avec
conservation des corrections/IDs/historique et contrôle des révisions. Restent : autres
layouts, XLS/ODS, images intégrées dans la fiche.
Dépendances : fichier utilisateur. Mapping feuilles/exercices/séries/réps/charges/repos,
prévisualisation et corrections. Critères : conservation de la structure du programme,
unités et consignes ; gérer cellules vides/fusionnées sans inventer de prescription.

### GYM-02 — Saisie pendant la séance (P1)
Livré : écran de séance, kg/reps/secondes par série, validation, ajout de séries, autosave,
brouillon d’onglet, reprise, historique en base, contrôle des révisions et fin de séance.
Restent : vrai mode hors ligne, minuteur de repos/RPE, correction des séances terminées.
Dépendances : GYM-01. Poids/réps par série, précédente performance, minuteur, difficulté et
notes. Autosave et reprise après fermeture ; mode hors ligne avec synchronisation. Critères :
pas de perte/duplication, saisie mobile rapide et distinction prévu/réalisé.

### GYM-03 — Progression et contexte coach (P1)
Livré : références de charge du même exercice entre programmes, performances Excel conservées
et unités confirmables, historique par exercice, séries validées dans le contexte coach, liens
média Excel, neuf familles de dessins locaux et lecteur YouTube configurable. Tutoriels
sélectionnables pour quelques variantes courantes et recherche précise modifiable.
Catalogue livré : 609 identités RepDB uniquement, aliases français/anglais, reconnaissance automatique des
formulations équivalentes et vocabulaire de coaching (DVP, variantes guidées, barre/corde,
Scott/EZ, machines assis/allongé) sur tous les imports, bilan des noms restant à préciser,
suggestions/confirmation de variantes,
conventions de poids et repères machines, historique compatible entre noms, crédits/licences
et illustrations départ/fin disponibles, silhouette musculaire face/dos avec
principaux/secondaires documentés et légende française. Exercices libres et anciens logs conservés.
Restent : comparaison/progression approfondie, suggestions chiffrées évaluées, extension des
aliases et animations, fusion calendrier/Garmin.
Dépendances : GYM-02, COACH-02. Progression par exercice, proposition prochaine séance sans
écraser programme source ; associer Garmin et saisie si même séance. Critères : gestion charges,
réps, RPE et déduplication de la charge multisport.

### PLAN-01 — Semaine multisport (P1)
Livré : calendrier mensuel et agenda du jour, séances manuelles, propositions du coach dans
la réponse avec confirmation/ajustement/refus, modification/annulation/réalisation, liens
Garmin explicites uniques, activités réalisées dans le calendrier, contexte du planning pour
le coach, révisions et historique borné. Tests simulés passent ; validation réelle du calendrier
et de la pertinence des propositions à effectuer. Restent : vue semaine avancée, récurrences,
propositions de déplacement/remplacement, agenda externe et envoi des entraînements vers Garmin.
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

### CONNECT-02 — Connexions depuis l’interface (P1)
Livré : import privé de sessions Garmin/ChatGPT, état/erreurs, autorisation ChatGPT depuis
l’interface locale, test d’inférence sans données santé, déconnexion ChatGPT et transfert CLI.
Restent : première authentification Garmin avec MFA depuis une interface locale, parcours
mobile sans fichier via assistant local, et voie commerciale cloud. Le callback officiel
ChatGPT reste loopback ; ne pas présenter un bouton Railway comme un OAuth cloud complet.

### GYM-04 — Bibliothèque illustrée et consignes de coaching
Livré : RepDB gratuit (609 variantes illustrées) installé au build, crédits/licence visibles,
miniatures dans programmes et recherche, départ/fin dans les fiches. Consigne gamme montante
séparée du mouvement ; presse oblique identifiable ; liens fiches abdos/mobilité utilisables
sans les assimiler à des exercices individuels manquants. Historique et source conservés.
Restent : traduction complète française, extraction consentie des fiches privées, extension
des synonymes précis et éventuelle licence d'animations après choix du propriétaire.

GYM-04 : migration RepDB uniquement, retrait du catalogue wger, associations anciennes
archivées/migrées sans effacer les séances ; noms français et variantes bilingues.
