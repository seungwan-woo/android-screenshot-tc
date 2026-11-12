# Emulator Screenshot CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test full emulator screenshots with a sample APK and deliver a tested PR.

**Architecture:** Keep the reusable cloud SDK/AVD in `/workspace/shared/android-ci`. Put the portable sample, capture/comparison CLIs and real-device smoke test in `ci/android/`, with GitHub Actions owning CI emulator lifecycle.

**Tech Stack:** Java 21, Android SDK 35, Build Tools 35.0.0, Python 3.12, Pillow 12.0.0, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-12-emulator-screenshot-ci-design.md`

## Global Constraints

Use API 35 default x86_64, emulator build 16740729, image revision 2, 1080×1920, 420 dpi, SwiftShader. Do not overwrite a reference during verification. Do not publish the cloud environment. Use the existing checkout. The user has requested the implementation and PR; continue inline without a separate execution-choice prompt.

## Review Focus

- Missing/corrupt baseline must fail closed: comparator CLI tests.
- Different PNG dimensions must fail: comparator CLI test.
- Percentage and channel tolerance boundaries must be exact: comparator CLI tests.
- Updated system image must require review: revision guard tests.
- First PR must have a baseline and genuine remote test evidence: inspect CI run before PR creation.

### Task 1: Portable screenshot implementation

Files: `ci/android/{capture.py,compare.py,smoke.py,ci-check.sh,check-system-image.py}`, sample APK source/build script, `requirements.txt`, `.gitignore`.

- [ ] Write CLI tests in `tests/test_compare.py` and `tests/test_system_image.py`; observe failure while scripts are absent.
- [ ] Port the validated cloud helpers, align all smoke commands to ANDROID_SERIAL, and add the revision guard.
- [ ] Run `python3 -m unittest discover -s tests -v`; expect all cases to execute and pass.

### Task 2: Emulator validation and CI

Files: `.github/workflows/screenshot.yml`, sample reference under `ci/android/reference/`, `README.md`.

- [ ] Run `python3 ci/android/smoke.py` against a booted emulator; expect APK/UI checks, exact match exit 0 and changed-screen exit 1.
- [ ] Inspect the sample reference, record it explicitly, then run `SCREENSHOT_MODE=verify bash ci/android/ci-check.sh`; expect exit 0.
- [ ] Configure branch push/PR/manual triggers, CPU tests, image revision guard and always-uploaded artifacts.
- [ ] Push the implementation branch and inspect its actual CI result; diagnose and fix any failing step without weakening comparison assertions.

### Task 3: Review, reusable configuration and PR

- [ ] Address the independent review findings: baseline bootstrap, image revision guard and consistent serial selection.
- [ ] Save the tested install script and startup instructions in the environment draft; leave repository selection unchanged.
- [ ] Commit the final implementation and create a PR against main after tests pass. Report the PR and evidence, with any remaining platform limitations.
