"""Synthetic end-to-end contract example; deliberately never a live UX approval."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
from . import assessment, design, imaging, reporting, runtime


def run(output_dir):
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError('Demo requires an empty output directory; existing evidence is preserved')
    def write(name, value):
        (out / name).write_text(json.dumps(value, indent=2) + '\n')
    (out / 'app').mkdir()
    (out / 'app' / 'AppButton.kt').write_text('// Synthetic source receipt, not a compiled Compose implementation.\n')
    (out / 'figma-context.json').write_text('{"origin":"fixture","description":"Synthetic design; no Figma MCP call"}\n')
    (out / 'trace.log').write_text('SYNTHETIC: valid -> click ci.save -> success\n')
    reference = Image.new('RGB', (360, 592), '#eeeeee')
    ImageDraw.Draw(reference).rectangle((24, 124, 119, 163), fill='#999999')
    reference.save(out / 'reference.png')
    raw = Image.new('RGB', (1080, 1920), '#111111')
    # Render at physical density so align uses an explicit uniform scale.
    raw.paste(reference.resize((1080, 1776), Image.Resampling.NEAREST), (0, 72))
    raw.save(out / 'screen.png')
    contract = {'schema_version': 1, 'design': {'origin': 'fixture', 'file_key': 'synthetic', 'node_id': '10:1', 'revision': 'fixture-r1', 'reference_image': 'reference.png', 'reference_scale': 1, 'evidence': ['figma-context.json']},
        'viewport': {'width_dp': 360, 'height_dp': 592, 'figma_units_per_dp': 1}, 'scope': ['visual', 'structure', 'behavior'],
        'environment': {'density': 3, 'font_scale': 1, 'locale': 'en-US', 'theme': 'light', 'rotation': 0},
        'nodes': [{'id': '10:2', 'name': 'Save', 'bounds_dp': [24, 124, 120, 164]}],
        'requirements': [{'id': 'save.bounds', 'kind': 'bounds', 'node_id': '10:2', 'state': 'empty', 'tolerance_dp': 0},
                         {'id': 'save.disabled', 'kind': 'property', 'node_id': '10:2', 'state': 'empty', 'property': 'enabled', 'expected': False},
                         {'id': 'save.parent', 'kind': 'parent', 'node_id': '10:2', 'state': 'empty', 'parent_tag': 'ci.form', 'hierarchy_kind': 'unmerged_semantics'},
                         {'id': 'save.mapping', 'kind': 'code_connect', 'node_id': '10:2', 'state': 'empty'},
                         {'id': 'save.pixels', 'kind': 'pixels', 'node_id': '10:2', 'state': 'empty'},
                         {'id': 'save.flow', 'kind': 'transition', 'node_id': '10:2', 'from_state': 'valid', 'action': 'click', 'action_tag': 'ci.save', 'to_state': 'success', 'postcondition': {'tag': 'ci.confirmation', 'property': 'text', 'expected': 'Saved'}}]}
    contract['design']['reference_sha256'] = imaging.digest(out / 'reference.png')
    mappings = {'schema_version': 1, 'mappings': [{'node_id': '10:2', 'framework': 'compose', 'component': 'AppButton', 'source': 'app/AppButton.kt'}]}
    prepared = design.prepare_design(contract, mappings, out)
    tags = {'schema_version': 1, 'build_id': 'synthetic-build', 'bindings': [{'node_id': '10:2', 'tag': 'ci.save', 'composable': 'AppButton', 'source': 'app/AppButton.kt'}]}
    captures = []
    for state in ('empty', 'valid', 'success'):
        capture = {'schema_version': 1, 'origin': 'fixture', 'build_id': 'synthetic-build', 'build_binding': 'declared', 'capture_id': state + '-1', 'state': state, 'hierarchy_kind': 'unmerged_semantics',
            'device': {'density': 3, 'font_scale': 1, 'locale': 'en-US', 'theme': 'light', 'rotation': 0, 'api': 35, 'fingerprint': 'synthetic-only'},
            'viewport_px': [1080, 1920], 'insets_px': {'left': 0, 'top': 72, 'right': 0, 'bottom': 72}, 'image': str(out / 'screen.png'), 'image_sha256': imaging.digest(out / 'screen.png'), 'evidence': ['SYNTHETIC-semantics.json'],
            'nodes': [{'id': 'n0', 'parent_id': None, 'tag': 'ci.form', 'bounds_px': [0, 72, 1080, 1848]},
                      {'id': 'n1', 'parent_id': 'n0', 'tag': 'ci.save', 'bounds_px': [72, 444, 360, 564], 'text': 'Save', 'enabled': state != 'empty', 'clickable': True}]}
        if state == 'success':
            capture['nodes'].append({'id': 'n2', 'parent_id': 'n0', 'tag': 'ci.confirmation', 'bounds_px': [72, 600, 360, 720], 'text': 'Saved'})
        capture = runtime.normalize_runtime(capture)
        write(state + '.json', capture); captures.append(capture)
    write('SYNTHETIC-semantics.json', {'note': 'All captures and hierarchy observations are synthetic tool fixtures', 'captures': captures})
    registration = imaging.align_image(out / 'screen.png', captures[0], prepared, out / 'aligned.png')
    # Filtering at downsampled edges is expected; tolerance here is a fixture setting, not a product recommendation.
    visual = imaging.compare_png(out / 'reference.png', out / 'aligned.png', out / 'comparison', channel_tolerance=20)
    visual.update(runtime_capture_id=registration['runtime_capture_id'], design_revision=registration['design_revision'], source_image_sha256=registration['source_image_sha256'])
    trace = {'schema_version': 1, 'build_id': 'synthetic-build', 'steps': [{'from_capture': 'valid-1', 'to_capture': 'success-1', 'action': 'click', 'tag': 'ci.save', 'status': 'passed', 'evidence': ['trace.log']}]}
    report = assessment.evaluate(prepared, captures, tags, trace, visual)
    for name, value in [('design.json', contract), ('code-connect.json', mappings), ('prepared.json', prepared), ('tags.json', tags), ('trace.json', trace), ('registration.json', registration), ('visual.json', visual), ('assessment.json', report)]:
        write(name, value)
    (out / 'report.md').write_text(reporting.render_markdown(report))
    if report['summary']['pass'] != 6 or report['summary']['fail'] or report['overall_status'] != 'inconclusive':
        raise ValueError('Synthetic demo did not produce its expected six checks and fixture-only verdict')
    return {'status': 'tool_demo_passed', 'validation_scope': 'fixture_only', 'report': str(out / 'report.md')}
