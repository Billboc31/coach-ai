# Catalogue RepDB uniquement

609 exercices du snapshot RepDB gratuit épinglé dans coach.repdb. Chaque fiche dispose
d’illustrations en couleur (positions de départ/fin ou une position pour les maintiens).
Aucune animation payante ni ancienne fiche wger n'est proposée dans le catalogue actif.

Exercise data by [RepDB (repdb.co)](https://repdb.co).
[Licence Free Tier v1.0](https://github.com/RepDB/exercise-dataset/blob/main/LICENSE-DATA.md) :
utilisation personnelle/commerciale dans l'app avec attribution. Pas de redistribution
comme dataset/API, ni d'utilisation des images comme référence/entrée de modèles génératifs.
Les illustrations du fournisseur ont été créées avec des outils IA. Elles restent chez lui.

Le build Docker télécharge le snapshot pour l'application. Les fichiers générés ne sont
jamais republiés dans git. En local : `PYTHONPATH=backend python -m coach.repdb` avant démarrage.
La CI installe le même snapshot avant les tests ; aucune donnée utilisateur n'est envoyée.

## Français et anglais

L'identité est `repdb:<slug>`, indépendante de la langue. Les noms français, synonymes,
abréviations (DC, DVP, SDT, DB) et pluriels enrichissent les noms anglais. Les 90 labels
français sont curatés ; le reste conserve son nom anglais et reste recherchable. Les
consignes du fournisseur restent en anglais dans la version gratuite. Les précisions
barre/haltères, angle, prise et machine sont conservées. Une proposition approximative
n'est jamais associée automatiquement. Une fiche liée n'est pas un exercice individuel.

## Migration et conservation

Seules les associations actives wger sont nettoyées. Une correspondance documentée est
migrée vers RepDB ; sa version originale est archivée dans la même donnée propriétaire.
Sans correspondance précise, l'association devient libre et sa convention est à repréciser.
Les refus explicites et associations RepDB existantes sont conservés. La migration est
idempotente ; la révision empêche un ancien formulaire d'écraser la nouvelle décision.

Les IDs privés, programmes, noms Excel, séries et performances originales ne changent pas.
Les références historiques acceptent les anciens IDs uniquement pour les équivalences
précises et des conventions/repères compatibles. La carte musculaire reprend les groupes
principaux/secondaires de RepDB, sans déduire des cibles depuis le nom.
