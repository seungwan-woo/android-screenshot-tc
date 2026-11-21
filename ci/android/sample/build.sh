#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SDK=${ANDROID_HOME:-${ANDROID_SDK_ROOT:?Set ANDROID_HOME to the Android SDK}}
bash "$ROOT/gradlew" -p "$ROOT" --no-daemon :app:assembleDebug
mkdir -p "$ROOT/build"
cp "$ROOT/app/build/outputs/apk/debug/app-debug.apk" "$ROOT/build/sample.apk"
"$SDK/build-tools/37.0.0/apksigner" verify --verbose "$ROOT/build/sample.apk"
printf 'Built %s\n' "$ROOT/build/sample.apk"
