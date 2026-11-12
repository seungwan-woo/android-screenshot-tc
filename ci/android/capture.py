#!/usr/bin/env python3
"""Capture a stable full emulator display, optionally installing and launching an APK."""
import argparse
import os
from pathlib import Path
import subprocess
import time
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('--serial', default=os.environ.get('ANDROID_SERIAL', 'emulator-5554'))
p.add_argument('--apk', type=Path)
p.add_argument('--component', help='Example: com.example.app/.MainActivity')
p.add_argument('--action', default='android.settings.SETTINGS')
p.add_argument('--no-launch', action='store_true', help='Capture current state without starting an activity')
p.add_argument('--output', type=Path, required=True)
p.add_argument('--settle-seconds', type=float, default=3)
args = p.parse_args()

def adb(*command):
    return subprocess.run(['adb', '-s', args.serial, *command], capture_output=True,
                          check=True, timeout=120).stdout

if adb('shell', 'getprop', 'sys.boot_completed').strip() != b'1':
    raise RuntimeError('Android is not booted')
adb('shell', 'wm', 'size', '1080x1920')
adb('shell', 'wm', 'density', '420')
for name in ['window_animation_scale', 'transition_animation_scale', 'animator_duration_scale']:
    adb('shell', 'settings', 'put', 'global', name, '0')
adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
adb('shell', 'settings', 'put', 'system', 'accelerometer_rotation', '0')
adb('shell', 'settings', 'put', 'system', 'user_rotation', '0')
adb('shell', 'settings', 'put', 'secure', 'show_ime_with_hard_keyboard', '0')
adb('shell', 'settings', 'put', 'global', 'sysui_demo_allowed', '1')
for extras in [
    ['-e', 'command', 'enter'],
    ['-e', 'command', 'clock', '-e', 'hhmm', '1000'],
    ['-e', 'command', 'battery', '-e', 'level', '100', '-e', 'plugged', 'false'],
    ['-e', 'command', 'network', '-e', 'wifi', 'show', '-e', 'level', '4',
     '-e', 'fully', 'true', '-e', 'mobile', 'hide'],
    ['-e', 'command', 'notifications', '-e', 'visible', 'false'],
]:
    adb('shell', 'am', 'broadcast', '-a', 'com.android.systemui.demo', *extras)
adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
adb('shell', 'wm', 'dismiss-keyguard')
if args.apk:
    if not args.component:
        p.error('--apk requires --component to select the application screen')
    adb('install', '-r', '-t', str(args.apk.resolve()))
result = b''
if args.no_launch:
    pass
elif args.component:
    result = adb('shell', 'am', 'start', '-W', '-n', args.component)
else:
    result = adb('shell', 'am', 'start', '-W', '-a', args.action)
if b'Error:' in result or b'Exception' in result:
    raise RuntimeError(result.decode(errors='replace'))
time.sleep(args.settle_seconds)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(adb('exec-out', 'screencap', '-p'))
with Image.open(args.output) as image:
    image.load()
    if image.size != (1080, 1920):
        raise RuntimeError(f'Unexpected screenshot dimensions: {image.size}')
print(f'Captured {args.output}: 1080x1920')
