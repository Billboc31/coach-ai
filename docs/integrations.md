# Contrats des intégrations

Documentation consultée le 7 octobre 2026. Tests réels encore nécessaires.

## Garmin

Adaptateur `garminconnect==0.3.17` : connexion officielle du compte via bibliothèque tierce,
MFA respectée et jetons locaux. Aucun changement des données Garmin : lecture uniquement.
Synchronisation dédupliquée sur activityId. Santé identifiée par date locale du profil.
Une source inaccessible conserve la dernière lecture ; ses erreurs sont exposées dans le
rapport de synchronisation. Une lecture ancienne n’est pas une mesure fraîche (amélioration
HEALTH-02 : provenance et date de lecture par source).

- https://github.com/cyberjunky/python-garminconnect
- https://developer.garmin.com/gc-developer-program/program-faq/

L’API officielle Garmin est le chemin à examiner avant commercialisation. La bibliothèque
personnelle n’est pas une garantie d’éligibilité commerciale.

## ChatGPT : application locale

Parcours dynamique pour applications locales, pas le parcours commercial identity-only.
Le host ID reste stable. Nouveau state, nonce et PKCE par tentative ; durée max 5 minutes.
Callback loopback sur 127.0.0.1, client ID délivré utilisé pour l’échange ; rejet si changement
inattendu sur une reconnexion. JWT vérifié via JWKS : signature RS256, issuer, audience,
expiration et nonce. L’identité précédente doit correspondre avant remplacement des jetons.
Le scope chatgpt.tokens.use.direct est nécessaire. Renouvellement et remplacement atomique
des jetons, verrou de fichier partagé CLI/API. Un seul chat en cours dans le serveur pour ce lot.

Requêtes `/v1/models` puis `/v1/responses`, `store:false`, `stream:true` et historique explicite.
Succès uniquement après événement terminal `response.completed`. Aucun endpoint `backend-api`
ni clé d’API payante en secours. Les modèles proviennent du catalogue du compte.

- https://developers.openai.com/siwc/token-sharing-open-source
- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
- https://developers.openai.com/siwc/token-sharing-open-source/token-reference
- https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations

## Validation manuelle requise

1. Connexion Garmin et MFA avec le compte du propriétaire.
2. Deuxième connexion sans identifiants ; sync répétée sans doublon.
3. Comparaison des séances et indicateurs avec Garmin Connect.
4. Autorisation ChatGPT, catalogue du compte, première réponse utilisant le forfait.
5. Redémarrage, expiration/renouvellement et refus d’autorisation.
6. Vérifier les limites/consommation dans ChatGPT ; aucun crédit API consommé par cette route.

Les mocks permettent de vérifier les contrats applicatifs, pas la disponibilité externe.

## Transfert vers le serveur personnel

Documentation : https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms
Autorisation terminée sur le poste ; envoi HTTPS direct vers l’app authentifiée, sans
redirection. L’import préserve le host ID du runtime et valide les JWT identité et accès
(signature, issuer/audience, subject et client associés), le scope et le catalogue. Le JWT
identité retenu peut être expiré après OAuth ; son expiration n’est pas celle de l’accès.
Le token d’accès doit rester valide. Écriture atomique seulement après validation.
Le transfert CLI retire la copie locale après succès ; l’import UI demande au propriétaire
de cesser d’utiliser la copie source. Test réel Railway/renouvellement encore requis.
