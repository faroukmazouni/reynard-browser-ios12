# iOS 12.1.1 Impactor build

This project includes a dedicated unsigned IPA path for iOS 12.0–12.3.  It is
intended for an arm64 iPad running iOS 12.1.1, then re-signed by Cydia Impactor
with the device owner's Apple development certificate.

## Build

If your Mac cannot run Xcode 15.4, the repository includes a GitHub Actions
workflow. Commit and push the project, open the **Actions** tab on GitHub, choose
**Build iOS 12 Impactor IPA**, click **Run workflow**, and download the artifact
named `Reynard-iOS12-Impactor` when it finishes. The workflow checks the Swift
project with Xcode 15.4 first, builds Gecko separately with Xcode 16.4 (Gecko
requires iOS SDK 18.4 or newer), then uses Xcode 15.4 to link the Swift app and
package the result. Both builds explicitly target iOS 12.0. No Apple signing
credentials are needed. Engine and app diagnostics are uploaded even on failure.

The macOS 14 runner needed for Xcode 15.4 is scheduled to retire on November 2,
2026. After that, the final app job needs a separately provided Sonoma runner
with Xcode 15.4; substituting a newer Xcode will not preserve iOS 12 support.

For a local build, use the steps below on a Mac that can run Xcode 15.4.

The Xcode project now uses explicit source membership compatible with Xcode
15.4. This version includes the iOS 17.5 SDK and can target iOS 12.0. Python 3
and Rust/Cargo are required; ldid is only needed for the separate jailbroken
packaging path. Gecko itself needs an additional Xcode/SDK installation with
an iOS SDK of at least 18.4. Select that installation for `build-gecko.sh`, then
select Xcode 15.4 for `build-ios12-impactor.sh`. The workflow automates this
split across two machines. From the project root:

```sh
./tools/development/update-gecko.sh
./tools/development/apply-patches.sh
./tools/development/build-idevice.sh
./tools/development/build-gecko.sh
./tools/release/build-ios12-impactor.sh
./tools/release/create-ios12-impactor-ipa.sh
```

The resulting file is:

```
dist/ios12-impactor/Reynard-iOS12-Impactor.ipa
```

The packaging script checks the actual Mach-O deployment minimum of every
embedded binary against iOS 12.1.1, verifies Gecko/helper files, and checks
bundled library dependencies. It stops instead of creating an IPA if these
checks fail. These static checks cannot replace launching on the iPad.

Do not use `create-ipa.sh` for this variant.  Its normal-release packaging
changes bundle identifiers after archiving and also creates packages that rely
on private entitlements; neither behavior is right for a development-signed
Impactor install.

## Install with Cydia Impactor

Install `Reynard-iOS12-Impactor.ipa` and leave **both** embedded extensions in
the IPA: `Reynard Helper.appex` starts Gecko content processes and
`OpenIn.appex` is the share extension.  If a sideload tool strips either one,
this is not a functional build even if the host application opens.

Trust the resulting development certificate in Settings before launching.
Development provisioning expires, so the app must be re-signed before that
certificate expires.

## Limitations

These changes address known build and API compatibility problems; a complete
IPA still needs to be built and tested on iOS 12.1.1. The unsigned package must
be re-signed before installation. Gecko includes an interpreter fallback when
JIT is unavailable, so lack of JIT alone does not establish the cause of a
blank page or crash. The helper extension's private extension point and process
launching on a stock iOS 12 device remain unverified. Capture the device crash
log if launch fails so the actual cause can be diagnosed.
