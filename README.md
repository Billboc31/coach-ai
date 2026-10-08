# Coach AI

Un coach conversationnel qui croise tous tes sports, tes activités Garmin, tes objectifs
et les informations que tu lui racontes. Première version personnelle, utilisable localement ou déployable sur Railway.

## Premier lot

- Interface responsive : vue d’ensemble, tableau d’activités par sport, fiches, profil, notes, chat et connexions.
- Mobile : quatre raccourcis et menu « Plus », zones tactiles agrandies, marges pour les
  zones de sécurité de l’iPhone, champs de saisie à 16 px, calendrier compact et formulaires
  en colonne. En séance de musculation, la fiche muscles/technique se déplie à la demande.
- Base SQLite persistante avec propriétaire utilisateur et schéma initial versionné.
- Accès par clé et cookie HttpOnly (Secure en production). Les données ne sont pas publiques.
- Connexion Garmin dans le terminal, MFA et session persistante ; synchronisation manuelle
  par période ou historique complet, reprise et mise à jour automatique configurable.
- Parcours officiel Sign in with ChatGPT pour applications locales : PKCE, state, nonce,
  vérification JWT, autorisation du forfait, catalogue de modèles, renouvellement et inférence.
- Historique du chat conservé, mémoire durable éditable, résumés datés et recherche lexicale.
- Après connexion ChatGPT, les modèles se chargent automatiquement : Sol est préféré
  s'il figure dans le catalogue, sinon le premier modèle disponible. Un choix manuel reste
  mémorisé dans le navigateur. La discussion s'ouvre au dernier échange et rejoint la
  nouvelle réponse sans remonter automatiquement lors d'une simple actualisation des données.
- Contexte : 20 activités récentes, agrégats mensuels et sélection par sport/période.
- Tests hors réseau et CI. Aucun appel payant automatique.

**À valider avec de vrais comptes** : accès Garmin et autorisation/inférence ChatGPT.
Un fichier de jetons indique une configuration enregistrée ; il ne prouve pas un accès actif.
La recherche vectorielle et l’import de conversations ne sont pas encore développés.

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

Le coach poursuit la discussion en français avec tutoiement : réponses adaptées au dernier
message, relances courtes, analyse détaillée sur demande ou si utile. Pas de bilan Garmin,
titres, listes, salutations répétées ou question finale imposés à chaque tour. Le dossier
profil/mémoire/activités reste disponible en arrière-plan dans un message documentaire
séparé des consignes ; il ne remplace pas la demande actuelle. L’historique conserve son
ordre et le vrai message utilisateur reste le dernier. Les propositions mémoire/planning
restent séparées de la réponse et soumises aux confirmations existantes. La qualité de ton
reste à évaluer avec le modèle choisi : voir [scénarios de conversation](docs/coach-conversation.md).

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
comme actuel. Les nouveaux faits exprimés dans un message peuvent être proposés directement
sous la réponse du coach : **Confirmer**, **Corriger**, **Ignorer**. La correction s’effectue
sur place et confirme la version corrigée. Les boutons et leur état persistent après rechargement.
Ces propositions viennent du même appel IA que la réponse, sans appel d’extraction supplémentaire.
Elles sont vérifiées contre une citation exacte du dernier message utilisateur avant enregistrement.
Une sortie non sourcée est ignorée. Une proposition ne devient active qu’après confirmation.
Si le modèle ajoute des champs mémoire/planning après une réponse en prose, le serveur
sépare une fin JSON valide du texte visible et conserve les cartes sourcées. Une fin
technique invalide est signalée au lieu d’être affichée ou stockée comme conseil. Les
anciens messages sont nettoyés à l’affichage et dans le contexte sans changer les originaux
ni leurs IDs ; aucun souvenir ancien n’est confirmé ou recréé par ce nettoyage. Le gras
simple et les paragraphes sont rendus en texte sûr, sans interpréter du HTML.
L’onglet Mémoire reste disponible pour gérer l’ensemble et voir les sources. Le résumé périodique
peut également proposer des souvenirs provenant des échanges plus anciens.

Quand un message annonce qu’une situation a changé, le coach peut proposer de **remplacer**
un souvenir ou de le **marquer comme terminé**. La carte montre l’ancien souvenir et le nouvel
état. Rien n’est modifié avant confirmation : confirmer archive l’ancien état avec sa date,
et active la nouvelle version en cas de remplacement. Une fin de situation est un événement
daté, pas un nouvel état de santé permanent ni un diagnostic. Ignorer garde l’ancien souvenir.
L’historique et les liens entre versions sont conservés. Une proposition basée sur un souvenir
corrigé/supprimé entre-temps est refusée ; demander une nouvelle proposition au coach.
L’identification du changement dépend du modèle : si la situation est ambiguë, le coach doit
poser une question. Les mises à jour ne concernent que les souvenirs, pas le profil ni les notes.

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

### Activités et synchronisation automatique

Dans **Connexions → Garmin**, la mise à jour en arrière-plan est activée par défaut,
toutes les heures. Fréquences disponibles : 30 minutes, 1, 3, 6 heures ou chaque jour.
Elle fonctionne côté serveur même lorsque l’interface est fermée, tant que Railway tourne.
La montre doit d’abord transférer sa séance à Garmin Connect ; il s’agit d’une interrogation
périodique, pas d’une notification instantanée. Aucun appel IA pour synchroniser.
Les activités et la santé des trois derniers jours sont actualisées ; après une interruption
prolongée, la période repart du dernier succès avec deux jours de recouvrement.
Les paramètres et le prochain passage persistent après redéploiement.
Un import manuel actif ou interrompu garde la priorité et son checkpoint : reprendre ou
terminer cet import pour laisser fonctionner la planification. Une erreur d’import automatique
suspend la planification ; vérifier la connexion puis réactiver l’option. Les limites 429
conservent le backoff borné de l’import. Une seule réplique/un seul worker est requis.

**Mes activités** affiche des cartes par sport, recherche par nom, filtres sport/dates,
totaux de la sélection et pagination de 24 séances. Cliquer ouvre la fiche : durée,
distance, fréquence cardiaque, calories et mesures spécifiques disponibles (allure,
vitesse, puissance, dénivelé, effets d’entraînement). Une donnée absente reste « — ».
**Récupérer les détails** lit le résumé détaillé, les tours et les échantillons des courbes
Garmin et les conserve localement. **Actualiser les détails** ajoute aussi les courbes aux
anciennes fiches en cache. Selon les capteurs et le sport : fréquence cardiaque, vitesse,
allure calculée, puissance, cadence, altitude, température, contact au sol et longueur de foulée.
Les graphiques se consultent par temps ou distance, au survol ou avec le curseur tactile/clavier.
Les coupures ne sont pas interpolées ; les unités non reconnues ne sont pas devinées.
Pendant un import Garmin, la fiche déjà importée reste accessible, mais la récupération
supplémentaire attend sa fin. Un échec conserve les détails précédents. Le volume des tours
est limité à 500 par séance. La requête demande au plus 4 000 points de courbe ; la résolution
dépend de Garmin. Pas de téléchargement massif pendant l’import historique. Le tracé GPS,
FIT et séries de musculation Garmin restent à développer. Les courbes restent dans la fiche
et ne sont pas automatiquement envoyées au coach avec chaque message.
L’interface ouverte vérifie les nouvelles données toutes les 30 secondes, sans recharger la page.
Les tests de ce lot sont simulés ; vérifier mesures, tours et courbes sur les vraies séances Garmin.

### Calendrier multisport

**Mon planning** affiche un calendrier mensuel et l’agenda du jour sélectionné : propositions
du coach, séances prévues, séances déclarées réalisées et activités Garmin synchronisées.
Ajouter/modifier permet de choisir sport, date, heure facultative, durée et consignes. Les
séances peuvent être annulées, marquées faites ou reliées explicitement à une activité Garmin.
Le rapprochement reste manuel pour éviter d’associer à tort deux entraînements du même sport.
Un lien ne peut servir à deux séances. Les totaux du mois et les cases du calendrier ne comptent
pas deux fois une séance liée à une activité Garmin. Les dates Garmin sans heure locale sont
converties dans le fuseau du profil. Cliquer une activité ouvre sa fiche.

**Organiser avec mon coach** prépare une demande dans la discussion. La réponse peut proposer
jusqu’à cinq nouvelles séances datées, chacune avec **Ajouter au planning**, **Ajuster** ou
**Ignorer**. Elles restent proposées avant confirmation ; une proposition ne peut pas déclarer
une séance réalisée ni lui associer un identifiant Garmin. Le modèle reçoit les séances des
14 derniers jours et des 60 prochains jours, avec leurs statuts et le fuseau/date du profil.
Ces propositions utilisent le même appel IA que la réponse, sans appel supplémentaire pour
les créer. Si le modèle répond sans propositions structurées valides, aucun ajout n’est fait.
La pertinence des séances suggérées reste à évaluer sur de vraies discussions.

Les modifications persistent avec révision et historique limité aux 50 états précédents.
Une modification concurrente renvoie un conflit sans écraser la version récente. La vue est
limitée à 400 séances et 500 activités par période de 93 jours maximum, avec signalement de
troncature. Les propositions restent disponibles dans le calendrier après sortie de l’historique
récent du chat. Ce lot ne synchronise pas de calendrier externe, n’envoie pas de séances vers
la montre et ne déplace pas automatiquement les séances existantes : les ajuster dans le planning.

### Musculation et Excel

**Musculation → Importer mon Excel** accepte les fichiers `.xlsx` (5 Mo, 30 feuilles,
1000 lignes et 40 colonnes maximum par feuille). Les anciens `.xls` doivent être convertis
avec Excel. L’aperçu propose les colonnes détectées et permet de les ajuster avant validation.
Les layouts de coaching avec ordre, semaines et titres « Séance » sont séparés en séances.
Les fusions verticales sont appliquées aux consignes sans modifier les valeurs originales.
Les formules ne sont pas exécutées. Les consignes au format Excel jour/mois (`10/10`, `5/5`, `2/3`) retrouvent leur affichage ;
les autres dates dans les champs reps/séries sont signalées ;
les séries ambiguës ne deviennent pas des prescriptions chiffrées inventées.
La notice, toutes les cellules, les hyperliens supportés et le fichier original sont conservés
privément ; l’original reste téléchargeable sans modification. Images/objets Excel restent dans
l’original et ne sont pas tous reproduits dans la grille de l’app. L’import n’édite pas Drive.

Les anciennes performances restent des entrées Excel distinctes des séries réalisées dans
l’app. Une case d’import permet de confirmer que les performances numériques simples sont en
kg (activée par défaut). `X`/`x` signifie une série réussie avec la dernière charge explicite
sur la même ligne : `5, X, X, X` représente quatre réussites à 5 kg. Sans charge précédente,
le poids reste inconnu. Les cellules vides gardent leur position ; les valeurs complexes
restent du texte. Les anciens imports utilisent désormais cette convention. Aucun
calcul de performance réelle à partir du nombre de répétitions prévu. Les imports identiques
sont dédupliqués ; importer un programme ne remplace pas l’historique des exercices.
Les programmes déjà importés sont réparés depuis leur source privée à la lecture ; les
identifiants, séries réellement saisies et révisions de séances restent inchangés.

Les boutons **Corriger** permettent d’ajuster le nom, séries, répétitions/durée, charge,
repos, tempo, consignes et dessin d’un exercice. Programme, feuille et séance sont renommables.
**Supprimer** retire un programme, une feuille, une séance ou un exercice des prochaines
séances ; **Éléments supprimés → Restaurer** annule cette action. Les séances déjà réalisées
et l’Excel source restent conservés. Ces actions sont confirmées dans l’interface.
**Réanalyser l’Excel** relit le fichier privé déjà stocké avec le parser courant, sans nouvel
upload. Les IDs, corrections manuelles, noms personnalisés, suppressions et séries saisies
restent conservés. Les anciennes performances Excel sont mises à jour sans entrées doublonnées.
Une révision de programme protège les modifications concurrentes. Les corrections concernent
les futures séances ; la prescription des séances créées par cette version reste figée.

Choisir programme/cycle/semaine, puis **Commencer la séance**. Saisir kg et reps, ou secondes
pour un maintien, puis valider chaque série. Ajouter des séries libres si le programme ne
précise pas leur nombre. Autosave après une courte pause, statut visible, reprise des séances
en cours dans un **mode séance simplifié** : navigation générale masquée, toutes les séries
visibles ensemble, champs poids/reps et coche verte par série. À la création, les charges
compatibles connues sont proposées série par série et les reps numériques prévues sont
préremplies. Une consigne explicite sur plusieurs lignes (12, 8, 5) crée trois séries ; une
fourchette, une consigne libre ou une charge inconnue restent à saisir. Les suggestions ne
sont jamais validées automatiquement. La liste des exercices avec miniatures et progression
permet de naviguer directement. Les maintiens et la recopie de charge sont dans les options.
Le repos démarre après validation si sa durée est précise, avec durée personnalisable,
pause/reprise et passage du repos. Le minuteur suit l'horloge et continue en changeant
l'exercice ou la vue ; il ne survit pas à la fermeture/recharge de la page.
**Détails** ouvre la vue complète (technique, vidéo, historique et comparaison des conflits),
sans perdre la saisie. Les séances anciennes encore ouvertes complètent une seule fois leurs
champs vides et leurs séries manquantes à la reprise, sans modifier les saisies ni validations.
Aucun réimport requis. Le repos est indiqué sous chaque série ; une liste explicite de repos
(30 secondes, 1 minute, 1 minute) est associée aux lignes et au minuteur respectifs.
« Reprendre mes charges » complète uniquement les charges vides non validées.
**Quitter** sauvegarde les modifications avant retour aux programmes ; une erreur bloque la
sortie et garde le brouillon. Les séances terminées restent consultables dans la vue complète.
Dans **Mes séances enregistrées**, **Supprimer** est disponible pour une séance inachevée.
La confirmation efface définitivement cette séance et ses séries saisies, sans toucher aux
programmes, à l'Excel ni aux séances terminées. Une modification concurrente impose de
recharger avant suppression ; un brouillon supprimé ne peut pas être recréé par un autosave.

Le brouillon reste dans l’onglet navigateur en cas d’échec. Un conflit exige une comparaison
et une action explicite avant remplacement. Ce lot exige le réseau pour créer/terminer les
séances ; le brouillon d’onglet ne constitue pas un mode hors ligne complet ni une sauvegarde.
Terminer conserve la séance et son historique ; la correction d’une séance terminée reste
à développer. Les logs sont distincts des activités Garmin et ne sont pas fusionnés dans le calendrier.

La fiche propose les précédentes charges du même exercice, sans augmentation automatique.
Le catalogue utilise uniquement les 609 exercices RepDB, chacun avec une illustration
en couleur. Les noms français, synonymes et abréviations sont associés aux identités anglaises. **Fiche exercice / Identifier**
affiche la variante, le matériel, les consignes et la provenance. Les noms précis et synonymes
connus sont reconnus ; la reconnaissance automatique accepte aussi les mots réordonnés,
pluriels, prépositions et abréviations usuelles sans supprimer les détails de variante.
Elle s’applique à tous les exercices, y compris des imports existants, sans réimport ni
validation fiche par fiche. Le bilan **Reconnaissance automatique** compte les noms uniques
du programme actif, toutes ses feuilles/semaines visibles, et liste uniquement les noms
restant à préciser. Les noms ambigus proposent une recherche et demandent un choix.
La correspondance est mémorisée avec un nom canonique stable, en conservant le nom Excel. Un exercice inédit sans référence garde ses charges vides. Conserver la même
convention de saisie (par haltère/charge totale et même matériel). Les noms différents partagent leurs références uniquement après confirmation du même
exercice, de la même convention de poids et du même repère matériel (obligatoire pour une
machine). Aucune conversion de charge ni réécriture des séries réalisées. Une ancienne
séance conserve sa variante et ses unités déjà précisées. Un exercice libre reste utilisable. Le panneau montre jusqu’à 20 séances récentes de cet exercice et
30 entrées Excel ; toutes les séries restent en base. La liste générale montre les 50 dernières
séances et jusqu’à 30 programmes. Le coach reçoit les séries validées des cinq séances récentes,
avec unités et distinction séance en cours/terminée, au maximum 25 exercices par séance.

Chaque fiche reconnue affiche une silhouette schématique face/dos avec les groupes
musculaires principaux et secondaires documentés par RepDB, deux couleurs et une légende
en français. Les groupes absents restent non renseignés, sans intensité inventée.
Les positions de départ/fin proviennent de RepDB ; cette édition gratuite ne contient pas
d’animations. Une image indisponible garde une icône sur le même fond bleu.
Les crédits et licences de chaque texte/média sont affichés ; voir [provenance du catalogue](docs/exercise-catalogue.md).

Les miniatures des cartes et fiches utilisent le style RepDB. Les anciens dessins locaux
restent seulement disponibles dans l’éditeur de correction, avec un pictogramme pour les
mouvements inconnus ; la variante exacte reste indiquée par le nom et la vidéo.
Les liens vidéo/images OneDrive présents dans Excel restent ouvrables. Un lien YouTube importé
ou enregistré dans la fiche permet d’afficher le lecteur sur place. Sans lien YouTube, la fiche
propose une recherche modifiable reprenant le nom précis et la saisie d’une URL. Quelques
variantes courantes proposent des tutoriels publics sélectionnables (squat barre, développé
couché, rowing haltère à un bras, fentes). Les suggestions ont des règles de variantes
conservatrices ; elles demandent un choix et ne remplacent pas automatiquement une vidéo.
Les liens ont été vérifiés par recherche le 7 octobre 2026 ; lecture/embedding restent à
vérifier chez le fournisseur. Aucun appel de recherche payant ni scraping YouTube à l’exécution. La vidéo ne charge qu’après clic ; sa disponibilité dépend du fournisseur.
Le parser a été essayé localement sur le fichier fourni par l’utilisateur. Tests API simulés,
lint et build vérifiés ; interaction mobile et vidéos à vérifier dans l’app Railway.

### Bibliothèque illustrée RepDB

Exercise data by [RepDB (repdb.co)](https://repdb.co). Le build Railway installe le
snapshot gratuit de 609 exercices : illustrations IA en couleur, positions de départ/fin,
consignes anglaises et muscles documentés. Les animations payantes ne sont pas incluses.
Les données sous licence sont téléchargées pendant le build, jamais republiées dans ce dépôt.
Installation locale : `PYTHONPATH=backend python -m coach.repdb`, puis redémarrer le serveur.
Les médias restent chez le fournisseur ; aucune donnée personnelle ne lui est transmise.
Licence : [RepDB Free Tier v1.0](https://github.com/RepDB/exercise-dataset/blob/main/LICENSE-DATA.md).
Pas de redistribution en dataset/API ni de réutilisation des images dans des modèles génératifs.
Les IDs privés et historiques existants sont conservés. Les anciennes associations wger
sont migrées vers RepDB lorsqu’une équivalence précise est documentée ; sinon elles
restent libres, sans reprise de poids entre variantes incertaines. Les correspondances incertaines
restent à préciser ; les variantes sont distinctes. « Gamme montante » est affiché comme
une consigne de progression, sans charge inventée. Les blocs « fiche » ouvrent les liens
de la ligne source et ne sont plus comptés comme des exercices manquant au catalogue.
