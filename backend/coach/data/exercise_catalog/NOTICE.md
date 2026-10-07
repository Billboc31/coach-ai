# Catalogue documentaire des exercices

Snapshot public wger du 7 octobre 2026 : 918 exercices, 584 avec une traduction
française ; 217 fiches avec média admissible, dont 49 avec GIF ou vidéo. Ce n’est
pas une bibliothèque d’animations pour chaque exercice. Les fichiers JSON sont
embarqués dans le paquet backend : recherche et correspondances ne nécessitent
ni abonnement, ni appel IA, ni accès à wger à l’exécution. Les médias restent
hébergés chez wger et ne sont chargés qu’à l’ouverture de la fiche (animations
après clic). Une indisponibilité conserve les alternatives image/dessin/YouTube.

Source : https://wger.de/api/v2/exerciseinfo/ ; provenance, date, empreinte du
snapshot et nombres figurent dans `backend/coach/data/exercise_catalog/manifest.json`.
Les données proviennent de l’API publique, sans import du code de l’application
wger (qui a sa propre licence AGPL).

## Licences et attribution

Les licences sont individuelles : `credit`, `text_credit` et `media[].credit`
contiennent la licence, son URL, les auteurs disponibles et les informations de
provenance. La sélection des médias accepte uniquement CC0, CC BY 4.0 et CC BY-SA
3.0/4.0, avec auteur documenté, HTTPS sur wger et chemin média d’exercice. Les
images signalées comme générées par IA sont exclues. Les crédits sont affichés
sur les fiches ; une licence manquante n’est pas remplacée par une licence supposée.

- CC0 : https://creativecommons.org/publicdomain/zero/1.0/
- CC BY 4.0 : https://creativecommons.org/licenses/by/4.0/
- CC BY-SA 3.0 : https://creativecommons.org/licenses/by-sa/3.0/
- CC BY-SA 4.0 : https://creativecommons.org/licenses/by-sa/4.0/

Le snapshot transforme le HTML en texte, limite la description à 1600 caractères,
préfère le français puis l’anglais, conserve les aliases et sélectionne les médias
admissibles. Les aliases français supplémentaires et noms de variantes sont
curatés dans `exercise_catalog.py`. Les données et leurs crédits restent publiés
avec leurs licences individuelles ; les conditions BY/SA doivent être conservées
lors d’une redistribution ou adaptation, y compris commerciale.

## Identités et poids

L’ID canonique est `wger:<id>`. Les IDs privés issus de l’import et les noms d’origine
restent inchangés. Une correspondance exacte non ambiguë peut être affichée directement ;
les formulations équivalentes (ordre, prépositions, pluriels et abréviations usuelles)
sont associées automatiquement si une seule variante correspond. Les détails d’angle,
prise et matériel ne sont pas supprimés. Le bilan du programme liste les noms encore
ambigus, sans revalidation des fiches reconnues. Aucun réimport nécessaire. Une décision
manuelle ou un retrait de correspondance reste prioritaire. Un rapprochement approximatif
reste une suggestion. L’utilisateur peut confirmer,
changer ou retirer une correspondance, avec contrôle de révision.

Le partage des références entre noms exige le même exercice et la même convention
confirmée : charge totale, par haltère, lest, machine ou poids du corps. Le repère
matériel fait aussi partie de la compatibilité ; une machine exige un repère non
vide. Aucun calcul de conversion entre ces conventions. Les anciennes séries avec
variante/unités connues restent figées ; les séries anciennes sans classification
peuvent être rattachées par la décision explicite de l’utilisateur.

## Carte musculaire et bibliothèques d’animations

Les champs muscles et muscles_secondary sont conservés depuis le même snapshot public.
Une silhouette SVG originale, locale et schématique représente les groupes documentés
face/dos : principaux en corail, secondaires en jaune, légende textuelle française.
Le dessin ne copie pas les SVG wger et ne représente pas un degré d’activation.
Un muscle absent reste non renseigné ; les cibles ne sont pas déduites du nom.

ExerciseDB annonce plus de 5000 GIF dans son offre complète :
https://github.com/ExerciseDB/exercisedb-api . Ses conditions d’API exigent un
abonnement actif et interdisent le stockage persistant des données/médias :
https://exercisedb.notion.site/ExerciseDB-API-Terms-of-Use-226983b728ca8090bf7be79564e4b356 .
Sa version gratuite annonce 1500 exercices avec GIF et un usage non commercial
avec attribution : https://oss.exercisedb.dev/docs . Aucun dataset ni média
ExerciseDB n’est importé dans ce lot. Une intégration future doit rester distincte
du snapshot wger et respecter l’offre/licence retenue.
