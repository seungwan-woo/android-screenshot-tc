"""Assess declared intent checks against attributable observations, never an opaque UX score."""
import math
from .imaging import comparison_problem


def evaluate(design, runtimes, tag_map, trace=None, visual=None):
    if not isinstance(runtimes, list) or not runtimes:
        raise ValueError('At least one normalized runtime capture is required')
    if type(tag_map.get('schema_version')) is not int or tag_map['schema_version'] != 1 or not isinstance(tag_map.get('bindings'), list):
        raise ValueError('Tag map requires schema_version=1 and bindings')
    if trace is not None:
        if type(trace.get('schema_version')) is not int or trace['schema_version'] != 1 or not isinstance(trace.get('steps'), list):
            raise ValueError('Trace requires schema_version=1 and steps')
        for step in trace['steps']:
            if not isinstance(step, dict):
                raise ValueError('Trace steps must be objects')
            if 'evidence' in step and (not isinstance(step['evidence'], list) or any(not isinstance(p, str) or not p for p in step['evidence'])):
                raise ValueError('Trace evidence must be a list of nonempty artifact references')
    if not isinstance(design.get('environment', {}), dict):
        raise ValueError('Design environment must be an object')
    bindings = tag_map['bindings']
    if any(not isinstance(b, dict) for b in bindings):
        raise ValueError('Tag map bindings must be objects')
    for key in ('node_id', 'tag'):
        values = [b.get(key) for b in bindings]
        if any(not isinstance(v, str) or not v for v in values) or len(values) != len(set(values)):
            raise ValueError(f'Tag map {key} values must be nonempty and unique')
    captures = {}
    for runtime in runtimes:
        cid = runtime.get('capture_id')
        if not cid or cid in captures:
            raise ValueError('Runtime capture_id values must be nonempty and unique')
        captures[cid] = runtime
    node_specs = {n['id']: n for n in design.get('nodes', [])}
    binding_by_node = {b['node_id']: b for b in bindings}
    limits, findings = [], []
    fixture = design.get('design', {}).get('origin') == 'fixture' or any(r.get('origin') == 'fixture' for r in runtimes)
    if fixture:
        limits.append('Synthetic fixture evidence validates the tooling, not a live product UX implementation.')
    if any(r.get('build_binding') != 'verified' for r in runtimes):
        limits.append('Installed APK/build identity has not been independently bound for every capture.')
    requirements = design.get('requirements', [])
    if not requirements:
        limits.append('No declared requirements were evaluated; this is not a zero-test pass.')
    expected_env = design.get('environment', {})

    def environment_problem(runtime):
        differences = [k for k, v in expected_env.items() if runtime.get('device', {}).get(k) != v]
        return 'Incomparable capture environment: ' + ', '.join(differences) if differences else None

    def lookup(req):
        binding = binding_by_node.get(req.get('node_id'))
        if not binding:
            return None, None, None, 'No explicit design-node to runtime-tag binding'
        matches = [r for r in runtimes if r.get('state') == req.get('state')]
        if len(matches) != 1:
            return binding, None, None, 'Missing or ambiguous capture for the required state'
        runtime = matches[0]
        nodes = [n for n in runtime.get('nodes', []) if n.get('tag') == binding['tag']]
        node = nodes[0] if len(nodes) == 1 else None
        if runtime.get('build_id') != tag_map.get('build_id'):
            return binding, runtime, node, 'Tag map and runtime build IDs differ'
        if environment_problem(runtime):
            return binding, runtime, node, environment_problem(runtime)
        if not node:
            return binding, runtime, None, 'Required tag is absent or ambiguous; accessibility absence alone is not a source-node deletion'
        return binding, runtime, node, None

    def transition(req):
        if not trace or trace.get('build_id') != tag_map.get('build_id'):
            return 'inconclusive', None, 'Missing or build-mismatched interaction trace', []
        candidates = []
        for step in trace.get('steps', []):
            before, after = captures.get(step.get('from_capture')), captures.get(step.get('to_capture'))
            if before and after and before.get('state') == req.get('from_state') and after.get('state') == req.get('to_state') and step.get('action') == req.get('action') and step.get('tag') == req.get('action_tag'):
                candidates.append((step, before, after))
        if len(candidates) != 1:
            return 'inconclusive', None, 'A transition needs matching before/after captures, not only a claimed passed action', []
        step, before, after = candidates[0]
        if step.get('status') not in ('passed', 'failed'):
            return 'inconclusive', None, 'Action result was not observed', step.get('evidence', [])
        evidence = step.get('evidence', []) + before.get('evidence', []) + after.get('evidence', [])
        if not step.get('evidence') or any(r.get('build_id') != tag_map.get('build_id') or environment_problem(r) for r in (before, after)):
            return 'inconclusive', None, 'Trace evidence or comparable build/environment is missing', evidence
        actions = [n for n in before.get('nodes', []) if n.get('tag') == req.get('action_tag')]
        post = req.get('postcondition', {})
        matches = [n for n in after.get('nodes', []) if n.get('tag') == post.get('tag')]
        prop = post.get('property')
        if len(actions) != 1 or len(matches) != 1 or not prop or prop not in matches[0] or 'expected' not in post:
            return 'inconclusive', None, 'Missing action target or observable postcondition', evidence
        if req.get('action') == 'click' and actions[0].get('enabled') is not True:
            return 'inconclusive', None, 'Click target was not observed enabled before the action', evidence
        observed = matches[0][prop]
        passed = step.get('status') == 'passed' and observed == post['expected']
        return ('pass' if passed else 'fail'), observed, 'Observed action and postcondition' if passed else 'Observed postcondition/action does not meet the intent', evidence

    for req in requirements:
        item = {'id': req['id'], 'kind': req.get('kind'), 'node_id': req.get('node_id'),
                'status': 'inconclusive', 'expected': req.get('expected'), 'observed': None,
                'reason': '', 'evidence': list(design.get('design', {}).get('evidence', []))}
        if req.get('applicable') is False and req.get('reason'):
            item.update(status='not_applicable', reason=req['reason']); findings.append(item); continue
        kind = req.get('kind')
        if kind == 'transition':
            status, observed, reason, refs = transition(req)
            item.update(status=status, observed=observed, expected=req.get('postcondition'), reason=reason)
            item['evidence'] += refs; findings.append(item); continue
        if kind == 'pixels':
            runtime = captures.get((visual or {}).get('runtime_capture_id'))
            if not visual or not runtime or runtime.get('state') != req.get('state') or visual.get('design_revision') != design['design'].get('revision') or not design['design'].get('reference_sha256') or visual.get('reference_sha256') != design['design']['reference_sha256'] or not runtime.get('image_sha256') or visual.get('source_image_sha256') != runtime['image_sha256'] or runtime.get('build_id') != tag_map.get('build_id') or environment_problem(runtime):
                item['reason'] = 'Pixel result needs the selected design revision, reference hash, state and raw capture hash'
            elif comparison_problem(visual):
                item['reason'] = comparison_problem(visual)
            else:
                item.update(status='pass' if visual.get('passed') is True else 'fail', expected={'channel_tolerance': visual.get('channel_tolerance'), 'max_diff_ratio': visual.get('max_diff_ratio')}, observed={'changed_pixels': visual.get('changed_pixels'), 'diff_ratio': visual.get('diff_ratio')}, reason='Visual difference is one check, not a UX percentage')
                item['evidence'] += [visual[k] for k in ('reference', 'actual', 'diff') if visual.get(k)]
            findings.append(item); continue
        binding, runtime, node, problem = lookup(req)
        if binding:
            item.update(runtime_tag=binding['tag'], source=binding.get('source'), composable=binding.get('composable'), binding_status='stale_build' if runtime and runtime.get('build_id') != tag_map.get('build_id') else 'matched_build' if runtime else 'unresolved')
        if runtime:
            item['evidence'] += runtime.get('evidence', [])
            item['capture_id'] = runtime.get('capture_id')
        if problem:
            item.update(reason=problem, observed=node); findings.append(item); continue
        if kind == 'bounds':
            expected = node_specs.get(req.get('node_id'), {}).get('bounds_dp'); actual = node.get('bounds_dp')
            tolerance = req.get('tolerance_dp', 0)
            if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
                raise ValueError('Bounds tolerance must be finite and nonnegative')
            if expected is None or actual is None:
                item['reason'] = 'Bounds need normalized content-dp coordinates on both sides'
            else:
                delta = [a - b for a, b in zip(actual, expected)]
                item.update(status='pass' if all(abs(v) <= tolerance for v in delta) else 'fail', expected=expected, observed=actual, delta_dp=delta, reason='Compared normalized bounds with explicit dp tolerance')
        elif kind == 'property':
            prop = req.get('property')
            if prop not in node or node[prop] is None or 'expected' not in req:
                item['reason'] = f'Runtime does not expose {prop}; absence is not a matching value'
            else:
                item.update(status='pass' if node[prop] == req['expected'] else 'fail', observed=node[prop], reason='Compared an observed runtime property')
        elif kind == 'parent':
            if req.get('hierarchy_kind') != runtime.get('hierarchy_kind') or runtime.get('hierarchy_kind') not in ('accessibility', 'unmerged_semantics'):
                item['reason'] = 'Hierarchy kinds are not comparable; accessibility/Semantics is not the complete composition tree'
            else:
                parent = next((n for n in runtime['nodes'] if n['id'] == node.get('parent_id')), None)
                if parent is None or not parent.get('tag'):
                    item['reason'] = 'The required parent is not exposed in this hierarchy'
                else:
                    item.update(status='pass' if parent['tag'] == req.get('parent_tag') else 'fail', expected=req.get('parent_tag'), observed=parent['tag'], reason='Compared parents within the explicitly selected hierarchy kind')
        elif kind == 'code_connect':
            mappings = [m for m in design.get('code_connect', {}).get('mappings', []) if isinstance(m, dict) and m.get('node_id') == req.get('node_id')]
            if len(mappings) != 1 or mappings[0].get('framework') not in ('compose', 'jetpack-compose') or mappings[0].get('supported') is False:
                item['reason'] = 'Missing, ambiguous or non-Compose Code Connect mapping'
            elif not mappings[0].get('source_exists') or not mappings[0].get('source_sha256'):
                item['reason'] = 'Mapped source has not been resolved and hashed in this project'
            else:
                mapping = mappings[0]
                actual = {'component': binding.get('composable'), 'source': binding.get('source')}
                expected = {k: mapping[k] for k in ('component', 'source')}
                item.update(status='pass' if actual == expected else 'fail', expected=expected, observed=actual, reason='Mapping consistency only; component execution/reuse still requires source/build review')
        else:
            item['reason'] = f'Unsupported requirement kind {kind}; add a supported check or explicit review evidence'
        findings.append(item)
    scope_kinds = {'visual': {'pixels'}, 'structure': {'bounds', 'parent', 'code_connect', 'property'}, 'behavior': {'transition'}}
    for scope in design.get('scope', []):
        if not any(r.get('kind') in scope_kinds.get(scope, set()) for r in requirements):
            limits.append(f'Requested {scope} scope has no declared check/evidence.')
    counts = {state: sum(f['status'] == state for f in findings) for state in ('pass', 'fail', 'inconclusive', 'not_applicable')}
    total = len(findings) - counts['not_applicable']; observed = counts['pass'] + counts['fail']
    status = 'fail' if counts['fail'] else 'inconclusive' if limits or counts['inconclusive'] or not total else 'pass'
    return {'schema_version': 1, 'overall_status': status, 'verdict_scope': 'declared_requirements',
            'validation_scope': 'fixture_only' if fixture else 'provided_evidence', 'summary': counts,
            'coverage': {'evaluated': observed, 'total': total, 'ratio': observed / total if total else 0},
            'provenance': {'design': design.get('design'), 'tag_map': tag_map, 'captures': [{'capture_id': r.get('capture_id'), 'build_id': r.get('build_id'), 'origin': r.get('origin'), 'build_binding': r.get('build_binding'), 'evidence': r.get('evidence', [])} for r in runtimes]},
            'findings': findings, 'design_issues': design.get('issues', []), 'limitations': limits}
