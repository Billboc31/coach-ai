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

La navigation principale est isolée dans AppNavigation : sidebar sur ordinateur, quatre
raccourcis et menu Plus sous 900 px. Le menu est un dialog modal natif (focus, Échap,
retour au déclencheur), avec blocage temporaire du défilement de fond. Les sélecteurs
de navigation ne ciblent plus les listes d'exercices. mobile.css est chargé après les
styles de fonctionnalités ; safe-area-inset et unités dvh adaptent marges et commandes
fixes. À moins de 600 px, les formulaires passent en colonne, le calendrier garde sept
colonnes avec pastilles et agenda détaillé, et la discussion utilise le défilement de page.
La fiche de référence en séance est repliable ; données et sauvegarde restent identiques.
useCoachModels lit le catalogue au passage de la connexion ChatGPT en état configuré,
avec annulation des requêtes obsolètes et erreurs séparées de l'état d'inférence du chat.
La préférence de modèle est un identifiant non secret dans localStorage, validé contre
le catalogue courant ; Sol n'est choisi que si son nom/ID est explicitement disponible.
Le scroll dépend de l'onglet et de la signature du dernier message, jamais de l'objet
dashboard rafraîchi toutes les 30 secondes. Sur grand écran, le conteneur et l'ancre
de rédaction sont repositionnés ; sur mobile, le défilement appartient à la page.
Voir les contrôles et limites de validation dans mobile.md.

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
Le bouton de détails lit aussi get_activity_details(maxchart=4000, maxpoly=0). Le décodeur
résout metricsIndex par nom et unité, sans appliquer aveuglément le factor du descripteur.
Il ne conserve que les canaux reconnus, temps relatif et distance ; aucun timestamp absolu,
coordonnée ou champ développeur. Un maximum de 5 000 échantillons est accepté. Une erreur
sur une des lectures conserve l'ancien cache. Les fiches anciennes sans séries restent lisibles.
Le SVG interactif affiche une mesure à la fois, par temps ou distance, et coupe les données
manquantes ou longs intervalles sans mesure. Les allures dérivées d'une vitesse nulle sont null.
Les tableaux d'échantillons ne sont pas inclus dans le contexte conversationnel du coach.

## Planning multisport

Records/planned_session conserve chaque séance avec UUID, dates locales, état, révision,
source et historique borné. Les mutations sont sérialisées ; elles exigent la révision actuelle.
Le lien Garmin est propriétaire, existant et unique entre séances réalisées. Les mesures
Garmin restent distinctes des consignes et durées prévues. L’API de calendrier lit par période
avec paramètres SQL et ownership, plafonds signalés ; elle convertit les dates GMT sans date
locale vers le fuseau du profil. Aucun changement du schéma SQLite.
Le même appel coach propose au maximum cinq séances structurées ; le serveur valide les dates,
les sports et les champs, force le statut proposed et retire les liens Garmin. Les suggestions
sont attachées au message assistant, confirmables dans le chat et visibles dans le calendrier.
Les séances prévues/réalisées et leurs statuts intègrent le contexte coach. Aucun outil de mutation
libre pour le modèle ni rapprochement implicite Garmin : confirmation/liaison restent explicites.

## Musculation

Records séparés : gym_import (aperçu, mapping, déduplication par empreinte), gym_source (fichier
original privé), gym_program (séances et sources), gym_exercise (nom normalisé, vidéo),
gym_excel_history (performances d’origine), gym_workout (séries saisies, révision, dates).
DELETE /api/gym/workouts/{id} exige session, origine autorisée et révision courante. Le verrou
des écritures de séance sérialise lecture et suppression : les séances terminées sont refusées,
une modification concurrente retourne 409 et un propriétaire différent voit 404. Seul le
record gym_workout est supprimé ; l'update refuse un ID absent et ne ressuscite pas le brouillon.
La confirmation UI avertit que les séries saisies seront effacées ; le cache d'onglet correspondant
est retiré uniquement après succès. Les programmes et performances Excel ne sont pas modifiés.
GymSession est une présentation du même état WorkoutScreen : toutes les séries, validation, champs
et actions partagent autosave, génération de brouillon et révisions. La vue détaillée reste
accessible et les composants gardent le même état. Le mode dédié masque navigation/header/footer
avec une classe de body retirée au changement de vue ou démontage. Sortir attend la sauvegarde
des modifications ; une erreur de réseau ou de révision conserve le brouillon et l'écran.
Les nouvelles séances reçoivent des suggestions non validées : reps numériques simples ou
liste explicite sur plusieurs lignes, poids connus de l'historique compatible ou de l'Excel
confirmé en kg. Les historiques retournent series_index pour ne pas décaler une montée en
charge dont certaines séries n'ont pas été validées. Les fiches documentaires restent vierges.
Les lectures des anciennes séances ouvertes exposent suggested_sets sans écrire en base.
WorkoutScreen fusionne uniquement les champs vides non validés et ajoute les lignes manquantes,
en gardant saisies, séries supplémentaires et brouillons. Le PUT révisionné marque
suggestions_applied afin de respecter ensuite les valeurs volontairement effacées. Les séances
terminées ne reçoivent aucune suggestion. Les charges restent vides si la variante/convention
a changé. Les repos explicites sur plusieurs lignes se répartissent par index lorsque leur
nombre correspond aux séries ; les autres consignes restent affichées sans durée inventée. Le minuteur appartient à WorkoutScreen et utilise une
échéance Date.now() ; un intervalle rafraîchit l'affichage, sans accumulation des retards.
Seule une validation explicite démarre le repos, dont les durées ambiguës restent manuelles.
Pause/reprise et changement de vue gardent l'état ; démontage/recharge le remet à zéro.
Aucune nouvelle table ; le volume SQLite existant garde l’ensemble. Les identifiants d’exercice
privés restent dérivés du nom normalisé. Un catalogue public JSON embarqué fournit des
identités RepDB stables ; les aliases précis et signatures lexicales équivalentes sont reconnus, les ambiguïtés
restent à choisir. La signature garde les détails de variante (angle, prise, matériel,
unilatéral), ignore seulement les prépositions et normalise des formes explicites. Elle
exige une identité unique ; aucune similarité approximative n’est auto-appliquée. Les
vues d’imports existants et nouveaux sont décorées automatiquement sans mutation des
programmes ni des séries. Une décision manuelle, même sans correspondance, reste prioritaire.
Records/gym_binding stocke les décisions privées, révisions, convention de poids et repère
matériel. Le rapprochement entre IDs privés exige une identité canonique et des conventions
confirmées compatibles ; une machine exige un repère non vide. Les séries portent un instantané
de variante/unités, sans conversion ni réécriture lors du changement de correspondance.
Le catalogue public est en cache ; les décisions et historiques restent propriétaire-scopés.
Les requêtes sont propriétaire-scopées. Les écritures de séance sont sérialisées, exigent la
révision actuelle et refusent les séances terminées. Les séries réalisées ne sont pas
préremplies ni marquées faites à partir d’un import. Requêtes SQL par exercice pour les
références, quel que soit l’âge de sa dernière occurrence ; affichage borné.
L’upload est borné, ZIP contrôlé avant lecture, aucun fetch de liens ni exécution de formules.
La prévisualisation associe explicitement les colonnes et signale les ambiguïtés ; le fichier
original est conservé sans changement. Les URLs de médias sont limitées aux fournisseurs
supportés ; les vidéos YouTube sont rendues depuis un identifiant validé, après clic.
Un brouillon de séries reste dans sessionStorage pendant l’autosave et n’est pas assimilé
à une écriture réussie en base. La comparaison de versions précède une reprise après conflit.

Les noms de cycles sont des valeurs explicites de sélecteur, espaces conservés. Le format
Excel jour/mois restaure les consignes textuelles ; aucune répétition réalisée n’en est déduite.
La réparation versionnée des anciens programmes relit leur source privée, sans changer
les IDs ni les logs/révisions de séances. Le décodage des performances porte la dernière
charge numérique uniquement sur les X de la même ligne ; succès et reps restent distincts.

Les mutations de programme exigent une révision et sont sérialisées. Les suppressions sont
réversibles (archived, hidden_sheets, hidden sur séance/exercice) ; start refuse les éléments
retirés et les séances vides. Les noms de feuilles source restent des identités stables ;
sheet_titles et display_name portent les noms personnalisés. Les edits d’exercice ne
contiennent que les champs modifiés, réappliqués après réanalyse. Le fichier original reste
privé et inchangé ; selection conserve le mapping confirmé. Le refresh du parser réutilise
les IDs par feuille/ligne et séance source, et les IDs d’historique existants (y compris
anciens formats). Une séance nouvelle porte display_version=2 et garde sa prescription
figée lors d’éditions ultérieures du programme. Le parser ne touche jamais les logs réels.
Les illustrations SVG sont locales ; les tutoriels publics sélectionnables sont définis
dans gym-visuals avec liens de provenance et règles de variantes. Pas de clé YouTube, pas
d’envoi de programme privé à un service de recherche, lecteur chargé après clic.

Les groupes muscles/muscles_secondary proviennent du snapshot, sans inférence depuis le
nom. La silhouette SVG est un dessin original schématique local ; couleur et légende
textuelle distinguent les groupes principaux/secondaires, sans score d’activation.

## Conversation et données de référence

`chatgpt.respond` conserve les consignes générales et le contrat JSON dans `instructions`.
Le dossier applicatif JSON est placé dans un message user documentaire distinct, puis les
vrais échanges sont ajoutés dans leur ordre, avec la question actuelle en dernier. Le dossier
n’est pas enregistré comme message de discussion, ni traité comme demande de souvenirs ;
les règles d’extraction restent ancrées au vrai dernier message utilisateur. Les 20 messages
récents, la mémoire et les plafonds de données restent disponibles. Aucun appel IA de style
supplémentaire, aucune suppression d’historique, aucun stockage distant de réponse activé.
Le coach privilégie la conversation et les informations pertinentes ; un bilan complet
n’est pas déclenché par la seule présence des données. Les tests vérifient la séparation
des consignes/données, l’ordre des rôles et la conservation des nulls/zéros et des cartes.
La qualité linguistique doit être évaluée avec le vrai modèle et les scénarios documentés.

Le parseur de réponse sépare également une réponse en prose suivie d’un suffixe JSON
réservé memory_proposals/planning_proposals valide. Les cartes passent toujours par la
validation des citations et restent proposées ; une métadonnée mal formée échoue avant
stockage. `visible_messages` est une projection de lecture des messages assistant pour
le dashboard et le contexte récent/retrouvé. Elle conserve IDs, dates et messages user,
sans réécriture des originaux ni recréation de cartes historiques. Le frontend ne rend
que paragraphes et gras simple avec React ; aucun HTML brut, média ou script interprété.

## Bibliothèque RepDB et fiches Excel

Le module coach.repdb télécharge un snapshot public épinglé au build Docker, le convertit
pour utilisation dans l'application et écrit repdb-generated.json, exclu du dépôt.
Le catalogue ne contient que ces 609 identités RepDB. Les anciens fichiers wger sont retirés.
exercise_aliases et le vocabulaire de coaching contiennent des labels et synonymes français,
sans modifier les consignes anglaises du fournisseur. La migration owner-scoped des
associations conserve leur version précédente, incrémente leur révision et ne touche pas
les programmes, logs ou noms sources. Une équivalence précise reprend le choix ; sinon
le mouvement redevient libre et les poids ne sont pas regroupés. Les anciens IDs canoniques
des séries restent stockés : seules les équivalences précises sont acceptées pour lire une
référence de charge. La migration est idempotente et respecte les refus explicites.

La projection de lecture sépare movement_name/training_instruction du nom source intact.
Les blocs fiche récupèrent les liens HTTPS autorisés sur leur ligne dans source_sheets ;
aucun téléchargement des documents privés ni extraction supposée de leurs exercices.
Ces liens sont conservés au démarrage d'une séance. Les logs, IDs et révisions ne changent
pas lors de l'affichage ; aucun poids n'est calculé à partir de « gamme montante ».

Les miniatures et photos de position utilisent uniquement le style RepDB. Une liste
de correspondances média vérifiées complète les noms anglais équivalents (squat poids
du corps, tractions pronation/supination, etc.) sans modifier les identités. Si la variante
n'a pas de visuel compatible, une icône sur le même fond bleu remplace les anciens dessins.
Les anciennes références wger restent uniquement dans les instantanés historiques et
les versions archivées des associations, sans figurer dans le catalogue actif.
