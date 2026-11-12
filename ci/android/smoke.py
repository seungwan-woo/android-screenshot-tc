#!/usr/bin/env python3
"""Exercise the APK, two real screen captures, and a real visual regression."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
OUT = Path(os.environ.get('SCREENSHOT_VALIDATION_OUT', ROOT / 'artifacts' / ('validation-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))))
OUT.mkdir(parents=True)
PYTHON = sys.executable
COMPONENT = 'com.example.screenshotci/.MainActivity'
SERIAL = os.environ.get('ANDROID_SERIAL', 'emulator-5554')

def run(*command):
    result = subprocess.run(command, text=True, capture_output=True, timeout=300)
    if result.returncode:
        print(result.stdout, file=sys.stderr, flush=True)
        print(result.stderr, file=sys.stderr, flush=True)
        result.check_returncode()
    return result

def adb(*command):
    return run('adb', '-s', SERIAL, *command).stdout

print(run('bash', str(ROOT / 'sample/build.sh')).stdout, flush=True)
adb('shell', 'am', 'force-stop', 'com.example.screenshotci')
print(run(PYTHON, str(ROOT / 'capture.py'), '--serial', SERIAL, '--apk', str(ROOT / 'sample/build/sample.apk'),
          '--component', COMPONENT, '--output', str(OUT / 'reference.png'), '--settle-seconds', '5').stdout, flush=True)
print(run(PYTHON, str(ROOT / 'capture.py'), '--serial', SERIAL, '--no-launch',
          '--output', str(OUT / 'actual.png')).stdout, flush=True)
print(run(PYTHON, str(ROOT / 'compare.py'), str(OUT / 'reference.png'), str(OUT / 'actual.png'),
          '--artifacts', str(OUT / 'same-screen')).stdout, flush=True)
adb('shell', 'uiautomator', 'dump', '--compressed', '/sdcard/screenshot-ci-window.xml')
hierarchy = adb('shell', 'cat', '/sdcard/screenshot-ci-window.xml')
(OUT / 'ready-window.xml').write_text(hierarchy)
tree = ET.fromstring(hierarchy)
if not any(n.attrib.get('text') == 'State: READY' for n in tree.iter('node')):
    raise RuntimeError('Expected sample screen not visible')
button = next(n for n in tree.iter('node') if n.attrib.get('content-desc') == 'update_state')
x1, y1, x2, y2 = map(int, re.findall(r'\d+', button.attrib['bounds']))
adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))
time.sleep(2)
adb('shell', 'uiautomator', 'dump', '--compressed', '/sdcard/screenshot-ci-window.xml')
changed_hierarchy = adb('shell', 'cat', '/sdcard/screenshot-ci-window.xml')
(OUT / 'updated-window.xml').write_text(changed_hierarchy)
if not any(n.attrib.get('text') == 'State: UPDATED' for n in ET.fromstring(changed_hierarchy).iter('node')):
    raise RuntimeError('Button did not update app state')
print(run(PYTHON, str(ROOT / 'capture.py'), '--serial', SERIAL, '--no-launch',
          '--output', str(OUT / 'changed.png')).stdout, flush=True)
negative = subprocess.run([PYTHON, str(ROOT / 'compare.py'), str(OUT / 'reference.png'),
                          str(OUT / 'changed.png'), '--artifacts', str(OUT / 'changed-screen')],
                         text=True, capture_output=True, timeout=60)
if negative.returncode != 1:
    raise RuntimeError(f'Expected visual regression exit=1; got {negative.returncode}: {negative.stdout} {negative.stderr}')
report = {'passed': True, 'checks': {'apk_built_and_signature_verified': True,
          'apk_installed_and_ready_state_visible': True, 'identical_screen_compare_exit': 0,
          'button_updated_visible_state': True, 'changed_screen_compare_exit': 1},
          'artifact_directory': str(OUT), 'sample_component': COMPONENT,
          'android_api': adb('shell', 'getprop', 'ro.build.version.sdk').strip(),
          'system_fingerprint': adb('shell', 'getprop', 'ro.build.fingerprint').strip()}
(OUT / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
(ROOT / 'artifacts').mkdir(exist_ok=True)
(ROOT / 'artifacts/latest-validation.txt').write_text(str(OUT) + '\n')
print(json.dumps(report, indent=2), flush=True)
