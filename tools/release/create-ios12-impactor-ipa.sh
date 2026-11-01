#!/bin/sh

# Package the unsigned archive produced by build-ios12-impactor.sh.  Do not
# use create-ipa.sh here: it rewrites bundle identifiers after archiving for
# the project's own release flow.  Impactor must receive an untouched bundle
# tree so it can re-sign all nested code consistently.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/ios12-impactor"
APP_DIR="$DIST_DIR/Reynard.xcarchive/Products/Applications"
WORK_DIR="$DIST_DIR/package"
IPA_PATH="$DIST_DIR/Reynard-iOS12-Impactor.ipa"

if [ ! -d "$APP_DIR" ]; then
  echo "Missing archive output at $APP_DIR"
  echo "Run tools/release/build-ios12-impactor.sh first."
  exit 1
fi

APP_PATH="$(find "$APP_DIR" -maxdepth 1 -type d -name '*.app' | head -n 1)"
if [ -z "$APP_PATH" ]; then
  echo "No .app found in $APP_DIR"
  exit 1
fi

for extension in "Reynard Helper.appex" "OpenIn.appex"; do
  if [ ! -d "$APP_PATH/PlugIns/$extension" ]; then
    echo "Missing required embedded extension: $extension"
    exit 1
  fi
done

rm -rf "$WORK_DIR" "$IPA_PATH"
mkdir -p "$WORK_DIR/Payload"
ditto "$APP_PATH" "$WORK_DIR/Payload/$(basename "$APP_PATH")"

(
  cd "$WORK_DIR"
  zip -qry "$IPA_PATH" Payload -x '._*' -x '.DS_Store' -x '__MACOSX'
)

echo "Created $IPA_PATH"
echo "Install it with Impactor without removing either embedded app extension."
