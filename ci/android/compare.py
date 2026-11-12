#!/usr/bin/env python3
"""Compare full-display PNGs. Exit 0=match, 1=visual difference, 2=bad input."""
import argparse
import json
from pathlib import Path
import sys
from PIL import Image, ImageChops

p = argparse.ArgumentParser()
p.add_argument('reference', type=Path)
p.add_argument('actual', type=Path)
p.add_argument('--artifacts', type=Path, default=Path('artifacts/screenshot'))
p.add_argument('--max-diff-ratio', type=float, default=0.0)
p.add_argument('--channel-tolerance', type=int, default=0)
args = p.parse_args()
if not 0 <= args.max_diff_ratio <= 1 or not 0 <= args.channel_tolerance <= 255:
    p.error('ratio must be in [0,1] and channel tolerance in [0,255]')
args.artifacts.mkdir(parents=True, exist_ok=True)
try:
    with Image.open(args.reference) as image:
        reference = image.convert('RGB')
    with Image.open(args.actual) as image:
        actual = image.convert('RGB')
except (OSError, ValueError) as error:
    print(f'Input error: {error}', file=sys.stderr)
    sys.exit(2)
reference.save(args.artifacts / 'reference.png')
actual.save(args.artifacts / 'actual.png')
if reference.size != actual.size:
    report = {'passed': False, 'reason': 'size mismatch',
              'reference_size': reference.size, 'actual_size': actual.size}
else:
    difference = ImageChops.difference(reference, actual)
    red, green, blue = difference.split()
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    mask = maximum.point([0 if i <= args.channel_tolerance else 255 for i in range(256)])
    changed = mask.histogram()[255]
    ratio = changed / (reference.width * reference.height)
    overlay = actual.copy()
    overlay.paste((255, 0, 80), (0, 0, *actual.size), mask)
    overlay.save(args.artifacts / 'diff.png')
    report = {'passed': ratio <= args.max_diff_ratio, 'changed_pixels': changed,
              'diff_ratio': ratio, 'max_diff_ratio': args.max_diff_ratio,
              'channel_tolerance': args.channel_tolerance,
              'width': actual.width, 'height': actual.height}
(args.artifacts / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
sys.exit(0 if report['passed'] else 1)
