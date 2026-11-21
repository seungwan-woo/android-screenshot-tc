import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'ci/android/run-screenshot.py'


class ScreenshotConfigTests(unittest.TestCase):
    def test_custom_gradle_apk_and_crop_flow_to_pixel_comparison(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            workspace = Path(directory)
            relative = workspace.relative_to(ROOT)
            (workspace / 'gradlew').write_text('test "$2" = ":app:assembleDebug" && touch custom.apk\n')
            image = workspace / 'device.png'
            Image.new('RGB', (12, 18), '#336699').save(image)
            Image.new('RGB', (6, 8), '#336699').save(workspace / 'reference.png')
            adb = workspace / 'adb'
            adb.write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
if args[-2:] == ['getprop', 'sys.boot_completed']:
    print(1)
elif args[-2:] == ['wm', 'size']:
    print('Physical size: 12x18')
elif args[-2:] == ['wm', 'density']:
    print('Physical density: 160')
elif args[-3:] == ['dumpsys', 'window', 'displays']:
    print('mCurrentFocus=Window{abc u0 example.app/.MainActivity}')
elif args[-3:] == ['exec-out', 'screencap', '-p']:
    sys.stdout.buffer.write(Path(os.environ['MOCK_FIGMA_DEVICE_PNG']).read_bytes())
''')
            adb.chmod(0o755)
            config = workspace / 'test.json'
            config.write_text(json.dumps({
                'component': 'example.app/.MainActivity', 'apk': str(relative / 'custom.apk'),
                'gradle': {'directory': str(relative), 'task': ':app:assembleDebug'},
                'reference': str(relative / 'reference.png'), 'size': '12x18', 'density': 160,
                'crop': [2, 3, 8, 11], 'settle_seconds': 0,
            }))
            output = workspace / 'output'
            env = {**os.environ, 'PATH': str(workspace) + os.pathsep + os.environ['PATH'],
                   'MOCK_FIGMA_DEVICE_PNG': str(image)}
            result = subprocess.run([sys.executable, str(RUN), '--config', str(config.relative_to(ROOT)),
                                     '--output', str(output)], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((output / 'run-result.json').read_text())['status'], 'match')
            self.assertEqual(json.loads((output / 'comparison/result.json').read_text())['changed_pixels'], 0)
            with Image.open(output / 'actual.png') as original:
                self.assertEqual(original.size, (12, 18))
