# Design, implementation and UX review

## Capability and evidence record

Discover tools from the current MCP tool registry; server prefixes and schemas vary. The Figma MCP server commonly exposes design context and screenshot capabilities (`get_design_context`, `get_screenshot`), but invoke only capabilities actually listed. Also look for component/variable metadata and a Code Connect mapping capability. Some versions use a code/workflow query tool instead. Follow the installed server's instructions and exact schema. Save the response or a precise receipt including tool name, arguments, time, file key, node ID, revision/version if provided, and local artifact paths. Do not label a local JSON fixture as an MCP response.

If revision is not provided, record an explicit export snapshot identifier and receipts; do not fabricate a Figma revision. A connector failure can leave independent local work runnable. Report that live extraction is blocked. Publishing Code Connect mappings or writing Figma files is a separate external mutation; this workflow reads existing design information.

## Client connection prerequisites

Skill discovery and MCP authentication are separate. Install the same skill folder in the client's supported path (see [installation](../README.md)), connect the official remote MCP endpoint `https://mcp.figma.com/mcp`, complete the client's Figma OAuth flow, then verify the current session exposes its tools. A local client registration does not automatically configure a separate hosted chat. Client skill-format support alone does not establish successful execution of this workflow.

For a local Codex CLI, register with `codex mcp add figma --url https://mcp.figma.com/mcp` and authenticate with `codex mcp login figma`. Follow the current Figma/client documentation for Gemini CLI or Claude Code. Preserve inherited network/proxy settings. If configuration is read-only, use a client with a writable configuration; if the proxy rejects the destination, report the network block and use an environment with authorized Figma access. Do not label an unsuccessful OAuth discovery request as a connected MCP server.

Before live validation, obtain the selected file/component URL and verify design access plus the project's actual Compose mapping. Creating or publishing a new Code Connect mapping is an explicit task using the appropriate Code Connect integration and its credentials/permissions. Reading existing mappings via MCP and publishing mappings are distinct operations. Credentials belong in the client's OAuth/secret storage, outside source control and review artifacts.

Official references, consulted 2026-11-14:

- [Figma MCP server guide](https://github.com/figma/mcp-server-guide)
- [Code Connect integrations, including Jetpack Compose](https://github.com/figma/code-connect)
- [Code Connect Compose documentation](https://www.figma.com/code-connect-docs/compose)
- [Gemini CLI Agent Skills](https://geminicli.com/docs/cli/skills/)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Android screenshot testing](https://developer.android.com/training/testing/ui-tests/screenshot)
- [Compose interoperability with UI Automator](https://developer.android.com/develop/ui/compose/testing/interoperability#uiautomator)
- [Compose Semantics](https://developer.android.com/develop/ui/compose/accessibility/semantics)
- [Layout Inspector](https://developer.android.com/studio/debug/layout-inspector)

## Translate design data into a contract

MCP responses are not the CLI contract. The agent converts them, preserving the raw evidence and explaining unit assumptions. Record whether a Figma frame includes system bars. Export a content-only reference or explicitly select its content frame; do not compare a full-device design export to cropped app content. Use `figma_units_per_dp` plus export `reference_scale`. `prepare` hashes the selected reference image.

Create a state/intent matrix before generation:

| Intent | Design/source input | Runtime evidence |
|---|---|---|
| Content position/size | Frame geometry, constraints, spacing tokens | Content-dp bounds, screenshot |
| Typography | Family, asset/version, size/weight, line height, letter spacing | Matched font environment; wrapping/truncation and screenshot |
| Component reuse | Compose Code Connect mapping, actual call site | Source diff/build receipt, tag identity |
| Enabled/selected state | Explicit variants, product rules | Observed properties in the required state |
| Grouping/reading order | Explicit accessibility or Semantics expectations | The same selected hierarchy kind |
| Submission/navigation | Before/action/after and expected result | Action trace, both captures, observable postcondition |
| Error/loading/empty | Specified data/network fixture | Each required scenario and recovery action |

A design layer parent is not automatically a Semantics parent. Declare hierarchy requirements only when their meaning is comparable. Use `review` or another unsupported kind for qualitative requirements that need a separate agent/human review; they stay inconclusive in the deterministic evaluator. Do not silently drop them to obtain a pass.

If the source design does not specify behavior, record the assumption and seek clarification where it changes product behavior. Use independent tasks to proceed while awaiting that information. A screenshot cannot establish keyboard order, reading order, error recovery or task completion.

## Generate Compose in the actual project

1. Inspect build files/BOM, route/state conventions, theme/tokens, fonts, component APIs, existing tests and required project checks.
2. Resolve Code Connect mapping framework, component and project-relative Kotlin path. React/SwiftUI mappings may inform design understanding but do not prove Compose reuse. Name similarity is insufficient.
3. Inspect mapped component implementation and modifier forwarding. Generate actual call sites using it, map variants/properties, and use existing tokens/assets. Keep meaningful app behavior; a static imitation is insufficient for declared interaction intent.
4. Compile and run appropriate project tests. Save exact commands, exit codes, build artifact path/hash, commit plus dirty diff, and generated source paths. `code_connect` checks only mapping consistency; separately review real usage and source/build receipts.
5. Create test-only instrumentation through the patch session. Avoid wrappers or semantics changes that alter the rendered layout/interaction just to make tests pass. Rebuild the instrumented APK, update tag map build ID, install and bind its hash at collection.

This skill is an agent workflow plus evidence tools, not a universal Kotlin generator. CLI scripts do not contact Figma or synthesize application code.

## Reproducible capture matrix

Pin device image/revision, renderer, screen dimensions/density, API, locale, theme, timezone/data/clock, animation settings and font assets. Record `font_scale`. Compare like environments to like design variants. For alternate fonts or accessibility font scales, use a separate variant/requirements: expected wrapping, no clipped critical content, reachable actions, stable reading order. Increasing pixel tolerance is not a substitute for that scenario. Renderers/fonts can differ from Figma, so choose and justify tolerances before inspecting the result. Keep raw diffs.

Drive scenarios with the project's test runner or UI Automator using exported tags. Record the actual command/action, before/after capture IDs and its output. Wait for a meaningful stable state (not an arbitrary long sleep). The read-only collector does not launch, install, reset, freeze or drive the app. Its screenshot, XML and WMS queries are sequential; capture a stable screen and corroborate synchronization with test logs. It does not prove atomicity or network determinism.

`metadata.json` must describe the selected device accurately. Read-only queries such as `adb -s SERIAL shell wm density`, `settings get system font_scale`, `getprop ro.build.fingerprint`, and `getprop ro.build.version.sdk` can help; effective override density wins, density is dpi/160. Locale/theme/rotation also need actual device/project checks. Preserve the command receipts rather than guessing. Supply `apk_path` to compare local APK bytes with the installed base APK. Split installs are explicitly unsupported by this collector.

## Review and handoff

Machine checks give measurements and requirement verdicts. Also inspect design, actual and highlighted diff; assess visual hierarchy, labels, affordances, focus/reading order, touch reachability and complete user journeys. Label qualitative conclusions and their evidence separately. Investigate large diffs before changing tolerances or baselines.

A previous runtime screenshot is a regression reference, not a Figma reference. Use separate comparisons and labels. This package's JSON records are evidence contracts, not cryptographic attestation of an untrusted test producer. Keep the original receipts and artifact hashes for review.

Run cleanup even when build/capture/assessment fails. Preserve conflicting local edits. Deliver missing evidence and next steps alongside what was observed. Never claim a fixture demo exercised an emulator, a Figma MCP connection or generated Compose compilation.
