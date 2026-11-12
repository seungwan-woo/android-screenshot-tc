# Emulator screenshot CI design

Capture the entire display of a real Android emulator, compare it to a checked-in PNG, fail CI on a visual regression, and retain reference/actual/difference images. The user requested a sample because no app exists, then requested tests followed by a PR.

Use a small native Android View APK built with JDK 21, SDK 35 and Build Tools 35.0.0. A button changes `State: READY` to `State: UPDATED`. ADB controls the application and captures PNGs; Pillow compares all RGB pixels. This exercises an actual device display rather than Compose Preview or host rendering.

The alternative was a preview/Robolectric screenshot library; that does not exercise the requested emulator display. An AndroidX instrumentation project would also work, but is unnecessary for this dependency-light environment sample.

Use API 35 default x86_64, emulator build 16740729, image revision 2, 1080×1920, 420 dpi, SwiftShader, fixed status-bar demo state and disabled animations. Guard the image revision so dependency updates require an explicit reference review. Store a sample reference PNG; verify compatibility on the CI runner before opening the PR. PR tests never overwrite a baseline. Manual record mode uploads a candidate for review.

Test exact matching, real pixel changes, ratio/tolerance boundaries, size mismatch and invalid files. The emulator smoke test verifies the visible READY state, two equal captures, a real button interaction and the expected comparison failure for UPDATED. GitHub Actions runs the same sample and uploads failure evidence. Do not claim a remote workflow passed without reading its result.

The cloud environment has no /dev/kvm. Retain SDK/startup helpers outside the checkout; use KVM on GitHub-hosted Ubuntu. Save cloud installation/start instructions as a draft and do not publish the environment. Use the existing isolated checkout; do not create a worktree. The empty repository needs a minimal base commit before a PR can exist.
