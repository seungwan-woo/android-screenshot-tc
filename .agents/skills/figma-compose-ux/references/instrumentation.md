# Temporary Compose instrumentation and runtime evidence

## Choose an evidence layer

| Source | What it gives | Limits |
|---|---|---|
| `adb exec-out screencap -p` | Physical display pixels | No semantic identity or task intent |
| UI Automator XML | Accessibility nodes, bounds, text/state, exported resource IDs | Semantics merging, hidden/lazy nodes and accessibility filtering omit composables |
| Compose test, unmerged Semantics | Test tags, semantic parent/children, properties and bounds | Still not the full composition/call tree |
| Android Studio Layout Inspector | Interactive Compose/layout inspection on supported debug app/tool versions | A separate development tool; no stable generic adb composition dump assumed here |
| `WindowInsets` test probe | Actual per-edge visible system-bar insets | Must match the screenshot window/display/time; cutout and IME need an explicit policy |

UI Automator cannot add a Compose `testTag` to an already installed APK. A root flag alone also does not assign tags to every composable. Tag selected source components in a test build, or use an existing test hook. Layout Inspector is useful for investigation; it is not substituted for machine-readable CI evidence.

## Minimal source edits after inspecting actual code

For modern Compose, the essential pattern is:

```kotlin
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId

// Apply once high in this screen's hierarchy.
Modifier.semantics { testTagsAsResourceId = true }
// Apply a stable, curated tag to a real layout/semantic node.
Modifier.testTag("ux.checkout.submit")
```

Use the project's Compose version; add an opt-in only if its compiler requires one. Forward modifiers through mapped components. A reusable component called twice needs instance-specific tags. Do not insert layout wrappers just to tag an otherwise non-layout composable. Some functions produce no independent node and have no observable runtime identity.

UI Automator lookup uses the tag verbatim:

```kotlin
device.findObject(By.res("ux.checkout.submit"))
```

The package/name overload assumes Android resource IDs and is inappropriate for these raw tags. Keep `tag-map.json` with Figma node ID, tag, composable and source path for the exact instrumented build. It is a curated attribution map, not an automatically discovered source call tree.

## Test adapter for insets and unmerged Semantics

Use the project's matching `androidx.compose.ui:ui-test-junit4`/test manifest configuration and instrumentation runner. Adapt an existing Android test; preserve its launch/state fixture. After waiting for the required screen to settle:

```kotlin
// In a Compose Android test, after the launched activity is ready:
val root = composeRule.onRoot(useUnmergedTree = true).fetchSemanticsNode()
// Traverse root.children; export stable IDs, parent IDs, TestTag, Text,
// Disabled/Selected/ToggleableState where exposed, and boundsInWindow.
// Unexposed properties must stay absent, rather than default false.
```

Use `SemanticsProperties` and `SemanticsActions` supported by that project's version. `printToLog` is useful for debugging; a CI adapter should serialize JSON matching the runtime contract. A click action and enabled state are different properties. Never infer every node is enabled simply because Disabled is absent without checking its semantics role/action.

Read insets on the UI thread from the active decor view, after insets are dispatched:

```kotlin
val wi = activity.window.decorView.rootWindowInsets
    ?: error("Insets not dispatched")
val bars = wi.getInsets(
    android.view.WindowInsets.Type.statusBars() or
        android.view.WindowInsets.Type.navigationBars()
)
// Export bars.left/top/right/bottom in physical pixels.
```

This snippet requires API 30+; use the project's WindowInsetsCompat dependency on older devices. `getInsets` reflects current visibility. Do not use `getInsetsIgnoringVisibility` when cropping bars from the visible screenshot. Do not subtract IME, mandatory gesture/tappable regions or the full app padding as system bars. Edge-to-edge content underneath visible bars is intentionally excluded by this crop; retain the original image for review. Display cutout/safe drawing comparisons require their own explicit policy.

Capture screenshot and probe data in the same settled test step; include state/build/capture IDs, device metadata and image hash. Confirm bounds coordinate origin: this package expects absolute display pixels before subtracting insets. `boundsInWindow` needs the actual window-to-display offset. For a single fullscreen window, assert its display, origin and dimensions match the screenshot; otherwise convert using the measured offset or declare the case unsupported. Dialogs, multiwindow, overlays and secondary displays need project-specific adapters. Do not blindly crop the same bars twice if a test API returns app-content-only pixels.

Create the final runtime JSON from the adapter; label it `hierarchy_kind: unmerged_semantics`. The provided `collect` CLI instead obtains `accessibility` via adb and parses Android WMS insets. If its strict parser rejects a vendor dump, keep diagnostics and use the probe; do not fall back to guessed 24/48 dp.

## Safe temporary patch lifecycle

The agent constructs a project-specific literal patch plan, after reading source. Example shape:

```json
{"patches":[{"path":"app/src/main/java/example/Screen.kt","before_sha256":"SHA256_OF_CURRENT_BYTES","search":"one exact source fragment","replace":"replacement fragment with imports/modifier edits"}]}
```

One patch per file; combine all edits to that file into one unique literal replacement. A new file uses `before_sha256: null`, `search: ""`, `replace: "complete file contents"`. The source may already be dirty; its current bytes are the preimage to restore.

1. Save the plan separately from source and choose a fresh private session directory.
2. Run `instrument --project-root PROJECT --plan patches.json --session SESSION`.
3. Build/run/collect in a `try` block. Tag map refers to this instrumented artifact.
4. Run `cleanup --session SESSION` in `finally`; inspect its JSON and exit code.

The scripts check all preimages, reject escaping/symlink paths, journal private backups and track applied postimages. Cleanup restores/deletes only files whose current bytes match the recorded postimage. A changed file is preserved as a conflict. Sessions/backups remain for review; protect them as source artifacts. No reset/clean/checkout is used. There is no lock against concurrent external editors; avoid concurrent edits to owned files. Resolve conflicts manually with the saved preimage, current source and intended instrumentation diff.

Removing source does not remove probes from the installed test APK. Rebuild/reinstall a clean artifact if the device must return to its previous state. Runtime data needed for review should remain outside the cleanup session.
