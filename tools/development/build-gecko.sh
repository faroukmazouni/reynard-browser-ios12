#!/bin/sh

set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
FIREFOX_DIR="$ROOT_DIR/engine/firefox"

TARGET="aarch64-apple-ios"

cd "$ROOT_DIR"

if [ ! -d "$FIREFOX_DIR" ]; then
	echo "Missing firefox source at $FIREFOX_DIR"
	echo "Add the submodule, then run tools/development/update-gecko.sh."
	exit 1
fi

rm -f "$FIREFOX_DIR/.mozconfig"

# Apple clang cannot target wasm, which the RLBox sandboxed libraries need.
# Use the WASI SDK's self-consistent clang/linker/sysroot/builtins as the
# wasm toolchain, downloading it if not already present.
WASI_SDK_DIR="$SCRIPT_DIR/wasi-sdk"
WASI_SDK_ARCH="$(uname -m)"
WASI_SDK_URL="https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-33/wasi-sdk-33.0-${WASI_SDK_ARCH}-macos.tar.gz"

if [ ! -d "$WASI_SDK_DIR" ]; then
	echo "Downloading WASI SDK ($WASI_SDK_ARCH)..."
	TMP_DIR="$(mktemp -d)"
	curl -L "$WASI_SDK_URL" -o "$TMP_DIR/wasi-sdk.tar.gz"
	mkdir -p "$WASI_SDK_DIR"
	tar -xzf "$TMP_DIR/wasi-sdk.tar.gz" -C "$WASI_SDK_DIR" --strip-components=1
	rm -rf "$TMP_DIR"
fi

{
	echo "ac_add_options --enable-application=mobile/ios"
	echo "ac_add_options --target=$TARGET"
	echo "ac_add_options --enable-ios-target=12.0"
	echo "ac_add_options --enable-webrtc"
	echo "ac_add_options --enable-optimize"
	echo "ac_add_options --disable-debug"
	echo "ac_add_options --disable-tests"
	echo "export WASM_CC=$WASI_SDK_DIR/bin/clang"
	echo "export WASM_CXX=$WASI_SDK_DIR/bin/clang++"
	echo "ac_add_options --with-wasi-sysroot=$WASI_SDK_DIR/share/wasi-sysroot"
} > "$FIREFOX_DIR/.mozconfig"

if ! rustup target list | grep -q "^$TARGET (installed)"; then
	rustup target add "$TARGET"
fi

cd "$FIREFOX_DIR"
./mach build
