import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ANDROID = Path(__file__).resolve().parents[1] / 'ci/android'


class ReportArchiveTests(unittest.TestCase):
    def test_archives_failed_runs_and_keeps_previous_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'repo'
            tools = workspace / 'ci/android'
            tools.mkdir(parents=True)
            for script in ('archive-report.sh', 'report.py'):
                shutil.copyfile(ANDROID / script, tools / script)
            remote = root / 'remote.git'
            self.git(root, 'init', '--bare', str(remote))
            self.git(workspace, 'init')
            self.git(workspace, 'remote', 'add', 'origin', str(remote))
            self.git(workspace, '-c', 'user.name=Test', '-c', 'user.email=test@example.org',
                     'commit', '--allow-empty', '-m', 'base')
            artifact = root / 'artifacts'
            screenshot = artifact / 'screenshot'
            screenshot.mkdir(parents=True)
            (screenshot / 'run-result.json').write_text(json.dumps({
                'name': '<button>', 'status': 'error', 'stage': 'capture',
                'capture_diagnostic': {'reason': 'foreground blocked'},
            }))
            for attempt in ('1', '2'):
                env = {**os.environ, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': attempt, 'RUNNER_TEMP': directory}
                output = root / ('report-' + attempt)
                subprocess.run([sys.executable, str(tools / 'report.py'), 'render', '--artifacts', str(artifact),
                                '--output', str(output), '--outcome', 'failure'], env=env, check=True)
                subprocess.run(['bash', str(tools / 'archive-report.sh'), str(output)], cwd=workspace, env=env,
                               check=True, capture_output=True)
            index = self.git(remote, 'show', 'gh-pages:index.html')
            self.assertIn('runs/123-1/', index)
            self.assertIn('runs/123-2/', index)
            self.assertIn('&lt;button&gt;', index)
            report = json.loads(self.git(remote, 'show', 'gh-pages:runs/123-1/report.json'))
            self.assertEqual(report['capture_diagnostic']['reason'], 'foreground blocked')
            self.assertEqual(report['outcome'], 'failure')

    @staticmethod
    def git(path, *arguments):
        return subprocess.run(['git', '-C', str(path), *arguments], check=True, capture_output=True, text=True).stdout
