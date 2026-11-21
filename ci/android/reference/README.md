# Screenshot Lab baselines

- `sample.png` captures the Compose sample in light theme.
- `sample-dark.png` captures the Compose sample in dark theme.

They are full 1080×1920 display captures from the GitHub Actions API 35 default x86_64 revision 2 emulator, at 420 dpi, with SwiftShader and the status bar in demo mode. The [recording run](https://github.com/seungwan-woo/android-screenshot-tc/actions/runs/44887490480) captured each theme with its own JSON configuration and verified the UI Automator theme label and button transition. Review together with the corresponding smoke artifacts before updating a baseline. The One UI Design Kit informed the sample's rounded shapes, spacing and colors. These images capture the Android sample directly.
