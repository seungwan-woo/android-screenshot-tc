#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
MODE=${SCREENSHOT_MODE:-verify}
OUT=${SCREENSHOT_OUT:-$ROOT/artifacts/ci}
REFERENCE=${REFERENCE_PNG:-$ROOT/reference/sample.png}
mkdir -p "$OUT"
if [[ "$MODE" != verify && "$MODE" != record ]]; then
  echo 'SCREENSHOT_MODE must be verify or record' >&2
  exit 2
fi
bash "$ROOT/sample/build.sh"
adb -s "${ANDROID_SERIAL:-emulator-5554}" shell am force-stop com.example.screenshotci
python3 "$ROOT/capture.py" --apk "$ROOT/sample/build/sample.apk" --component com.example.screenshotci/.MainActivity --output "$OUT/actual.png"
if [[ "$MODE" == record ]]; then
  echo "Candidate reference: $OUT/actual.png. Review before replacing $REFERENCE."
else
  python3 "$ROOT/compare.py" "$REFERENCE" "$OUT/actual.png" --artifacts "$OUT/comparison"
fi
