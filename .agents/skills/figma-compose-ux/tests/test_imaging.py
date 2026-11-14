import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class ImagingTest(unittest.TestCase):
    def setUp(self):
        module = Path(__file__).resolve().parents[1] / 'scripts/uxlib/imaging.py'
        self.assertTrue(module.exists(), 'imaging implementation is missing')
        from uxlib.imaging import align_image, compare_png
        self.align = align_image; self.compare = compare_png
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.raw = self.root / 'raw.png'; Image.new('RGB', (30, 60), 'white').save(self.raw)
        self.runtime = {'viewport_px': [30, 60], 'insets_px': {'left': 0, 'top': 3, 'right': 0, 'bottom': 3}, 'device': {'density': 3}}
        self.design = {'viewport': {'width_dp': 10, 'height_dp': 18, 'figma_units_per_dp': 1}, 'design': {'reference_scale': 2}}

    def test_crop_then_scale_uses_declared_density_and_export_scale(self):
        out = self.root / 'aligned.png'
        result = self.align(self.raw, self.runtime, self.design, out)
        with Image.open(out) as image: self.assertEqual(image.size, (20, 36))
        self.assertEqual(result['crop_px'], [0, 3, 30, 57])

    def test_wrong_viewport_is_rejected_not_stretched(self):
        self.design['viewport']['width_dp'] = 12
        with self.assertRaises(ValueError): self.align(self.raw, self.runtime, self.design, self.root / 'x.png')

    def test_stale_screenshot_hash_is_rejected(self):
        self.runtime['image_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.align(self.raw, self.runtime, self.design, self.root / 'x.png')

    def test_exact_match_and_real_change_have_opposite_results(self):
        other = self.root / 'other.png'; Image.new('RGB', (30, 60), 'white').save(other)
        self.assertTrue(self.compare(self.raw, other, self.root / 'match')['passed'])
        with Image.open(other) as image: image.putpixel((1, 1), (0, 0, 0)); image.save(other)
        result = self.compare(self.raw, other, self.root / 'changed')
        self.assertFalse(result['passed']); self.assertEqual(result['changed_pixels'], 1)
        self.assertTrue((self.root / 'changed/diff.png').is_file())

    def test_dimension_mismatch_fails_and_invalid_threshold_rejected(self):
        other = self.root / 'other.png'; Image.new('RGB', (15, 30), 'white').save(other)
        self.assertFalse(self.compare(self.raw, other, self.root / 'size')['passed'])
        with self.assertRaises(ValueError): self.compare(self.raw, other, self.root / 'bad', max_diff_ratio=2)

    def test_unclear_transparency_requires_background(self):
        other = self.root / 'alpha.png'; Image.new('RGBA', (30, 60), (0, 0, 0, 0)).save(other)
        with self.assertRaises(ValueError): self.compare(self.raw, other, self.root / 'alpha')


    def test_output_alias_cannot_replace_original_capture_or_reference(self):
        before = self.raw.read_bytes()
        with self.assertRaises(ValueError): self.align(self.raw, self.runtime, self.design, self.raw)
        self.assertEqual(self.raw.read_bytes(), before)
        folder = self.root / 'comparison'; folder.mkdir()
        reference = folder / 'reference.png'; Image.new('RGB', (30, 60), 'white').save(reference)
        before = reference.read_bytes()
        with self.assertRaises(ValueError): self.compare(reference, self.raw, folder)
        self.assertEqual(reference.read_bytes(), before)


    def test_saved_pixel_evidence_is_recomputed_and_tampering_rejected(self):
        from uxlib.imaging import verify_comparison
        other = self.root / 'other.png'; Image.new('RGB', (30, 60), 'white').save(other)
        result = self.compare(self.raw, other, self.root / 'match')
        self.assertIsNone(verify_comparison(result, self.root))
        Image.new('RGB', (30, 60), 'black').save(result['actual'])
        self.assertIn('hash', verify_comparison(result, self.root))


if __name__ == '__main__': unittest.main()
