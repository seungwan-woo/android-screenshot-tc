import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'ux.py'


class CliTests(unittest.TestCase):
    def run_cli(self, *args, cli=CLI, cwd=None):
        return subprocess.run([sys.executable, str(cli), *map(str, args)], capture_output=True, text=True, cwd=cwd)

    def test_demo_runs_outside_repository_with_canonical_report(self):
        with tempfile.TemporaryDirectory() as temp:
            portable = Path(temp) / 'portable'
            shutil.copytree(ROOT / 'scripts', portable / 'scripts')
            out = Path(temp) / 'run'
            result = self.run_cli('demo', '--output-dir', out, cli=portable / 'scripts' / 'ux.py')
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((out / 'assessment.json').read_text())
            self.assertEqual(report['validation_scope'], 'fixture_only')
            self.assertEqual(report['overall_status'], 'inconclusive')
            self.assertEqual(report['summary']['fail'], 0)
            self.assertGreaterEqual(report['summary']['pass'], 5)
            self.assertIn('fixture', (out / 'report.md').read_text().lower())

    def test_unsupported_requirement_is_inconclusive_and_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(self.run_cli('demo', '--output-dir', out).returncode, 0)
            design = json.loads((out / 'prepared.json').read_text())
            design['requirements'].append({'id': 'unknown', 'kind': 'mindreading', 'node_id': '10:2', 'state': 'empty'})
            (out / 'prepared.json').write_text(json.dumps(design))
            result = self.run_cli('assess', '--design', out / 'prepared.json', '--runtime', out / 'empty.json', '--tag-map', out / 'tags.json', '--output', out / 'partial.json')
            self.assertEqual(result.returncode, 3, result.stderr)
            report = json.loads((out / 'partial.json').read_text())
            self.assertEqual(report['findings'][-1]['status'], 'inconclusive')

    def test_compare_fails_for_changed_pixels(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new('RGB', (4, 4), 'white').save(root / 'ref.png')
            Image.new('RGB', (4, 4), 'black').save(root / 'actual.png')
            result = self.run_cli('compare', '--reference', root / 'ref.png', '--actual', root / 'actual.png', '--output-dir', root / 'comparison')
            self.assertEqual(result.returncode, 1, result.stderr)

    def test_invalid_json_and_output_alias_are_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'bad.json'
            path.write_text('{"value": NaN}')
            result = self.run_cli('normalize', '--input', path, '--output', path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(), '{"value": NaN}')

    def test_stale_visual_registration_cannot_be_attached(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(self.run_cli('demo', '--output-dir', out).returncode, 0)
            Image.new('RGB', (360, 592), 'black').save(out / 'aligned.png')
            result = self.run_cli('compare', '--reference', out / 'reference.png', '--actual', out / 'aligned.png', '--registration', out / 'registration.json', '--output-dir', out / 'new-comparison')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('hash', result.stderr.lower())


    def test_cli_patch_cleanup_preserves_dirty_preimage_and_later_conflict(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp); project = out / 'project'; project.mkdir()
            source = project / 'Screen.kt'; original = b'// user dirty work\nval tag = "old"\n'; source.write_bytes(original)
            plan = out / 'plan.json'; plan.write_text(json.dumps({'patches': [{'path': 'Screen.kt', 'before_sha256': hashlib.sha256(original).hexdigest(), 'search': '"old"', 'replace': '"temporary"'}]}))
            result = self.run_cli('instrument', '--project-root', project, '--plan', plan, '--session', out / 'session')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('temporary', source.read_text())
            result = self.run_cli('cleanup', '--session', out / 'session')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(self.run_cli('instrument', '--project-root', project, '--plan', plan, '--session', out / 'session-2').returncode, 0)
            source.write_text('// later user change\n')
            result = self.run_cli('cleanup', '--session', out / 'session-2')
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(source.read_text(), '// later user change\n')


    def test_all_commands_preserve_ancillary_evidence_aliases(self):
        import os
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(self.run_cli('demo', '--output-dir', out).returncode, 0)
            assessment = out / 'assessment.json'; before = assessment.read_bytes()
            alias = out / 'alias.md'; os.link(assessment, alias)
            result = self.run_cli('report', '--assessment', assessment, '--output', alias)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(assessment.read_bytes(), before)
            reference = out / 'reference.png'; before = reference.read_bytes()
            result = self.run_cli('align', '--design', out / 'prepared.json', '--runtime', out / 'empty.json', '--output', reference, '--registration', out / 'new-registration.json')
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(reference.read_bytes(), before)
            compare_dir = out / 'other-comparison'; compare_dir.mkdir()
            registration_alias = compare_dir / 'reference.png'; registration_alias.write_bytes((out / 'registration.json').read_bytes()); before = registration_alias.read_bytes()
            result = self.run_cli('compare', '--reference', reference, '--actual', out / 'aligned.png', '--registration', registration_alias, '--output-dir', compare_dir)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(registration_alias.read_bytes(), before)


    def test_cli_assessment_rejects_fabricated_pass_and_changed_artifacts(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(self.run_cli('demo', '--output-dir', out).returncode, 0)
            visual = json.loads((out / 'visual.json').read_text())
            keys = ('runtime_capture_id', 'design_revision', 'passed', 'reference_sha256', 'source_image_sha256')
            (out / 'bare.json').write_text(json.dumps({k: visual[k] for k in keys}))
            def assess(visual_path, name):
                result = self.run_cli('assess', '--design', out / 'prepared.json', '--runtime', out / 'empty.json', '--tag-map', out / 'tags.json', '--visual', visual_path, '--output', out / name)
                self.assertEqual(result.returncode, 3, result.stderr)
                return json.loads((out / name).read_text())['findings'][4]
            self.assertEqual(assess(out / 'bare.json', 'bare-result.json')['status'], 'inconclusive')
            Image.new('RGB', (360, 592), 'black').save(visual['actual'])
            finding = assess(out / 'visual.json', 'changed-result.json')
            self.assertEqual(finding['status'], 'inconclusive')
            self.assertIn('hash', finding['reason'])

    def test_document_links_and_skill_frontmatter_are_portable(self):
        import re
        skill = (ROOT / 'SKILL.md').read_text()
        self.assertTrue(skill.startswith('---\nname: figma-compose-ux\ndescription: Use when'))
        for doc in ROOT.rglob('*.md'):
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', doc.read_text()):
                if '://' in target or target.startswith('#'):
                    continue
                self.assertTrue((doc.parent / target.split('#', 1)[0]).exists(), (doc, target))


    def test_relative_paths_support_documented_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(self.run_cli('demo', '--output-dir', 'run', cwd=temp).returncode, 0)
            result = self.run_cli('align', '--design', 'run/prepared.json', '--runtime', 'run/empty.json', '--output', 'aligned-relative.png', '--registration', 'relative-registration.json', cwd=temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli('compare', '--reference', 'run/reference.png', '--actual', 'aligned-relative.png', '--registration', 'relative-registration.json', '--channel-tolerance', 20, '--output-dir', 'relative-comparison', cwd=temp)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_cli('assess', '--design', 'run/prepared.json', '--runtime', 'run/empty.json', '--tag-map', 'run/tags.json', '--visual', 'relative-comparison/pixels.json', '--output', 'assessment.json', cwd=temp)
            self.assertEqual(result.returncode, 3, result.stderr)
            report = json.loads((Path(temp) / 'assessment.json').read_text())
            self.assertEqual(report['findings'][4]['status'], 'pass', report['findings'][4])


if __name__ == '__main__':
    unittest.main()
