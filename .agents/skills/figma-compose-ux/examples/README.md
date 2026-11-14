# Runnable synthetic example

Run `python3 ../scripts/ux.py demo --output-dir /tmp/ux-demo-unique` from this directory. Choose an empty, fresh directory. It generates:

- Design/reference and Code Connect inputs; synthetic Kotlin source receipt.
- An empty-state image with measured simulated bars, density=3, and explicit geometry.
- Empty, valid and success runtime records; tag map and action trace.
- Cropped/aligned image, registration, pixel comparison and six requirement findings.
- Canonical JSON and readable Markdown.

All inputs and observations are fixtures. The state records are synthetic, not screenshots of three actual app states. The Kotlin file is a source-hashing fixture, not a compiled app. Six deterministic checks pass; the overall assessment stays **inconclusive / fixture_only**. Demo exit 0 means the tools behave as expected.

Modify a node bound to create a layout failure, delete the trace to leave the flow inconclusive, use a stale tag map to lose identity, or change `font_scale` to demonstrate an incomparable environment. Existing screenshot regression CI remains a separate runtime comparison.
