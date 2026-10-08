# Interface mobile

La barre du bas propose Accueil, Coach, Activités et Muscu. Plus ouvre Planning,
Profil, Mémoire et Connexions. Sur ordinateur, les huit pages restent dans la sidebar.
Les zones de sécurité de l'iPhone sont prises en compte sans désactiver le zoom.

Les champs utilisent une taille de texte de 16 px sur petit écran. Les formulaires,
titres longs et commandes se réorganisent ; seuls tableaux, filtres et listes
d'exercices défilent horizontalement. Le calendrier montre des pastilles de statut,
avec les noms complets dans l'agenda du jour. La discussion défile avec la page.
Les cartes d'activité sont des blocs verticaux, sans héritage du flex des boutons.
Les dates des filtres sont sur deux lignes distinctes avec une largeur bornée, pour
éviter le chevauchement des contrôles natifs Safari.

Le catalogue IA est chargé automatiquement depuis la session ChatGPT existante,
sans déclencher une nouvelle autorisation ni une inférence. Sol est préféré par nom
ou identifiant explicite dans ce catalogue ; aucun identifiant non proposé n'est inventé.
Un choix manuel enregistré dans le navigateur prime, s'il reste disponible. Le bouton
Actualiser les modèles permet de réessayer une erreur de catalogue. Ouvrir Coach ou
recevoir un nouveau message rejoint la fin de discussion et le champ de rédaction.
Une actualisation du dashboard avec les mêmes messages ne déplace pas la lecture.

En séance, les réglages et illustrations de référence se déplient. Les séries gardent
leur autosave, leurs limites et leur validation. Le poids propose un clavier décimal,
les reps/secondes un clavier numérique, et la case de validation mesure 44 px.
Les séances en cours s'ouvrent désormais dans un écran dédié : navigation générale masquée,
un exercice et une série à la fois, champs agrandis et bouton Valider. Validation rejoint la
prochaine série non validée ; le poids précédent se recopie uniquement par action explicite.
Détails permet de retrouver technique/vidéo/historique et les outils de résolution de conflit.
Quitter attend la sauvegarde. La liste des séances permet la suppression confirmée des
séances inachevées et de leurs séries ; les séances terminées n'offrent pas cette commande.

## Validation

Vérification locale Chromium avec API simulée et données fictives, aux largeurs
320, 375, 390, 430, 768 et 1440 px : vue d'ensemble, coach et rédaction, liste et fiche
d'activité avec courbes, planning et formulaire, programme et saisie de séance,
profil, mémoire et connexions. Contrôles : aucun débordement horizontal global,
taille des champs, accès à chaque page via Plus, fermeture du menu par sélection
ou Échap, changement temps/distance, exploration de la courbe et saisie/validation
d'une série conservée après autosave simulé. Captures examinées à 390 px.
Vérification complémentaire avec 30 messages fictifs : ouverture au dernier échange
sur téléphone, scroll du conteneur sur tablette/ordinateur, modèle Sol choisi sans clic,
envoi de la question avec ce modèle, accès à la rédaction après réponse, et conservation
d'un choix manuel de modèle après rechargement. Sélection testée aussi avec Sol absent
ou un ancien choix retiré du catalogue.

Un lot complémentaire à ces six largeurs vérifie le mode dédié, deux séries poids/reps
et autosave, changement d'exercice, aller-retour détails/mode simple sans perte, sortie,
annulation puis confirmation de suppression d'une séance en cours. Tests API locaux :
ownership, origine autorisée, révision périmée, refus d'une séance terminée et absence de
résurrection après suppression. Ces données sont fictives.

Cette vérification n'utilise ni compte Garmin ni session Railway. Le comportement
du clavier logiciel, de la barre Safari et des zones de sécurité nécessite encore
un essai sur un iPhone réel. Dans l'app déployée, vérifier notamment :

- Ouvrir Plus, choisir une page puis revenir à Coach sans défilement latéral global.
- Saisir un message et accéder au bouton Envoyer avec le clavier ouvert.
- Ouvrir une séance, saisir kg/reps et valider une série avec le clavier ouvert.
- Consulter un jour du calendrier et modifier une séance.
- Passer en paysage et utiliser les formulaires et la navigation.

Le mode hors ligne complet et l'installation PWA ne sont pas inclus dans ce lot.
