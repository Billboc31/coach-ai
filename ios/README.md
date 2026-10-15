# Coach AI sur iPhone

Application SwiftUI pour iPhone, iOS 17 minimum. Aucun changement du stockage Railway :
les comptes, programmes, séances, Garmin et conversations utilisent le serveur existant.
Android n’est pas inclus dans ce lot.

## Installer depuis ton Mac

1. Mettre à jour le dépôt et ouvrir **ios/CoachAI.xcodeproj** dans Xcode 16 ou ultérieur.
2. Dans **Settings → Accounts**, ajouter ton compte Apple. Dans le target **CoachAI →
   Signing & Capabilities**, choisir ta Team. Si nécessaire, changer le Bundle Identifier
   `com.bpconsulting.coachai` pour un identifiant disponible pour ta Team.
3. Brancher l’iPhone au Mac, l’autoriser, activer le mode développeur si iOS le demande.
   Choisir l’iPhone comme destination et appuyer sur **Run ▶**.
4. Saisir l’URL HTTPS de ton serveur et ta clé personnelle Coach AI.

Le compte Apple gratuit permet les essais locaux avec les limites de signature Apple.
La distribution TestFlight/App Store demande une signature et une configuration de distribution
Apple adaptées. Aucun certificat ni compte Apple n’est fourni dans le dépôt.

## Disponible

- Musculation **native** : choix du programme/cycle/feuille/séance, reprise, historique récent,
  images RepDB et crédits, consignes, conventions de poids, séries préremplies par le serveur.
- Grands champs poids/répétitions/secondes, validation, ajout de série, repos sur chaque ligne,
  minuteur et notification locale à échéance si autorisée. Le minuteur utilise une date réelle,
  pas un compteur dépendant de l’exécution en arrière-plan. L’écran reste allumé pendant
  la séance au premier plan. Une nouvelle séance de minuteur remplace la précédente.
- Proposition d’augmentation de charge au passage à l’exercice suivant après validation
  complète, enregistrement de progression dans la même base que le web.
- Enregistrement au cochage d’une série, bouton manuel pour les autres modifications,
  fin et suppression confirmée des séances commencées.
- Brouillon protégé localement après chaque modification valide ; récupération au prochain
  lancement après authentification au même compte/serveur. Aucun rejeu automatique d’une
  mutation dont la réponse a été perdue. Les conflits de révision bloquent l’écrasement ;
  comparer les valeurs dans la vue web avant de choisir « Recharger la version serveur ».
  **Un brouillon actif par compte et serveur** : enregistrer avant de changer de séance.
  Les brouillons des autres comptes sont conservés séparément.
  Les séances nouvelles demandent un accès réseau. Ce n’est pas une synchronisation hors ligne
  complète ni un téléchargement de tous les programmes sur l’iPhone.
- Coach, activités, planning et paramètres via les pages existantes dans une WKWebView
  authentifiée. Ces écrans sont encore **web**, avec leurs fonctions existantes.
- Import **natif** de fichiers JSON de session Garmin/ChatGPT depuis Fichiers, limité à 64 Ko,
  confirmation du compte/serveur avant transfert et validation réelle côté serveur. Le fichier
  n’est pas copié dans le stockage de l’app. Renouvellement ChatGPT depuis les paramètres web.

## Connexions : limite à connaître

Cette version n’implémente pas une autorisation Garmin ou ChatGPT initiale entièrement locale
sur iPhone. Le formulaire Garmin web appelle toujours Railway et peut toujours recevoir un 403.
L’import d’une session déjà obtenue fonctionne via les fonctions serveur existantes, sans
promesse de contourner le refus Garmin. Le callback OAuth ChatGPT local et l’autorisation
commerciale ne deviennent pas disponibles simplement en ajoutant un conteneur iOS.
Aucun mot de passe fournisseur ni client OAuth emprunté n’est ajouté à l’app.

## Sécurité et conservation

- Clé d’accès saisie transitoirement ; seul le cookie de session (8 heures, invalidé au
  redémarrage du serveur) est conservé dans le trousseau, accessible sur cet appareil
  uniquement lorsqu’il est déverrouillé. Pas de clé dans UserDefaults.
- URL serveur HTTPS limitée à une origine, pas de paramètres ni identifiants ; Origin exact
  sur les mutations. URLSession éphémère, pas de cache, pas de redirections API autorisées.
- Cookie transféré à WKHTTPCookieStore sans JavaScript ; stockage web en mémoire recréé
  à chaque connexion/déconnexion. Liens externes explicites dans Safari, sans cookie Coach AI.
- Brouillon dans Application Support, protection complète iOS, exclu de la sauvegarde.
  Le brouillon est conservé après expiration/déconnexion pour le compte d’origine ;
  une autre identité ne peut pas le charger. Pas d’envoi en télémétrie ni de journal des données.
- Notifications locales sans information d’exercice, pas de notification push ni tâche serveur.
  Les notifications sont annulées en quittant une séance ou en se déconnectant.

## Validation

Le workflow **iPhone** construit le projet et exécute les tests unitaires dans un simulateur
Apple sur un runner macOS. Tests : origines, absence de données ≠ zéro, prescriptions de repos,
respect des séries déjà cochées, schéma de mise à jour/révision, en-têtes authentifiés,
absence de rejeu après conflit, rejet de session expirée avant envoi et isolation des brouillons
entre comptes/serveurs.

Sur Mac, équivalent (adapter la destination avec `xcodebuild -showdestinations`) :

```sh
xcodebuild test -project ios/CoachAI.xcodeproj -scheme CoachAI \
  -destination 'platform=iOS Simulator,name=iPhone 16' CODE_SIGNING_ALLOWED=NO
```

Avant distribution : installation iPhone réelle, clavier français/décimales, notification
avec écran verrouillé, révocation de session, mode avion puis retour réseau, comparaison
conflit sur deux appareils et tests des intégrations avec de vrais comptes. Aucun test
simulé ne valide une connexion réelle Garmin ou ChatGPT.
