#!/usr/bin/env python3
"""Portable CLI. Exit: 0 successful operation/pass, 1 failed check, 2 bad input, 3 inconclusive."""
import argparse
import json
from pathlib import Path
import sys
from uxlib import assessment, design, imaging, instrumentation, reporting, runtime


def read(path):
    def invalid(token):
        raise ValueError(f'Non-finite JSON number: {token}')
    value = json.loads(Path(path).read_text(), parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError('JSON document must be an object')
    return value


def write(path, value, inputs=()):
    path = Path(path)
    imaging.ensure_distinct([path], [source for source in inputs if source])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    def command(name, fields):
        p = subs.add_parser(name)
        for field in fields:
            p.add_argument('--' + field, required=True)
        return p
    p = command('prepare', ('design', 'output')); p.add_argument('--code-connect'); p.add_argument('--source-root')
    command('normalize', ('input', 'output'))
    p = command('collect', ('serial', 'package', 'build-id', 'state', 'metadata', 'output-dir')); p.add_argument('--adb', default='adb')
    p = command('align', ('design', 'runtime', 'output')); p.add_argument('--registration', required=True)
    p = command('compare', ('reference', 'actual', 'output-dir')); p.add_argument('--registration'); p.add_argument('--channel-tolerance', type=int, default=0); p.add_argument('--max-diff-ratio', type=float, default=0); p.add_argument('--background', nargs=3, type=int)
    p = command('assess', ('design', 'tag-map', 'output')); p.add_argument('--runtime', action='append', required=True); p.add_argument('--trace'); p.add_argument('--visual')
    command('report', ('assessment', 'output'))
    command('instrument', ('project-root', 'plan', 'session'))
    command('cleanup', ('session',))
    command('demo', ('output-dir',))
    args = parser.parse_args(argv)
    try:
        result, code = None, 0
        if args.command == 'prepare':
            result = design.prepare_design(read(args.design), read(args.code_connect) if args.code_connect else None, args.source_root)
            reference = result['design'].get('reference_image')
            if reference:
                reference = Path(reference)
                if not reference.is_absolute(): reference = Path(args.design).resolve().parent / reference
                result['design']['reference_sha256'] = imaging.digest(reference)
            write(args.output, result, [args.design, args.code_connect, reference])
        elif args.command == 'normalize':
            result = runtime.normalize_runtime(read(args.input)); write(args.output, result, [args.input])
        elif args.command == 'collect':
            result = runtime.normalize_runtime(runtime.collect_adb(args.serial, args.package, args.build_id, args.state, args.output_dir, args.adb, read(args.metadata)))
            output = Path(result['image']).parent / 'runtime.json'; write(output, result)
            result = {'runtime': str(output), 'build_binding': result['build_binding']}
        elif args.command == 'align':
            r, d = runtime.normalize_runtime(read(args.runtime)), design.prepare_design(read(args.design))
            image = Path(r['image']); image = image if image.is_absolute() else Path(args.runtime).resolve().parent / image
            reference = d['design'].get('reference_image')
            if reference:
                reference = Path(reference)
                if not reference.is_absolute(): reference = Path(args.design).resolve().parent / reference
            imaging.ensure_distinct([args.output, args.registration], [p for p in (args.design, args.runtime, image, reference) if p])
            result = imaging.align_image(image, r, d, args.output)
            write(args.registration, result, [args.design, args.runtime, image, args.output])
        elif args.command == 'compare':
            imaging.ensure_distinct([Path(args.output_dir) / name for name in ('reference.png', 'actual.png', 'diff.png', 'pixels.json')], [p for p in (args.reference, args.actual, args.registration) if p])
            registration = read(args.registration) if args.registration else None
            if registration and (registration.get('image_sha256') != imaging.digest(args.actual) or Path(registration['image']).resolve() != Path(args.actual).resolve()):
                raise ValueError('Registration image path/hash differs from the actual image')
            result = imaging.compare_png(args.reference, args.actual, args.output_dir, args.channel_tolerance, args.max_diff_ratio, args.background)
            if registration:
                result.update({k: registration[k] for k in ('runtime_capture_id', 'design_revision', 'source_image_sha256')})
                write(Path(args.output_dir) / 'pixels.json', result, [args.registration])
            code = 0 if result['passed'] else 1
        elif args.command == 'assess':
            visual = read(args.visual) if args.visual else None
            if visual:
                problem = imaging.verify_comparison(visual, Path(args.visual).resolve().parent)
                if problem: visual['evidence_error'] = problem
            result = assessment.evaluate(design.prepare_design(read(args.design)), [runtime.normalize_runtime(read(path)) for path in args.runtime], read(args.tag_map), read(args.trace) if args.trace else None, visual)
            write(args.output, result, [args.design, args.tag_map, args.trace, args.visual, *args.runtime])
            code = {'pass': 0, 'fail': 1, 'inconclusive': 3}[result['overall_status']]
        elif args.command == 'report':
            imaging.ensure_distinct([args.output], [args.assessment])
            output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(reporting.render_markdown(read(args.assessment)))
            result = {'report': str(output)}
        elif args.command == 'instrument':
            result = instrumentation.apply_patches(args.project_root, read(args.plan)['patches'], args.session)
        elif args.command == 'cleanup':
            result = instrumentation.cleanup(args.session); code = 0 if result['status'] == 'clean' else 3
        elif args.command == 'demo':
            from uxlib.demo import run
            result = run(args.output_dir)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return code
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Input/collection error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
