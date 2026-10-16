#!/usr/bin/env bash
# Run only on a trusted macOS GitHub runner. Never enable shell tracing here.
set -euo pipefail
umask 077

required=(ASC_KEY_ID ASC_ISSUER_ID ASC_PRIVATE_KEY APPLE_TEAM_ID COACH_BUNDLE_ID GITHUB_RUN_NUMBER)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "::error::Configuration absente : $name. Consulte ios/TESTFLIGHT.md."
    exit 1
  fi
done
[[ "$ASC_KEY_ID" =~ ^[A-Z0-9]{10}$ ]] || { echo '::error::Key ID Apple invalide.'; exit 1; }
[[ "$APPLE_TEAM_ID" =~ ^[A-Z0-9]{10}$ ]] || { echo '::error::Team ID Apple invalide.'; exit 1; }
[[ "$ASC_ISSUER_ID" =~ ^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$ ]] || { echo '::error::Issuer ID Apple invalide.'; exit 1; }
[[ "$COACH_BUNDLE_ID" =~ ^[A-Za-z0-9]+([.-][A-Za-z0-9]+)+$ ]] || { echo '::error::Bundle ID invalide.'; exit 1; }
[[ "$GITHUB_RUN_NUMBER" =~ ^[1-9][0-9]*$ ]] || { echo '::error::Numéro de build invalide.'; exit 1; }

private_dir=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/coach-testflight.XXXXXX")
cleanup() { rm -rf "$private_dir"; }
trap cleanup EXIT
key_path="$private_dir/AuthKey_${ASC_KEY_ID}.p8"
printf '%s\n' "$ASC_PRIVATE_KEY" > "$key_path"
unset ASC_PRIVATE_KEY
if ! openssl pkey -in "$key_path" -noout >/dev/null 2>&1; then
  echo '::error::Clé privée Apple incompatible ; utilise le contenu original du fichier .p8.'
  exit 1
fi

archive_path="$private_dir/CoachAI.xcarchive"
# Build the real iPhone archive without a local signing identity. Distribution
# signing happens during export through Apple's cloud-managed certificate.
xcodebuild archive -project ios/CoachAI.xcodeproj -scheme CoachAI \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$archive_path" \
  PRODUCT_BUNDLE_IDENTIFIER="$COACH_BUNDLE_ID" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" CURRENT_PROJECT_VERSION="$GITHUB_RUN_NUMBER" \
  CODE_SIGNING_ALLOWED=NO

export COACH_EXPORT_PLIST="$private_dir/ExportOptions.plist"
python3 - <<'PY'
import os
import plistlib
with open(os.environ['COACH_EXPORT_PLIST'], 'wb') as stream:
    plistlib.dump({
        'method': 'app-store-connect',
        'destination': 'upload',
        'signingStyle': 'automatic',
        'teamID': os.environ['APPLE_TEAM_ID'],
        'manageAppVersionAndBuildNumber': True,
        'uploadSymbols': True,
        'testFlightInternalTestingOnly': True,
    }, stream)
PY
xcodebuild -exportArchive -archivePath "$archive_path" \
  -exportOptionsPlist "$COACH_EXPORT_PLIST" \
  -exportPath "$private_dir/export" -allowProvisioningUpdates \
  -authenticationKeyPath "$key_path" \
  -authenticationKeyID "$ASC_KEY_ID" \
  -authenticationKeyIssuerID "$ASC_ISSUER_ID"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  cat >> "$GITHUB_STEP_SUMMARY" <<'SUMMARY'
## Envoi à Apple terminé
Le binaire a été envoyé à App Store Connect. Il n'est pas encore installé ni
nécessairement disponible : attendre le traitement Apple, puis attribuer le build
au groupe de test interne et ouvrir TestFlight sur l'iPhone.
Aucune publication App Store ni invitation de testeur externe n'a été effectuée.
SUMMARY
fi
