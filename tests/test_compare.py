import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / 'ci/android/compare.py'

class CompareCliTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), 'comparison implementation is missing')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / 'reference.png'
        self.actual = self.root / 'actual.png'
        Image.new('RGB', (2, 2), 'white').save(self.reference)
        Image.new('RGB', (2, 2), 'white').save(self.actual)

    def run_compare(self, *options):
        p = subprocess.run([sys.executable, str(SCRIPT), str(self.reference), str(self.actual),
                            '--artifacts', str(self.root / 'result'), *options],
                           text=True, capture_output=True, timeout=20)
        report = self.root / 'result/result.json'
        return p, json.loads(report.read_text()) if report.exists() else None

    def change_pixel(self, color=(0, 0, 0)):
        with Image.open(self.actual) as image:
            image.putpixel((0, 0), color)
            image.save(self.actual)

    def test_identical_screens_pass_and_report_zero_changes(self):
        p, report = self.run_compare()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(report['passed'])
        self.assertEqual(report['changed_pixels'], 0)

    def test_changed_pixel_fails_and_creates_evidence(self):
        self.change_pixel()
        p, report = self.run_compare()
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual(report['changed_pixels'], 1)
        self.assertEqual(report['diff_ratio'], 0.25)
        for name in ['reference.png', 'actual.png', 'diff.png']:
            self.assertTrue((self.root / 'result' / name).is_file())

    def test_ratio_boundary_is_inclusive(self):
        self.change_pixel()
        self.assertEqual(self.run_compare('--max-diff-ratio', '0.25')[0].returncode, 0)
        self.assertEqual(self.run_compare('--max-diff-ratio', '0.249')[0].returncode, 1)

    def test_channel_tolerance_boundary_is_inclusive(self):
        self.change_pixel((253, 255, 255))
        self.assertEqual(self.run_compare('--channel-tolerance', '2')[0].returncode, 0)
        self.assertEqual(self.run_compare('--channel-tolerance', '1')[0].returncode, 1)

    def test_size_mismatch_fails(self):
        Image.new('RGB', (3, 2), 'white').save(self.actual)
        p, report = self.run_compare()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(report['reason'], 'size mismatch')

    def test_missing_reference_is_input_error(self):
        self.reference.unlink()
        self.assertEqual(self.run_compare()[0].returncode, 2)

    def test_corrupt_actual_is_input_error(self):
        self.actual.write_text('not a PNG')
        self.assertEqual(self.run_compare()[0].returncode, 2)

    def test_invalid_threshold_is_input_error(self):
        self.assertEqual(self.run_compare('--max-diff-ratio', '-1')[0].returncode, 2)

if __name__ == '__main__':
    unittest.main()
