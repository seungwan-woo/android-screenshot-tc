#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SDK=${ANDROID_HOME:?Source ../env.sh or set ANDROID_HOME}
TOOLS="$SDK/build-tools/35.0.0"
ANDROID_JAR="$SDK/platforms/android-35/android.jar"
OUT="$ROOT/build"
mkdir -p "$OUT/classes" "$OUT/dex"
"$TOOLS/aapt2" link -I "$ANDROID_JAR" --manifest "$ROOT/AndroidManifest.xml" -o "$OUT/resources.ap_"
javac --release 8 -classpath "$ANDROID_JAR" -d "$OUT/classes" "$ROOT/src/com/example/screenshotci/MainActivity.java"
mapfile -d '' classfiles < <(find "$OUT/classes" -name '*.class' -print0)
"$TOOLS/d8" --min-api 23 --lib "$ANDROID_JAR" --output "$OUT/dex" "${classfiles[@]}"
cp "$OUT/resources.ap_" "$OUT/unsigned.apk"
python3 - "$OUT" <<'PY'
from pathlib import Path
import sys,zipfile
out=Path(sys.argv[1])
with zipfile.ZipFile(out/'unsigned.apk','a',zipfile.ZIP_DEFLATED) as apk:
    for dex in sorted((out/'dex').glob('*.dex')): apk.write(dex,dex.name)
PY
"$TOOLS/zipalign" -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
KEYSTORE_DIR=${ANDROID_USER_HOME:-$HOME/.android}
mkdir -p "$KEYSTORE_DIR"
KEYSTORE="$KEYSTORE_DIR/screenshot-ci-debug.keystore"
if ! test -f "$KEYSTORE"; then
  (umask 077; keytool -genkeypair -keystore "$KEYSTORE" -alias androiddebugkey -storepass android -keypass android -dname 'CN=Android Debug,O=Android,C=US' -keyalg RSA -keysize 2048 -validity 10000)
fi
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out "$OUT/sample.apk" "$OUT/aligned.apk"
"$TOOLS/apksigner" verify --verbose "$OUT/sample.apk"
printf 'Built %s\n' "$OUT/sample.apk"
