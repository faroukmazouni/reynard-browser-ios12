# iOS 12 Compatibility Gates

This document tracks every place where an iOS 13+ (or later) API was **gated off** for
the iOS 12 backport PoC, so the corresponding iOS-12 **fallbacks** can be found and
implemented later. Each gate currently means: *the feature is simply unavailable / a no-op
on iOS 12* (PoC behavior — no functional replacement yet).

Convention used:
- `@available(iOS 13.0, *)` on a whole type/extension → that type is unavailable on iOS 12.
- `if #available(iOS 13.0, *) { … }` at a call site → the block is skipped on iOS 12.
- A `UICompat` shim (see `Reynard/Client/Extensions/UICompat.swift`) provides real fallbacks
  (semantic colors, grouped-table style, corner curve) — those are NOT feature losses.

Legend: **[SHIM]** = real fallback provided · **[GATE]** = feature disabled on iOS 12 (needs fallback later)

---

## 0. iOS 12.0–12.3 deployment and framework loading — [SHIM]
The iOS 12.1.1 sideload build must use a **12.0** deployment target everywhere,
not 12.4: the app target, the Gecko build, libimobiledevice and the packaged
helper binary.  Those settings live in `Configuration/Reynard.xcconfig`,
`Reynard.xcodeproj`, `tools/development/build-{gecko,idevice}.sh`, and
`tools/release/create-ipa.sh`.

`PhotosUI` and `UniformTypeIdentifiers` first ship in iOS 14; `QuickLookThumbnailing`
first ships in iOS 13.  Their individual uses are availability-gated, but that is
not sufficient if the Mach-O binary has a normal (strong) framework dependency:
dyld would exit before the first availability check.  They are therefore
weak-linked through `Reynard.xcconfig`.

`CryptoKit` was also removed from the iOS 12 app target. `Data.sha256Hex` now
uses the iOS-12-compatible CommonCrypto implementation on every OS version.

---

## 0. Helper extension point (Gecko child-process host) — [SHIM, needs device verification]
`Helper/Info.plist` — `NSExtensionPointIdentifier` changed `com.apple.ar.viewer` (iOS 13.4+) →
`com.apple.app.non-ui-extension.multiple-instances`. The Helper is GeckoView's content/child-process
host (app extension with `NSExtensionActivationRule=FALSEPREDICATE`, `XPCService _ProcessType=App`,
`_MultipleInstances=true`). `com.apple.ar.viewer` is unavailable on iOS 12 → the OS rejects the whole
bundle at install. `com.apple.app.non-ui-extension.multiple-instances` is the older multi-instance
process-spawning point (private API; Ian McDowell's technique, iOS 12/13 era) that `ar.viewer` later
replaced. **MUST be verified on an iOS 12 device**: (a) installs, (b) web content actually renders
(i.e. child processes spawn). If content is blank, this point/config needs revisiting.

---

## 0b. Swift Concurrency RUNTIME (libswift_Concurrency) — [FIXED — was the launch crash]
Removing `async`/`await` was not enough: `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` + explicit
`@MainActor`/`nonisolated` attributes made the compiler reference `MainActor` (which lives in
`libswift_Concurrency.dylib`, min iOS 13), so that runtime got autolinked + embedded → **dyld could
not load it on iOS 12 → instant launch crash** ("white screen → springboard", Xcode "Failed looking
up pid of launched process").
Fix:
- `Reynard.xcodeproj/project.pbxproj` (×4 configs): `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor` → `nonisolated`; `SWIFT_APPROACHABLE_CONCURRENCY = YES` → `NO`.
- Stripped all `@MainActor` (57) and `nonisolated` (11) attributes from every `.swift` (Swift 5 mode
  doesn't enforce isolation, so this is behavior-preserving; main-thread correctness now relies on the
  existing `DispatchQueue.main` usage, same as pre-concurrency UIKit code).
- Verified: `libswift_Concurrency.dylib` no longer embedded; no binary links it.

## 1. Semantic colors / table style / corner curve — [SHIM] (done, no fallback needed)
- `Reynard/Client/Extensions/UICompat.swift` — `UIColor.app*` semantic colors, `UITableView.Style.appGrouped`, `CALayer.applyContinuousCornerCurve()`. Swept across ~96 files. Real light-mode fallbacks on iOS 12.
- Haptics: `Reynard/Client/Shared/Haptics.swift` — `.rigid` → `.heavy` (iOS 12 fallback). [SHIM]
- `UIColor.appSystemYellow` — iOS 13's `systemYellow`, with a fixed yellow fallback
  for iOS 12. Used by the donation recommendation card, which is constructed on
  initial homepage display. [SHIM]

## 2. Context menus (UIContextMenuInteraction / UIMenu / UIAction) — [GATE]
_iOS 12 has no context-menu API. All gated off; long-press does nothing on iOS 12._

Homepage / Library (all `@available(iOS 13.0, *)` unless noted):
- `Homepage/Sections/Favorites/FavoritesItemActions.swift:11` — `struct FavoritesItemActions` — favorites bookmark/folder long-press menu
- `Homepage/Sections/Favorites/FavoritesItemActions.swift:72` — `extension FavoritesSectionViewController: UIContextMenuInteractionDelegate`
- `Homepage/Sections/Favorites/FavoritesSectionViewController.swift:49` — `contextMenuInteraction` property retyped `UIContextMenuInteraction?`→`UIInteraction?` (stored props can't be `@available`)
- `Homepage/Sections/Favorites/FavoritesSectionViewController.swift` — `removeFavoriteContextMenuInteraction`, `presentFavoriteContextMenu` gated; caller wrapped in `if #available`
- `Homepage/Sections/FrequentlyVisited/FrequentlyVisitedSiteActions.swift:11,45` — `struct` + delegate extension
- `Homepage/Sections/FrequentlyVisited/FrequentlyVisitedSectionViewController.swift:~246` — `addInteraction(...)` wrapped in `if #available`
- `Homepage/Sections/RecentlyClosedTabs/RecentlyCloseTabItemActions.swift:11,51` — `struct` + delegate extension
- `Homepage/Sections/RecentlyClosedTabs/RecentlyClosedTabsSectionViewController.swift:~283` — `addInteraction(...)` wrapped in `if #available`
- `Library/Bookmarks/BookmarksViewController.swift` — `makeBookmarkMenu`, `makeSortMenu` gated
- `Library/Downloads/DownloadsViewController.swift` — `makeDownloadsMenu` gated
- (already guarded, no change) `Library/LibrarySharedUtils.swift`, `SiteSettings/SiteSettingsViewController.swift`

ContextMenu / Chrome / ContentView (all `@available(iOS 13.0, *)` unless noted):
- `ContextMenu/ContextMenuCoordinator.swift` — `interaction` prop retyped→`UIInteraction?`; `configure()` attach wrapped `if #available`; `makeTargetedPreview`, delegate extension gated — web-view link/image context menu
- `ContextMenu/ImagePreview/ImagePreviewMenu.swift` / `LinkPreview/LinkPreviewMenu.swift` — `struct` gated — image/link context menus
- `Chrome/AddressBar/AddressBarMenu.swift` — `Identifier`, `makeMenu` gated — address-bar menu
- `Chrome/AddressBar/AddressBar.swift` — `addonsMenu` prop→`Any?`; `updateMenu`, `applyLeadingButtonState` menu attach wrapped `if #available` — address-bar leading-button menu
- `Chrome/AddressBar/AddressBarButton.swift` — `pendingMenuAfterDismissal`/`legacyMenuDelegate` props→`Any?`; `UIContextMenuInteraction` creation, `handleLegacyPrimaryTap`, `setMenuPreservingPresentation`, `replacementMenu`, `legacyContextMenuWillEnd`, `LegacyContextMenuDelegate` gated — address-bar long-press menu
- `ContentView/WebContent/FilePicker/FilePickerMenu.swift` — `presentMenuFromAnchorButton` `@available(iOS 14)` (only reached from existing iOS-14 path)
- `ContentView/WebContent/SelectionActionMenu/SelectionActionMenuHostView.swift` — `UIMenuController.showMenu/hideMenu` wrapped `if #available(iOS 13)` — text-selection edit menu
- `ContentView/WebContent/SelectPicker/SelectPicker.swift` — `buildMenuElements` `@available(iOS 14)`
- (no change) `ContextMenuTabActions.swift`, `WebContentView.swift`, `FilePickerMenuAnchorButton.swift`, `SelectPickerMenuAnchorButton.swift`, `LibrarySharedUtils.swift`, `SiteSettingsViewController.swift`

## 3. SF Symbols + symbol configuration (iOS 13+) — [FIXED — icons now render on iOS 12]
The `reynard.*` icons were 60 `.symbolset` assets, which iOS 12 cannot load (`UIImage(named:)` → nil → blank icons). They are now converted to universal **template `.imageset`s** (same asset names, so all `UIImage(named: "reynard.…")` call sites are unchanged and work on iOS 12 and iOS 13+). Regenerate with `tools/development/generate-ios12-icons.py` (extracts each symbol's Regular glyph from the SF Symbols export SVG and rasterizes @1x/2x/3x template PNGs via qlmanage). Trade-off: iOS 13+ also uses the raster icons, so `setPreferredSymbolConfiguration`/`applyingSymbolConfiguration` (still `if #available(iOS 13)`-gated) no-op on non-symbol images and icons render at their intrinsic size.
Legacy shim (barely used): `UIImage+Symbol.swift` (`UIImage.appSymbol` → nil on iOS 12).
- 13 files gated (icons load unstyled on iOS 12): `Chrome/ActionBar/PageZoom/PageZoomActionBar`, `Chrome/Toolbar/ToolBarButton`, `Homepage/Sections/Recommendations/{Donation,Performance}RecommendationViewController`, `Homepage/Sections/UpdateAvailable/UpdateAvailableViewController`, `Library/LibrarySection`, `Library/Settings/.../AddressBarPosition/AddressBarPositionOptionControl`, `.../AppAppearance/AppAppearanceOptionControl`, `Sidebar/SidebarActionCell`, `TabBar/TabBarCell`, `TabOverview/TabOverviewCard`, `TabOverview/.../TabOverviewToolbarButton`, `JIT/Interface/JITFailure`
- `Chrome/AddressBar/AddressBarButton.swift`, `AddressBarDismissButton.swift` — `setPreferredSymbolConfiguration` gated

## 3b. Dynamic (dark-mode) UIColor — `UIColor { traitCollection … }` (iOS 13+) — [GATE]
iOS-12 fallback = the light-appearance branch.
- `Chrome/AddressBar/AddressBarDismissButton.swift`, `AddressBar.swift`, `AddressBarGestures.swift`, `Homepage/Sections/PrivateBrowsing/PrivateBrowsingSectionViewController.swift`

## 5. Other iOS-13+ APIs — [SHIM]/[GATE]
- `UICompat.swift` — `UIBlurEffect.Style.appChromeMaterial/appMaterial` (→ `.regular` on 12); `UISearchBar.compatAlignmentView` (search field on 13+, bar on 12, layout only) [SHIM]. Swept: `PageZoomActionBar`, `ChromeOverlayContentView`; `searchTextField` in Bookmarks/History/Downloads VCs.
- `Data+SHA256.swift` — `Data.sha256Hex` via CryptoKit on 13+, CommonCrypto on 12 [SHIM]. Used by `FaviconStore`, `SiteMetadataStore`.
- `Search/UserDataSuggestionCell.swift` — `RelativeDateTimeFormatter` → short absolute date on iOS 12 [SHIM]
- `Library/LibraryTabBarStyle.swift` — `UITabBarAppearance` gated; iOS 12 uses legacy `barTintColor`/tint [SHIM]
- `Sidebar/SidebarMenuViewController.swift` — diffable data source stored as `AnyObject?` behind `@available(iOS 13)` accessor; setup/use gated → **sidebar list empty on iOS 12** [GATE]
- `Library/Downloads/DownloadFileIconProvider.swift` — `QLThumbnailGenerator` gated; iOS 12 uses document-interaction placeholder icons [SHIM]
- `Library/{Bookmarks,Downloads}ViewController.swift` — `legacy*MenuDelegate` props → `AnyObject?`
- `TabBar/TabBarCollection.swift`, `TabOverview/TabOverviewCard.swift`, `AddressBar/AddressBarDismissButton.swift` — `UITraitCollection.current` → the view's own `traitCollection` (iOS 12-safe)
- `JIT/Interface/JITFailure.swift` — `monospacedSystemFont` → Menlo on iOS 12; `isModalInPresentation` gated
- `Addons/AddonCoordinator.swift`, `ContentView/.../FilePickerMediaPicker.swift`, `JITFailure.swift` — `isModalInPresentation` gated (no interactive sheet-dismissal on iOS 12)
- `Addons/AddonPermissionSupport.swift` — `ListFormatter` → comma-join on iOS 12 [SHIM]
- `ContentView/WebContent/FilePicker` — `UIAdaptivePresentationControllerDelegate`
  and assignments to `presentationController.delegate` are iOS 13+; both are
  now guarded. iOS 12 continues to receive cancellation through the document
  and image picker delegates. [SHIM]
- `main.swift` — `configureUnsandboxedAppDataDirectories` (iOS 13.x-only) call-site narrowed to skip iOS 12 [GATE — revisit if unsandboxed iOS-12 builds need MOZ_APP_DATA setup]

## 4. Scene lifecycle (UIWindowScene / UISceneConfiguration) — [GATE] + [SHIM]
- `SceneDelegate.swift:10` — whole class `@available(iOS 13.0, *)` [GATE]. Creates the `BrowserViewController` window on iOS 13+ (via the Info.plist `UIApplicationSceneManifest`).
- `main.swift` — **iOS-12 window bootstrap** [SHIM]. The engine calls `UIApplicationMain` with its own `AppShellDelegate` (`nsAppShell.mm:308`), so the app's `AppDelegate`/`SceneDelegate` are not the running delegate for window creation on iOS 12 (SceneDelegate is scene-manifest-driven and iOS 13+ only). On iOS 12 we register a `UIApplication.didFinishLaunchingNotification` observer (before `GeckoRuntime.main`) that builds the `BrowserViewController` window, mirroring `SceneDelegate`. Without this the app launches to a 100% black screen (no delegate ever creates a window).
- `AppDelegate.swift` — NOT the running UIApplication delegate (`AppShellDelegate` is); its methods do not execute. Kept as a no-op with an explanatory note. [note]
- `Client/Extensions/UIApplication+Presentation.swift` — `appKeyWindow` helper (scenes on 13+, `windows` on 12); `topViewController()` + split-screen helpers routed through it [SHIM]
- `Client/Interface/Appearance/AppAppearanceController.swift` — `apply()` no-ops on iOS 12 (no dark mode); `userInterfaceStyle(for:)` `@available(iOS 13.0, *)` [GATE]
- `Client/Interface/Sidebar/SidebarCoordinator.swift:172` — status bar height via `statusBarManager` on 13+, `UIApplication.statusBarFrame` on 12 [SHIM]
- `JIT/JITController.swift:334` — `canPresentFailureUI` returns true on iOS 12 (no scenes) [SHIM]
- `Client/Interface/BrowserViewController.swift` — `currentInterfaceOrientation` helper (windowScene on 13+, `statusBarOrientation` on 12); 3 sites routed through it [SHIM]
