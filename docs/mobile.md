# Interface mobile

La barre du bas propose Accueil, Coach, Activités et Muscu. Plus ouvre Planning,
Profil, Mémoire et Connexions. Sur ordinateur, les huit pages restent dans la sidebar.
Les zones de sécurité de l'iPhone sont prises en compte sans désactiver le zoom.

Les champs utilisent une taille de texte de 16 px sur petit écran. Les formulaires,
titres longs et commandes se réorganisent ; seuls tableaux, filtres et listes
d'exercices défilent horizontalement. Le calendrier montre des pastilles de statut,
avec les noms complets dans l'agenda du jour. La discussion défile avec la page.

En séance, les réglages et illustrations de référence se déplient. Les séries gardent
leur autosave, leurs limites et leur validation. Le poids propose un clavier décimal,
les reps/secondes un clavier numérique, et la case de validation mesure 44 px.

## Validation

Vérification locale Chromium avec API simulée et données fictives, aux largeurs
320, 375, 390, 430, 768 et 1440 px : vue d'ensemble, coach et rédaction, liste et fiche
d'activité avec courbes, planning et formulaire, programme et saisie de séance,
profil, mémoire et connexions. Contrôles : aucun débordement horizontal global,
taille des champs, accès à chaque page via Plus, fermeture du menu par sélection
ou Échap, changement temps/distance, exploration de la courbe et saisie/validation
d'une série conservée après autosave simulé. Captures examinées à 390 px.

Cette vérification n'utilise ni compte Garmin ni session Railway. Le comportement
du clavier logiciel, de la barre Safari et des zones de sécurité nécessite encore
un essai sur un iPhone réel. Dans l'app déployée, vérifier notamment :

- Ouvrir Plus, choisir une page puis revenir à Coach sans défilement latéral global.
- Saisir un message et accéder au bouton Envoyer avec le clavier ouvert.
- Ouvrir une séance, saisir kg/reps et valider une série avec le clavier ouvert.
- Consulter un jour du calendrier et modifier une séance.
- Passer en paysage et utiliser les formulaires et la navigation.

Le mode hors ligne complet et l'installation PWA ne sont pas inclus dans ce lot.
