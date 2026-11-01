#!/bin/sh

# Make an unsigned archive for Cydia Impactor on iOS 12.0–12.3 devices.
# Impactor must be the only signer: it needs to sign the host app, the Gecko
# helper extension, the share extension, and every embedded framework with the
# same development team.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/ios12-impactor"
PROJECT_PATH="$ROOT_DIR/browser/Reynard.xcodeproj"
XCCONFIG_PATH="$ROOT_DIR/browser/Configuration/Reynard.xcconfig"

rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

cp "$XCCONFIG_PATH" "$DIST_DIR/Reynard.xcconfig"
BUILD_SHA="$(git -C "$ROOT_DIR" rev-parse --short=7 HEAD 2>/dev/null || echo local)"
sed -i '' "s/CURRENT_BUILD = .*/CURRENT_BUILD = $BUILD_SHA/" "$DIST_DIR/Reynard.xcconfig"

xcodebuild archive \
  -scheme "Reynard" \
  -archivePath "$DIST_DIR/Reynard.xcarchive" \
  -project "$PROJECT_PATH" \
  -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  -arch arm64 \
  -configuration Release \
  -xcconfig "$DIST_DIR/Reynard.xcconfig" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO \
  CODE_SIGN_IDENTITY="" \
  DEVELOPMENT_TEAM=""
