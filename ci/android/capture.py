#!/usr/bin/env python3
"""Capture a stable full emulator display, optionally installing and launching an APK."""
import argparse
import io
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
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
p.add_argument('--size', default='1080x1920')
p.add_argument('--density', type=int, default=420)
p.add_argument('--theme', choices=('system', 'light', 'dark'), default='system')
p.add_argument('--expected-package', help='Verify foreground ownership when capturing the current state')
p.add_argument('--focus-timeout', type=float, default=25)
p.add_argument('--diagnostic', type=Path, help='Write the observed focus when the screen is blocked')
args = p.parse_args()
if args.apk and not args.component:
    p.error('--apk requires --component to select the application screen')
if args.no_launch and (args.apk or args.component or args.theme != 'system'):
    p.error('--no-launch cannot install or launch an application or change its theme')
if not re.fullmatch(r'[1-9]\d{0,3}x[1-9]\d{0,3}', args.size) or not 1 <= args.density <= 1000:
    p.error('size must be WIDTHxHEIGHT and density in [1,1000]')
if any(not math.isfinite(value) or value < 0 for value in (args.focus_timeout, args.settle_seconds)):
    p.error('capture timeouts must be finite and nonnegative')
if args.component and not re.fullmatch(r'[\w.]+/[\w.$]+', args.component, re.ASCII):
    p.error('component must be PACKAGE/ACTIVITY')
target = args.expected_package or (args.component.split('/', 1)[0] if args.component else None)
if target and not re.fullmatch(r'[\w.]+', target, re.ASCII):
    p.error('expected package has an invalid format')

def adb(*command):
    return subprocess.run(['adb', '-s', args.serial, *command], capture_output=True,
                          check=True, timeout=120).stdout

if adb('shell', 'getprop', 'sys.boot_completed').strip() != b'1':
    raise RuntimeError('Android is not booted')
if not args.no_launch:
    sizes = re.findall(r'(?:Physical|Override) size:\s*(\d+x\d+)', adb('shell', 'wm', 'size').decode())
    densities = re.findall(r'(?:Physical|Override) density:\s*(\d+)', adb('shell', 'wm', 'density').decode())
    if not sizes or not densities:
        raise RuntimeError('Could not read the current Android display geometry')
    if sizes[-1] != args.size:
        adb('shell', 'wm', 'size', args.size)
    if densities[-1] != str(args.density):
        adb('shell', 'wm', 'density', str(args.density))
    for name in ['window_animation_scale', 'transition_animation_scale', 'animator_duration_scale']:
        adb('shell', 'settings', 'put', 'global', name, '0')
    adb('shell', 'settings', 'put', 'system', 'font_scale', '1.0')
    if args.theme != 'system':
        adb('shell', 'cmd', 'uimode', 'night', 'yes' if args.theme == 'dark' else 'no')
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
        adb('install', '-r', '-t', str(args.apk.resolve()))
    if args.component:
        result = adb('shell', 'am', 'start', '-W', '-n', args.component)
    else:
        result = adb('shell', 'am', 'start', '-W', '-a', args.action)
    if b'Error:' in result or b'Exception' in result:
        raise RuntimeError(result.decode(errors='replace'))
time.sleep(args.settle_seconds)


def focus():
    dump = adb('shell', 'dumpsys', 'window', 'displays').decode(errors='replace')
    display = re.split(r'(?m)^\s*Display: mDisplayId=\d+\b', dump)
    if len(display) > 1:
        header = re.search(r'(?m)^\s*Display: mDisplayId=(\d+)\b', dump)
        if not header or header[1] != '0':
            return None, 'Default display 0 is absent or not first'
        dump = display[1]
    match = re.search(r'(?m)^\s*mCurrentFocus=(.+)$', dump)
    window = match[1].strip() if match else 'No focused window reported'
    owner = re.match(r'Window\{\S+ u\d+ ([\w.]+)/', window, re.ASCII)
    return owner[1] if owner else None, window


if target:
    deadline = time.monotonic() + args.focus_timeout
    while True:
        owner, window = focus()
        if owner == target:
            screenshot = adb('exec-out', 'screencap', '-p')
            owner, window = focus()
            if owner == target:
                break
        if time.monotonic() >= deadline:
            if args.diagnostic:
                args.diagnostic.parent.mkdir(parents=True, exist_ok=True)
                args.diagnostic.write_text(json.dumps({'reason': 'foreground blocked', 'expected_package': target,
                                                       'focus': window}, indent=2) + '\n')
            print(f'Capture blocked: expected {target} in the foreground, observed {window}', file=sys.stderr)
            sys.exit(2)
        time.sleep(min(1, max(0, deadline - time.monotonic())))
else:
    screenshot = adb('exec-out', 'screencap', '-p')

with Image.open(io.BytesIO(screenshot)) as image:
    image.load()
    if image.format != 'PNG' or image.size != tuple(map(int, args.size.split('x'))):
        raise RuntimeError(f'Expected {args.size} PNG, got {image.size} {image.format}')
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(screenshot)
print(f'Captured {args.output}: {args.size}')
