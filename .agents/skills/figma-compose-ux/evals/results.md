# Authoring validation — 2026-11-14

## Agent application trials

Five independent agents reviewed `scenario.txt` before this skill was written. All preserved uncertainty and local work and declined the unsupported 99% claim. The observed problem was five different JSON structures, not dishonest UX approval.

Five fresh agents then read the skill and used isolated, explicitly synthetic demo-derived fixtures. They were allowed to execute scripts in scratch directories, while control agents answered the text-only scenario. This is an authoring usability exercise, not a controlled benchmark comparing model quality.

| Guided run | Canonical output | Overall | Check counts | assess exit |
|---|---|---|---|---|
| 1 | schema_version 1, findings/provenance/coverage | inconclusive / fixture_only | 7 inconclusive | 3 |
| 2 | schema_version 1, findings/provenance/coverage | inconclusive / fixture_only | 7 inconclusive | 3 |
| 3 | schema_version 1, findings/provenance/coverage | inconclusive / fixture_only | 6 inconclusive | 3 |
| 4 | schema_version 1, findings/provenance/coverage | inconclusive / fixture_only | 7 inconclusive | 3 |
| 5 | schema_version 1, findings/provenance/coverage | inconclusive / fixture_only | 6 inconclusive | 3 |

Each independently confirmed content 360×592 dp, Save [24,124,120,164] dp, but stale build attribution and absent mapping/flow/hierarchy evidence prevented product approval. Counts differ because agents included six or seven explicit requirements. All used the common result contract. Three runs exercised synthetic patch cleanup, restoring dirty preimages and preserving later edits as conflicts; two correctly recorded that no instrumentation ran.

Feedback led to preserving design preparation issues in the final report, carrying tag-map provenance and explicit binding status, and clarifying complete device metadata requirements. Strict metadata remains intentional: density-only arithmetic is possible, but missing live locale/font/device facts must not be invented to complete a capture record. Demo rectangles test geometry and pixels; they are not real application UI or typography validation.

## Code review and automated verification

Independent review found evidence-output aliases could overwrite input artifacts, and a producer's bare pixel `passed` flag was trusted. Regression tests reproduced those defects before fixes. Outputs now guard path/hardlink aliases; pixel evidence requires internally consistent metrics and preserved artifact hashes, and CLI assessment reopens artifacts to recompute differences.

Reproduce automated checks from repository root:

```bash
python3 -m unittest discover -s .agents/skills/figma-compose-ux/tests -v
python3 .agents/skills/figma-compose-ux/scripts/ux.py demo --output-dir /tmp/ux-skill-eval-unique
python3 -m unittest discover -s tests -v
```

Tests cover design/schema validation, source mapping containment, XML and WMS parsing, geometry/insets normalization, mocked bounded adb/APK binding, safe patch sessions and conflicts, image comparison/provenance, requirement checks, CLI exit codes, evidence preservation and execution after copying scripts outside the repository. CI runs the module suite and a separate synthetic pipeline. No live Figma call, actual Compose compilation/probe, or new emulator UX run was performed for this skill package.

Final local verification: **131 skill tests and 17 existing repository tests passed**. The distributable ZIP was extracted into a fresh temporary directory; all 131 tests and the synthetic demo ran there successfully. No repository checkout was needed for that package run.
