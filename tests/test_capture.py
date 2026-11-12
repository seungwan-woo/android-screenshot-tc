import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'ci/android/capture.py'

class CaptureCliTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / 'adb.jsonl'
        self.png = self.root / 'device.png'
        Image.new('RGB', (1080, 1920), 'white').save(self.png)
        adb = self.root / 'adb'
        adb.write_text('''#!/usr/bin/env python3
import json,os,pathlib,sys
args=sys.argv[1:]
with open(os.environ['FAKE_ADB_LOG'],'a') as out: out.write(json.dumps(args)+'\\n')
if args[-2:]==['getprop','sys.boot_completed']:
    print(os.environ.get('FAKE_BOOT','1'))
elif args[-3:]==['exec-out','screencap','-p']:
    sys.stdout.buffer.write(pathlib.Path(os.environ['FAKE_PNG']).read_bytes())
elif args[-3:]==['shell','wm','size']:
    print('Physical size: '+os.environ.get('FAKE_SIZE','1080x1920'))
elif args[-3:]==['shell','wm','density']:
    print('Physical density: '+os.environ.get('FAKE_DENSITY','420'))
''')
        adb.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.root) + os.pathsep + os.environ['PATH'],
                    'FAKE_ADB_LOG': str(self.log), 'FAKE_PNG': str(self.png)}

    def capture(self, *options, no_launch=True):
        mode = ['--no-launch'] if no_launch else []
        return subprocess.run([sys.executable, str(SCRIPT), '--serial', 'test-device',
                              *mode, '--settle-seconds', '0', '--output', str(self.root / 'captured.png'), *options],
                              env=self.env, text=True, capture_output=True, timeout=20)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_no_launch_preserves_display_and_activity_state(self):
        p = self.capture()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.commands(), [
            ['-s', 'test-device', 'shell', 'getprop', 'sys.boot_completed'],
            ['-s', 'test-device', 'exec-out', 'screencap', '-p'],
        ])
        self.assertEqual((self.root / 'captured.png').read_bytes(), self.png.read_bytes())

    def test_unbooted_device_fails_without_capturing(self):
        self.env['FAKE_BOOT'] = '0'
        p = self.capture()
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((self.root / 'captured.png').exists())
        self.assertEqual(len(self.commands()), 1)

    def test_no_launch_rejects_application_install_before_device_mutation(self):
        apk = self.root / 'sample.apk'
        apk.write_bytes(b'test apk')
        p = self.capture('--apk', str(apk), '--component', 'example/.Main')
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual(self.commands(), [])

    def test_launch_preserves_already_correct_display_geometry(self):
        p = self.capture('--component', 'example/.Main', no_launch=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn(['-s', 'test-device', 'shell', 'wm', 'size', '1080x1920'], self.commands())
        self.assertNotIn(['-s', 'test-device', 'shell', 'wm', 'density', '420'], self.commands())

    def test_launch_corrects_mismatched_display_geometry(self):
        self.env.update(FAKE_SIZE='720x1280', FAKE_DENSITY='320')
        p = self.capture('--component', 'example/.Main', no_launch=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(['-s', 'test-device', 'shell', 'wm', 'size', '1080x1920'], self.commands())
        self.assertIn(['-s', 'test-device', 'shell', 'wm', 'density', '420'], self.commands())

if __name__ == '__main__':
    unittest.main()
