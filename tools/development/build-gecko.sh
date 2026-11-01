#!/bin/sh

set -euo pipefail

BUILD_ACTION="${1:-build}"
case "$BUILD_ACTION" in
	build|configure) ;;
	*) echo "Usage: $0 [build|configure]" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
FIREFOX_DIR="$ROOT_DIR/engine/firefox"

TARGET="aarch64-apple-ios"

cd "$ROOT_DIR"

if [ ! -x "$FIREFOX_DIR/mach" ]; then
	echo "Missing firefox source at $FIREFOX_DIR"
	echo "Add the submodule, then run tools/development/update-gecko.sh."
	exit 1
fi

# Pin both SDKs to the selected Xcode. Gecko also compiles tools that run on
# macOS, so a sufficiently new iOS SDK alone does not satisfy its requirements.
export MACOS_SDK_DIR="${MACOS_SDK_DIR:-$(xcrun --sdk macosx --show-sdk-path)}"
export IPHONEOS_SDK_DIR="${IPHONEOS_SDK_DIR:-$(xcrun --sdk iphoneos --show-sdk-path)}"

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
	curl --fail --location --retry 3 "$WASI_SDK_URL" -o "$TMP_DIR/wasi-sdk.tar.gz"
	mkdir -p "$WASI_SDK_DIR"
	tar -xzf "$TMP_DIR/wasi-sdk.tar.gz" -C "$WASI_SDK_DIR" --strip-components=1
	rm -rf "$TMP_DIR"
fi

{
	echo "ac_add_options --enable-application=mobile/ios"
	echo "ac_add_options --target=$TARGET"
	echo "ac_add_options --enable-ios-target=12.0"
	# Release builds do not bootstrap by default. Gecko needs a newer LLVM
	# toolchain than the Apple compiler shipped with Xcode 15.4.
	echo "ac_add_options --enable-bootstrap"
	echo "ac_add_options --enable-webrtc"
	echo "ac_add_options --enable-optimize"
	echo "ac_add_options --disable-debug"
	echo "ac_add_options --disable-debug-symbols"
	echo "ac_add_options --disable-tests"
	if [ -n "${GECKO_BUILD_JOBS:-}" ]; then
		# MOZ_PARALLEL_BUILD takes a plain worker count.  Unlike `make -j`,
		# its value is parsed directly as an integer by mach.
		echo "mk_add_options MOZ_PARALLEL_BUILD=${GECKO_BUILD_JOBS}"
	fi
	echo "export WASM_CC=$WASI_SDK_DIR/bin/clang"
	echo "export WASM_CXX=$WASI_SDK_DIR/bin/clang++"
	echo "ac_add_options --with-wasi-sysroot=$WASI_SDK_DIR/share/wasi-sysroot"
} > "$FIREFOX_DIR/.mozconfig"

if ! rustup target list | grep -q "^$TARGET (installed)"; then
	rustup target add "$TARGET"
fi

# Gecko probes Rustup proxies using a synthetic argv[0]. Homebrew's wrapper
# scripts discard that name, so supply the actual installed toolchain binaries.
export RUSTC="${RUSTC:-$(rustup which rustc)}"
export CARGO="${CARGO:-$(rustup which cargo)}"

cd "$FIREFOX_DIR"
./mach "$BUILD_ACTION"
