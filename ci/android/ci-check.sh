#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
args=(--mode "${SCREENSHOT_MODE:-verify}" --output "${SCREENSHOT_OUT:-$ROOT/artifacts/ci}")
args+=(--config "${SCREENSHOT_CONFIG:-ci/android/configs/sample.json}")
if [[ -n "${REFERENCE_PNG:-}" ]]; then
  args+=(--reference-override "$REFERENCE_PNG")
fi
exec python3 "$ROOT/run-screenshot.py" "${args[@]}"
