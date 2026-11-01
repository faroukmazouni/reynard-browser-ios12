# iOS 12.1.1 Impactor build

This project includes a dedicated unsigned IPA path for iOS 12.0–12.3.  It is
intended for an arm64 iPad running iOS 12.1.1, then re-signed by Cydia Impactor
with the device owner's Apple development certificate.

## Build

If your Mac cannot run Xcode 15.4, the repository includes a GitHub Actions
workflow. Commit and push the project, open the **Actions** tab on GitHub, choose
**Build iOS 12 Impactor IPA**, click **Run workflow**, and download the artifact
named `Reynard-iOS12-Impactor` when it finishes. This workflow uses a macOS 14
runner with Xcode 15.4 and does not need your Apple signing credentials.

For a local build, use the steps below on a Mac that can run Xcode 15.4.

Use an Xcode version with an iOS 12 SDK/deployment target, Python 3, Rust,
Cargo, and ldid.  From the project root:

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

This avoids iOS 13/14 framework-load crashes and supports iOS 12.1.1 as the
minimum OS, but it cannot grant a stock iOS 12 device private browser or JIT
entitlements.  If the app opens but web content remains blank or the process
is terminated while Gecko starts, capture the device crash log; that points to
the Apple code-signing/JIT restriction rather than an iOS-version deployment
failure.  A jailbroken device can use the project's separate jailbroken build
path instead.
