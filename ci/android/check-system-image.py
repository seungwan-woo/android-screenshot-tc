#!/usr/bin/env python3
"""Fail before capture when an SDK image update changes the baseline environment."""
import os
from pathlib import Path
import sys

sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
if not sdk:
    sys.exit('Set ANDROID_HOME to the Android SDK directory.')
properties = Path(sdk) / 'system-images/android-35/default/x86_64/source.properties'
try:
    values = dict(line.split('=', 1) for line in properties.read_text().splitlines()
                  if '=' in line and not line.lstrip().startswith('#'))
    revision = tuple(int(part) for part in values.get('Pkg.Revision', '').strip().split('.'))
except (OSError, ValueError):
    sys.exit('Expected API 35 default x86_64 image revision 2; install the pinned image before reviewing a baseline.')
revision = revision + (0,) * max(0, 3 - len(revision))
if revision != (2, 0, 0):
    sys.exit(f'Expected API 35 default x86_64 image revision 2, got {values.get("Pkg.Revision")}; review the environment and baseline explicitly before upgrading.')
print('Verified API 35 default x86_64 system image revision 2.')
