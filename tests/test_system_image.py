import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'ci/android/check-system-image.py'

class SystemImageGuardTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'system image guard implementation is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sdk = Path(self.temp.name)
        self.properties = self.sdk / 'system-images/android-35/default/x86_64/source.properties'
        self.properties.parent.mkdir(parents=True)

    def check(self):
        return subprocess.run([sys.executable, str(SCRIPT)], env={**os.environ, 'ANDROID_HOME': str(self.sdk)},
                              text=True, capture_output=True, timeout=20)

    def test_expected_image_revision_passes(self):
        self.properties.write_text('Pkg.Revision=2\n')
        self.assertEqual(self.check().returncode, 0)

    def test_equivalent_revision_notation_passes(self):
        self.properties.write_text('Pkg.Revision=2.0.0\n')
        self.assertEqual(self.check().returncode, 0)

    def test_image_upgrade_requires_explicit_review(self):
        self.properties.write_text('Pkg.Revision=3\n')
        p = self.check()
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('revision 2', p.stderr)
        self.assertIn('baseline', p.stderr)

    def test_missing_image_fails(self):
        self.assertNotEqual(self.check().returncode, 0)

if __name__ == '__main__':
    unittest.main()
