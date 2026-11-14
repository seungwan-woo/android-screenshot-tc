"""Explicit coordinate registration and image evidence; no inferred viewport stretching."""
import hashlib
import json
import math
from pathlib import Path
from PIL import Image, ImageChops


def _number(value, name, minimum=0, strict=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if value < minimum or (strict and value == minimum):
        raise ValueError(f'{name} is outside its supported range')
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()



def ensure_distinct(outputs, inputs):
    """Do not overwrite source evidence, including symlink/hardlink aliases."""
    targets, sources = list(map(Path, outputs)), list(map(Path, inputs))
    for index, target in enumerate(targets):
        for source in sources + targets[:index]:
            if target.resolve() == source.resolve() or (target.exists() and source.exists() and target.samefile(source)):
                raise ValueError('Output paths must differ from input evidence and each other')


def align_image(image_path, runtime, design, output_path):
    image_path, output_path = Path(image_path), Path(output_path).resolve()
    ensure_distinct([output_path], [image_path])
    actual_hash = digest(image_path)
    if runtime.get('image_sha256') and runtime['image_sha256'] != actual_hash:
        raise ValueError('Screenshot hash does not match this capture; recollect matching evidence')
    density = _number(runtime['device']['density'], 'density', strict=True)
    insets = runtime['insets_px']
    edges = [_number(insets[k], f'insets.{k}') for k in ('left', 'top', 'right', 'bottom')]
    if any(int(v) != v for v in edges):
        raise ValueError('Insets must use whole screenshot pixels')
    left, top, right, bottom = map(int, edges)
    with Image.open(image_path) as opened:
        opened.load()
        if list(opened.size) != runtime['viewport_px']:
            raise ValueError('PNG size does not match the recorded viewport')
        if left + right >= opened.width or top + bottom >= opened.height:
            raise ValueError('Insets leave no content area')
        crop_box = (left, top, opened.width - right, opened.height - bottom)
        cropped = opened.crop(crop_box)
        view = design['viewport']
        width = _number(view['width_dp'], 'viewport.width_dp', strict=True)
        height = _number(view['height_dp'], 'viewport.height_dp', strict=True)
        if not math.isclose(cropped.width / density, width, abs_tol=1e-6) or not math.isclose(cropped.height / density, height, abs_tol=1e-6):
            raise ValueError('Content viewport differs from the selected Figma variant; do not stretch it to fit')
        scale = _number(design['design'].get('reference_scale', 1), 'reference_scale', strict=True)
        units = _number(view.get('figma_units_per_dp', 1), 'figma_units_per_dp', strict=True)
        size = (round(width * scale * units), round(height * scale * units))
        if min(size) < 1:
            raise ValueError('Reference export scale produces an empty image')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.resize(size, Image.Resampling.LANCZOS).save(output_path)
    return {'image': str(output_path), 'crop_px': list(crop_box), 'scale': scale * units / density,
            'image_sha256': digest(output_path), 'source_image_sha256': actual_hash,
            'runtime_capture_id': runtime.get('capture_id'), 'design_revision': design['design'].get('revision')}


def _opaque(path, background=None):
    with Image.open(path) as opened:
        image = opened.convert('RGBA')
        if image.getchannel('A').getextrema() != (255, 255):
            if background is None:
                raise ValueError('Transparent reference needs an explicit background color')
            base = Image.new('RGBA', image.size, tuple(background) + (255,))
            image = Image.alpha_composite(base, image)
        return image.convert('RGB')


def compare_png(reference, actual, output_dir, channel_tolerance=0, max_diff_ratio=0, background=None):
    _number(channel_tolerance, 'channel_tolerance')
    _number(max_diff_ratio, 'max_diff_ratio')
    if int(channel_tolerance) != channel_tolerance or channel_tolerance > 255 or max_diff_ratio > 1:
        raise ValueError('Tolerance must be an integer in [0,255]; ratio must be in [0,1]')
    out = Path(output_dir).resolve()
    ensure_distinct([out / name for name in ('reference.png', 'actual.png', 'diff.png', 'pixels.json')], [reference, actual])
    if background is not None and (len(background) != 3 or any(type(c) is not int or c < 0 or c > 255 for c in background)):
        raise ValueError('Background must contain three integer RGB channels in [0,255]')
    a, b = _opaque(reference, background), _opaque(actual, background)
    input_hashes = (digest(reference), digest(actual))
    out.mkdir(parents=True, exist_ok=True)
    a.save(out / 'reference.png'); b.save(out / 'actual.png')
    (out / 'diff.png').unlink(missing_ok=True)
    report = {'method': 'pixel_difference', 'reference_sha256': input_hashes[0], 'actual_sha256': input_hashes[1],
              'reference': str(out / 'reference.png'), 'actual': str(out / 'actual.png'),
              'channel_tolerance': channel_tolerance, 'max_diff_ratio': max_diff_ratio}
    if a.size != b.size:
        report.update(passed=False, reason='dimension mismatch', reference_size=list(a.size), actual_size=list(b.size))
    else:
        channels = ImageChops.difference(a, b).split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        mask = maximum.point([0 if v <= channel_tolerance else 255 for v in range(256)])
        changed = mask.histogram()[255]
        ratio = changed / (a.width * a.height)
        overlay = b.copy(); overlay.paste((255, 0, 80), (0, 0, *b.size), mask); overlay.save(out / 'diff.png')
        report.update(passed=ratio <= max_diff_ratio, changed_pixels=changed, diff_ratio=ratio,
                      diff=str(out / 'diff.png'), width=a.width, height=a.height)
    report.update(reference_artifact_sha256=digest(out / 'reference.png'), actual_artifact_sha256=digest(out / 'actual.png'), background=background)
    if report.get('diff'): report['diff_sha256'] = digest(out / 'diff.png')
    (out / 'pixels.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def comparison_problem(report):
    """Validate measurements before a producer's passed flag can be used."""
    if not isinstance(report, dict) or report.get('method') != 'pixel_difference' or type(report.get('passed')) is not bool:
        return 'Pixel evidence needs method, measurements and an explicit boolean outcome'
    if report.get('evidence_error'):
        return report['evidence_error']
    for key in ('reference', 'actual'):
        if not isinstance(report.get(key), str) or not report[key]:
            return f'Pixel evidence is missing artifact {key}'
    for key in ('reference_sha256', 'actual_sha256', 'reference_artifact_sha256', 'actual_artifact_sha256'):
        value = report.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            return f'Pixel evidence needs {key}'
    try:
        tolerance = _number(report.get('channel_tolerance'), 'channel_tolerance')
        ratio_limit = _number(report.get('max_diff_ratio'), 'max_diff_ratio')
        if int(tolerance) != tolerance or tolerance > 255 or ratio_limit > 1:
            return 'Invalid pixel thresholds'
        if report.get('reason') == 'dimension mismatch':
            sizes = [report.get(k) for k in ('reference_size', 'actual_size')]
            if any(not isinstance(s, list) or len(s) != 2 or any(type(n) is not int or n <= 0 for n in s) for s in sizes) or sizes[0] == sizes[1] or report['passed']:
                return 'Invalid dimension mismatch evidence'
            return None
        width, height, count = [report.get(k) for k in ('width', 'height', 'changed_pixels')]
        if any(type(v) is not int for v in (width, height, count)) or min(width, height) <= 0 or not 0 <= count <= width * height:
            return 'Missing or invalid pixel dimensions/count'
        ratio = _number(report.get('diff_ratio'), 'diff_ratio')
        if not math.isclose(ratio, count / (width * height), rel_tol=0, abs_tol=1e-12) or report['passed'] != (ratio <= ratio_limit):
            return 'Pixel outcome disagrees with measured count/ratio/threshold'
        if not report.get('diff') or not isinstance(report.get('diff_sha256'), str) or len(report['diff_sha256']) != 64:
            return 'Pixel evidence is missing its diff artifact/hash'
    except (ValueError, TypeError) as exc:
        return str(exc)
    return None


def verify_comparison(report, base_dir):
    """Reopen preserved evidence and recompute pixel counts; never write artifacts."""
    problem = comparison_problem(report)
    if problem:
        return problem
    try:
        paths = {}
        for key, hash_key in (('reference', 'reference_artifact_sha256'), ('actual', 'actual_artifact_sha256'), ('diff', 'diff_sha256')):
            if key not in report:
                continue
            path = Path(report[key]); path = path if path.is_absolute() else Path(base_dir) / path
            if digest(path) != report[hash_key]:
                return f'Pixel artifact {key} hash differs from the recorded evidence'
            paths[key] = path
        a, b = _opaque(paths['reference']), _opaque(paths['actual'])
        if report.get('reason') == 'dimension mismatch':
            return None if list(a.size) == report['reference_size'] and list(b.size) == report['actual_size'] else 'Dimension mismatch artifacts disagree with measurements'
        if a.size != b.size or list(a.size) != [report['width'], report['height']]:
            return 'Pixel artifact dimensions disagree with measurements'
        channels = ImageChops.difference(a, b).split()
        maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
        mask = maximum.point([0 if v <= report['channel_tolerance'] else 255 for v in range(256)])
        if mask.histogram()[255] != report['changed_pixels']:
            return 'Pixel artifact differences disagree with measured count'
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f'Pixel artifact evidence unavailable: {exc}'
    return None
