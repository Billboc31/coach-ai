# Installer la version native sans ton Mac

Le Mac de compilation est le runner macOS 26 GitHub avec Xcode 26.6, pour respecter
le SDK iOS 26 minimum demandé par Apple depuis avril 2026. Sur l’iPhone, l’installation
se fait avec l’application **TestFlight** d’Apple. Aucun IPA non signé ni build
simulateur ne peut remplacer cet envoi signé.

## Situation et prérequis

La chaîne de distribution est préparée dans `.github/workflows/testflight.yml`.
Elle n’est pas lancée tant que le **bon compte Apple Developer** n’est pas connecté,
la fiche de l’app créée et les accès de signature configurés. Un build simulateur
ou une archive iPhone non signée ne valide pas la distribution réelle.

Il faut un abonnement Apple Developer actif pour l’équipe choisie, ses contrats
à jour, et le droit de créer/gérer l’app et d’utiliser les certificats de distribution
gérés dans le cloud Apple. Les droits d’une autre équipe ne doivent pas être réutilisés.
Le workflow ne révoque ni ne supprime les certificats des apps existantes.

## Configuration, une seule fois depuis le navigateur

1. Dans le **bon compte Apple**, enregistrer le Bundle ID choisi et créer la fiche
   **Coach AI** dans App Store Connect, plateforme iOS. Le Bundle ID du workflow
   doit correspondre exactement à cette fiche. Choisir un SKU propre à l’app.
2. Dans **Utilisateurs et accès → Intégrations → API App Store Connect**, configurer
   une clé d’équipe ayant les droits nécessaires sur cette app et la signature cloud.
   La création d’une clé est une autorisation sensible : elle doit être validée par
   le titulaire autorisé. Ne jamais envoyer la clé privée `.p8` dans une discussion,
   un ticket, un commit ou un artefact public.
3. Dans le dépôt GitHub, **Settings → Environments → testflight**, ajouter :
   - variable `APPLE_TEAM_ID` : l’identifiant de l’équipe Apple, 10 caractères ;
   - secret `ASC_KEY_ID` : Key ID de la clé API ;
   - secret `ASC_ISSUER_ID` : Issuer ID de cette équipe ;
   - secret `ASC_PRIVATE_KEY` : contenu du fichier `.p8`, avec ses vraies lignes.
   Utiliser une protection d’environnement/reviewer si disponible. Ces valeurs ne
   sont pas des variables Railway et ne doivent pas être placées dans l’app mobile.
4. Ouvrir **Actions → TestFlight → Run workflow**, branche `main`, renseigner le Bundle ID.
   Le workflow est uniquement manuel : aucun push ni pull request ne déclenche d’envoi.

La compilation génère une archive destinée à **iPhone réel**. L’export utilise
`xcodebuild -exportArchive`, la clé App Store Connect, la signature automatique
et les certificats gérés par Apple. La clé est écrite dans un dossier privé du runner
puis supprimée à la fin ; aucun secret n’est publié en artefact. Les droits/certificats
cloud de l’équipe doivent être vérifiés lors du premier envoi réel. Si Apple refuse
la signature ou impose une configuration supplémentaire, le workflow échoue et
l’app n’est pas annoncée installable.

## Installation sur ton téléphone

Après un envoi réussi, attendre que le build soit traité dans **App Store Connect →
Coach AI → TestFlight**. Renseigner les informations de test/export si Apple les demande,
créer un groupe de **test interne**, y ajouter ton utilisateur autorisé et le build.
Installer **TestFlight** depuis l’App Store et ouvrir Coach AI depuis TestFlight.
Ce flux est réservé aux tests internes ; il ne publie pas l’app sur l’App Store,
ne crée pas de lien public et n’invite aucun tiers automatiquement.

Apple peut encore bloquer l’envoi pour un contrat non accepté, des droits insuffisants,
un Bundle ID incorrect ou une fiche inexistante. Le compte, la signature, le traitement
Apple et l’installation physique ne sont pas validés par les tests de compilation.

## Utilisation immédiate en attendant TestFlight

La version web a une icône et un manifeste pour l’écran d’accueil. Ouvrir le serveur
Coach AI dans **Safari → Partager → Sur l’écran d’accueil → Ajouter**. Le guide intégré
se trouve à `/assets/app/install.html`. Cette installation reste la version web :
elle n’active pas le code SwiftUI ni ses notifications natives et demande Internet.
Aucun service worker ne conserve les conversations, activités ou jetons hors ligne.

## Données et confidentialité avant distribution

`PrivacyInfo.xcprivacy` déclare les données santé/fitness, contenu utilisateur et identité
utilisées pour les fonctions de l’app, ainsi que l’usage des préférences locales.
Il ne remplace pas les réponses « Confidentialité de l’app » d’App Store Connect ni
la politique de confidentialité à fournir avant une distribution plus large.
