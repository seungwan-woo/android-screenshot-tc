#!/usr/bin/env python3
"""Render one screenshot report or refresh the static archive index."""
import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import shutil


STYLE = '''<style>
:root{color-scheme:light dark;font:16px/1.55 system-ui,sans-serif}body{max-width:1120px;margin:3rem auto;padding:0 1.25rem}
a{color:LinkText}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:.65rem;border-bottom:1px solid GrayText}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}figure{margin:0}
img{display:block;width:100%;height:auto;border-radius:.4rem}figcaption{margin-bottom:.4rem;font-weight:600}
pre{white-space:pre-wrap;overflow-wrap:anywhere}code{overflow-wrap:anywhere}
</style>'''
RUN_KEY = re.compile(r'[0-9]+-[0-9]+')


def page(title, body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' + f'<title>{escape(title)}</title>{STYLE}<main>{body}</main></html>\n'


def json_object(path):
    if not path.is_file():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} must contain a JSON object')
    return value


def render(artifacts, output, outcome):
    screenshot = artifacts / 'screenshot'
    run = json_object(screenshot / 'run-result.json')
    comparison = json_object(screenshot / 'comparison/result.json')
    name = str(run.get('name', 'Emulator screenshot test'))
    run_id = os.getenv('GITHUB_RUN_ID', '0')
    attempt = os.getenv('GITHUB_RUN_ATTEMPT', '1')
    key = f'{run_id}-{attempt}'
    if not RUN_KEY.fullmatch(key):
        raise ValueError('Invalid GitHub run ID or attempt')
    repo = os.getenv('GITHUB_REPOSITORY', '')
    actions_url = ''
    if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        actions_url = f'https://github.com/{repo}/actions/runs/{run_id}/attempts/{attempt}'
    status = run.get('status', 'error')
    metadata = {
        'key': key, 'name': name, 'status': status, 'outcome': outcome,
        'mode': run.get('mode', ''), 'stage': run.get('stage', 'runner setup'),
        'error': run.get('error', ''), 'smoke_exit': run.get('smoke_exit'),
        'capture_diagnostic': run.get('capture_diagnostic'),
        'capture': run.get('capture'),
        'ref': os.getenv('GITHUB_REF_NAME', ''), 'sha': os.getenv('GITHUB_SHA', ''),
        'recorded_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ'),
        'actions_url': actions_url, 'comparison': comparison,
    }
    output.mkdir(parents=True, exist_ok=True)
    thumbnails = []
    cropped = screenshot / 'cropped.png'
    candidates = [('actual.png', 'Captured screen', cropped if cropped.is_file() else screenshot / 'actual.png')]
    if comparison:
        candidates = [(name + '.png', label, screenshot / 'comparison' / (name + '.png'))
                      for name, label in [('reference', 'Reference'), ('actual', 'Captured screen'), ('diff', 'Difference')]]
    for filename, label, source in candidates:
        if source.is_file() and not source.is_symlink():
            shutil.copyfile(source, output / filename)
            thumbnails.append(f'<figure><figcaption>{label}</figcaption><a href="{filename}"><img src="{filename}" alt="{label}"></a></figure>')
    (output / 'report.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    body = f'<h1>{escape(name)}</h1><p>Comparison <strong>{escape(str(status))}</strong> · test job <strong>{escape(outcome)}</strong></p>'
    if actions_url:
        body += f'<p><a href="{actions_url}">GitHub Actions run {key}</a></p>'
    if isinstance(comparison.get('diff_ratio'), (int, float)):
        body += f'<p>Changed pixels <strong>{comparison["diff_ratio"]:.2%}</strong></p>'
    if thumbnails:
        body += '<section class="gallery">' + ''.join(thumbnails) + '</section>'
    body += '<details><summary>Run details</summary><pre>' + escape(json.dumps(metadata, ensure_ascii=False, indent=2)) + '</pre></details>'
    (output / 'index.html').write_text(page(name, body))


def index(site):
    rows = []
    reports = [path for path in (site / 'runs').glob('*/report.json') if RUN_KEY.fullmatch(path.parent.name)]
    for path in sorted(reports, key=lambda item: tuple(map(int, item.parent.name.split('-'))), reverse=True):
        data = json_object(path)
        key = path.parent.name
        cells = ''.join(f'<td>{escape(str(data.get(field, "")))}</td>' for field in ('name', 'ref', 'mode', 'status', 'outcome', 'recorded_at'))
        rows.append(f'<tr><td><a href="runs/{key}/">{key}</a></td>{cells}</tr>')
    header = ''.join(f'<th scope="col">{field}</th>' for field in ('Run', 'Scenario', 'Ref', 'Mode', 'Comparison', 'Job', 'Recorded (UTC)'))
    body = '<h1>Android screenshot reports</h1><p>Each entry records one GitHub Actions run attempt.</p>'
    body += f'<table><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
    (site / 'index.html').write_text(page('Android screenshot reports', body))
    (site / '.nojekyll').touch()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    render_cmd = commands.add_parser('render')
    render_cmd.add_argument('--artifacts', type=Path, required=True)
    render_cmd.add_argument('--output', type=Path, required=True)
    render_cmd.add_argument('--outcome', choices=('success', 'failure', 'cancelled', 'skipped'), required=True)
    index_cmd = commands.add_parser('index')
    index_cmd.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'render':
        render(args.artifacts, args.output, args.outcome)
    else:
        index(args.site)


if __name__ == '__main__':
    main()
