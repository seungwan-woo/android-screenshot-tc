#!/usr/bin/env python3
"""Build or select an APK, capture its foreground screen and compare it."""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / 'ci/android'
DEFAULT_COMPONENT = 'com.example.screenshotci/.MainActivity'
DEFAULTS = {
    'schema_version': 1, 'name': 'Screenshot CI sample', 'component': DEFAULT_COMPONENT,
    'reference': 'ci/android/reference/sample.png', 'apk': None, 'gradle': None,
    'size': '1080x1920', 'density': 420, 'settle_seconds': 3, 'focus_timeout': 25, 'crop': None,
    'channel_tolerance': 0, 'max_diff_ratio': 0, 'smoke': False,
}


def repo_path(value, suffix=None):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or '.git' in Path(value).parts:
        raise ValueError('Expected a path relative to the repository')
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT) or (suffix and path.suffix != suffix):
        raise ValueError(f'Invalid repository path: {value}')
    return path


def load_config(path):
    if path is not None:
        data = json.loads(repo_path(path, '.json').read_text())
    else:
        data = {}
    if not isinstance(data, dict) or set(data) - DEFAULTS.keys():
        raise ValueError('Unknown or invalid screenshot configuration fields')
    config = {**DEFAULTS, **data}
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    if not isinstance(config['name'], str) or not config['name'].strip() or len(config['name']) > 120:
        raise ValueError('name must be a nonempty string of at most 120 characters')
    if not isinstance(config['component'], str) or not re.fullmatch(r'[\w.]+/[\w.$]+', config['component'], re.ASCII):
        raise ValueError('component must be PACKAGE/ACTIVITY')
    if not isinstance(config['size'], str) or not re.fullmatch(r'[1-9]\d{0,3}x[1-9]\d{0,3}', config['size']):
        raise ValueError('size must be WIDTHxHEIGHT')
    crop = config['crop']
    if crop is not None:
        width, height = map(int, config['size'].split('x'))
        if not isinstance(crop, list) or len(crop) != 4 or any(type(value) is not int for value in crop):
            raise ValueError('crop must contain four pixel coordinates')
        left, top, right, bottom = crop
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError('crop is outside the configured display')
    for key, minimum, maximum in [('density', 1, 1000), ('channel_tolerance', 0, 255)]:
        if type(config[key]) is not int or not minimum <= config[key] <= maximum:
            raise ValueError(f'{key} must be an integer in [{minimum},{maximum}]')
    for key, maximum in [('settle_seconds', 60), ('focus_timeout', 120), ('max_diff_ratio', 1)]:
        value = config[key]
        if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
            raise ValueError(f'{key} must be in [0,{maximum}]')
    if type(config['smoke']) is not bool:
        raise ValueError('smoke must be a boolean')
    if config['smoke'] and (config['apk'] or config['gradle'] or config['component'] != DEFAULT_COMPONENT
                            or config['size'] != '1080x1920' or config['density'] != 420):
        raise ValueError('smoke requires the built-in sample and its display geometry')
    repo_path(config['reference'], '.png')
    if config['apk'] is not None:
        repo_path(config['apk'], '.apk')
    elif config['component'] != DEFAULT_COMPONENT or config['gradle'] is not None:
        raise ValueError('A custom app must specify apk')
    gradle = config['gradle']
    if gradle is not None:
        if not isinstance(gradle, dict) or set(gradle) != {'directory', 'task'}:
            raise ValueError('gradle needs directory and task')
        repo_path(gradle['directory'])
        if not isinstance(gradle['task'], str) or not re.fullmatch(r'(?::[\w-]+)*:assemble[\w]+', gradle['task'], re.ASCII):
            raise ValueError('gradle.task must be a fully qualified assemble task')
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', help='Repository-relative JSON file')
    parser.add_argument('--mode', choices=('verify', 'record'), default='verify')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-override', type=Path, help='Local ci-check.sh compatibility')
    parser.add_argument('--smoke-output', type=Path)
    parser.add_argument('--recover-launcher-anr', action='store_true', help='Allow one Quickstep restart on CI AVD')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = {'mode': args.mode, 'status': 'error', 'stage': 'configuration', 'name': args.config or DEFAULTS['name']}

    def run(command, cwd=ROOT, env=None):
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env)
        return result.returncode

    def require(command, **options):
        code = run(command, **options)
        if code:
            raise RuntimeError(f'{state["stage"]} failed with exit {code}')

    try:
        config = load_config(args.config)
        state['name'] = config['name']
        state['config'] = args.config
        reference = args.reference_override or repo_path(config['reference'], '.png')
        if args.mode == 'verify' and not reference.is_file():
            raise ValueError(f'Reference PNG is missing: {reference}')
        if args.validate_only:
            state['status'] = 'validated'
            return 0
        state['capture'] = {key: config[key] for key in ('component', 'size', 'density', 'crop')}
        state['stage'] = 'build'
        if config['gradle']:
            project = repo_path(config['gradle']['directory'])
            require(['bash', './gradlew', '--no-daemon', config['gradle']['task']], cwd=project)
        if config['apk']:
            apk = repo_path(config['apk'], '.apk')
        else:
            require(['bash', ANDROID / 'sample/build.sh'])
            apk = ANDROID / 'sample/build/sample.apk'
        if not apk.is_file():
            raise ValueError(f'APK is missing: {apk}')
        serial = os.environ.get('ANDROID_SERIAL', 'emulator-5554')
        adb = ['adb', '-s', serial]
        require([*adb, 'shell', 'am', 'force-stop', config['component'].split('/')[0]])
        state['stage'] = 'capture'
        diagnostic = output / 'capture-diagnostic.json'
        capture = [sys.executable, ANDROID / 'capture.py', '--apk', apk, '--component', config['component'],
                   '--output', output / 'actual.png', '--diagnostic', diagnostic]
        for name in ('size', 'density', 'settle_seconds', 'focus_timeout'):
            capture.extend(['--' + name.replace('_', '-'), config[name]])
        code = run(capture)
        if code == 2 and args.recover_launcher_anr and diagnostic.is_file():
            observed = json.loads(diagnostic.read_text())['focus']
            if 'Application Not Responding: com.android.launcher3}' in observed:
                diagnostic.rename(output / 'launcher-anr-recovery.json')
                require([*adb, 'shell', 'am', 'force-stop', 'com.android.launcher3'])
                code = run(capture)
        if code:
            if diagnostic.is_file():
                state['capture_diagnostic'] = json.loads(diagnostic.read_text())
            raise RuntimeError(f'capture failed with exit {code}')
        candidate = output / 'actual.png'
        if config['crop'] is not None:
            with Image.open(candidate) as image:
                candidate = output / 'cropped.png'
                image.crop(tuple(config['crop'])).save(candidate)
        if args.mode == 'verify':
            state['stage'] = 'comparison'
            code = run([sys.executable, ANDROID / 'compare.py', reference, candidate,
                        '--artifacts', output / 'comparison', '--channel-tolerance', config['channel_tolerance'],
                        '--max-diff-ratio', config['max_diff_ratio']])
            if code not in (0, 1):
                raise RuntimeError(f'comparison failed with exit {code}')
            state['status'] = 'match' if code == 0 else 'difference'
        else:
            code = 0
            state['status'] = 'recorded'
        if config['smoke'] and args.smoke_output:
            state['stage'] = 'smoke'
            state['smoke_exit'] = run([sys.executable, ANDROID / 'smoke.py'],
                                      env={**os.environ, 'SCREENSHOT_VALIDATION_OUT': str(args.smoke_output.resolve())})
            if state['smoke_exit'] != 0:
                state['error'] = 'Sample smoke test failed'
                return 1 if code == 1 else 2
        state['stage'] = 'completed'
        return code
    except (OSError, ValueError, RuntimeError) as error:
        state['error'] = str(error)
        print(error, file=sys.stderr)
        return 2
    finally:
        (output / 'run-result.json').write_text(json.dumps(state, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
