---
name: figma-compose-ux
description: Use when implementing or reviewing Android Jetpack Compose screens against Figma, Code Connect, UX requirements, emulator screenshots, UI Automator, or Compose Semantics evidence.
---

# Figma → Compose → UX evidence

Evaluate **declared UX intent** through attributable design, source and runtime evidence. Pixel similarity is one check. A matching regression golden does not establish Figma fidelity or successful navigation.

## Start

Resolve this directory as `SKILL_DIR`; run `python3 "$SKILL_DIR/scripts/ux.py" --help`. Install `requirements.txt` in the project's Python environment. The package is portable; no repository-specific paths are required.

Read [workflow.md](references/workflow.md) for design/code generation, [contracts.md](references/contracts.md) for JSON inputs/outputs and CLI commands, and [instrumentation.md](references/instrumentation.md) before changing source or collecting runtime data.

## Workflow

1. **Discover.** Inspect project instructions, Compose/toolchain versions, components, build/test commands, dirty files and available MCP tools. Record available capabilities. If Figma is unavailable, use explicitly identified exports or fixtures and record the missing live connection.
2. **Specify intent.** Read the selected Figma frame, screenshot, variants, variables and Code Connect mapping. Preserve file/node/revision and tool receipts. Define measurable requirements for layout, hierarchy, text, accessibility and states/transitions. Separate explicit requirements from assumptions; clarify consequential missing intent.
3. **Implement.** Resolve Compose mappings to real Kotlin source. Reuse project components and tokens; inspect actual call sites. Generate/edit Compose using project conventions, then run its build/tests. Keep a source/build receipt. An incompatible or absent mapping stays unresolved.
4. **Instrument temporarily.** Inspect modifier forwarding; create an exact, hashed patch plan. Use `instrument` with a fresh session outside source. Expose curated tags via `testTagsAsResourceId`; use an Android test adapter for unmerged Semantics/insets where necessary. UI Automator exposes accessibility, not every composable. Preserve the design↔tag↔source map for this build.
5. **Observe.** Stabilize each required scenario. Collect original screenshot, measured insets, hierarchy, device/font configuration, APK binding and interaction evidence. Capture before/action/after for transitions. Keep every capture tied to its state and build.
6. **Assess.** Run prepare → normalize/collect → align → compare → assess → report. Crop measured bars before density conversion; use comparable design variants and explicit tolerances. Inspect images and UX behavior separately from machine checks. Unsupported or missing evidence is `inconclusive`.
7. **Restore.** Run cleanup in `finally`, including failures. Preserve conflicts and report exact remaining files. Cleaning source does not remove probes from an installed APK; rebuild/reinstall when needed.

## Deliver

Return canonical `assessment.json`, readable report, design/actual/diff images, source/build and interaction receipts, plus cleanup status. Include requirement-level `pass/fail/inconclusive/not_applicable`, evidence and limitations. Coverage is evaluated checks, never a UX quality score. Distinguish fixture tooling validation from live app validation. List missing scenarios and qualitative UX observations separately.

Try `python3 "$SKILL_DIR/scripts/ux.py" demo --output-dir /tmp/ux-demo-unique` for a fully synthetic contract example.
