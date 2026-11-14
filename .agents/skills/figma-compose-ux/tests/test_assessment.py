import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


def evidence():
    design = {'schema_version': 1, 'design': {'origin': 'figma_export', 'file_key': 'demo', 'node_id': '10:1', 'revision': 'r1', 'evidence': ['figma.json']},
              'viewport': {'width_dp': 360, 'height_dp': 592, 'figma_units_per_dp': 1}, 'scope': ['structure', 'behavior'],
              'nodes': [{'id': '10:2', 'bounds_dp': [24, 124, 120, 164]}],
              'requirements': [
                  {'id': 'bounds', 'kind': 'bounds', 'node_id': '10:2', 'state': 'empty', 'tolerance_dp': 0},
                  {'id': 'disabled', 'kind': 'property', 'node_id': '10:2', 'state': 'empty', 'property': 'enabled', 'expected': False}]}
    capture = {'schema_version': 1, 'build_id': 'abc', 'build_binding': 'verified', 'capture_id': 'empty-1', 'origin': 'device', 'state': 'empty',
               'hierarchy_kind': 'accessibility', 'device': {'density': 3, 'font_scale': 1}, 'content_size_dp': [360, 592], 'evidence': ['ui.xml'],
               'nodes': [{'id': 'n0', 'parent_id': None, 'tag': 'ci.save', 'bounds_dp': [24, 124, 120, 164], 'enabled': False}]}
    tags = {'schema_version': 1, 'build_id': 'abc', 'bindings': [{'node_id': '10:2', 'tag': 'ci.save', 'composable': 'AppButton', 'source': 'AppButton.kt'}]}
    return design, [capture], tags


class AssessmentTest(unittest.TestCase):
    def setUp(self):
        module = Path(__file__).resolve().parents[1] / 'scripts/uxlib/assessment.py'
        self.assertTrue(module.exists(), 'assessment implementation is missing')
        from uxlib.assessment import evaluate
        self.evaluate = evaluate

    def test_geometry_and_disabled_state_have_evidence_but_missing_flow_is_unknown(self):
        d, r, t = evidence()
        result = self.evaluate(d, r, t)
        self.assertEqual([f['status'] for f in result['findings']], ['pass', 'pass'])
        self.assertEqual(result['overall_status'], 'inconclusive')
        self.assertIn('behavior', ' '.join(result['limitations']))
        self.assertNotIn('ux_score', result)

    def test_wrong_geometry_fails(self):
        d, r, t = evidence()
        r[0]['nodes'][0]['bounds_dp'][0] += 8
        self.assertEqual(self.evaluate(d, r, t)['findings'][0]['status'], 'fail')

    def test_stale_tag_map_never_establishes_node_identity(self):
        d, r, t = evidence()
        t['build_id'] = 'older'
        result = self.evaluate(d, r, t)
        self.assertTrue(all(f['status'] == 'inconclusive' for f in result['findings']))

    def test_accessibility_parent_is_not_composable_parent(self):
        d, r, t = evidence()
        d['requirements'] = [{'id': 'parent', 'kind': 'parent', 'node_id': '10:2', 'state': 'empty', 'parent_tag': 'ci.form', 'hierarchy_kind': 'unmerged_semantics'}]
        self.assertEqual(self.evaluate(d, r, t)['findings'][0]['status'], 'inconclusive')

    def test_missing_boolean_is_unknown_not_false(self):
        d, r, t = evidence()
        del r[0]['nodes'][0]['enabled']
        self.assertEqual(self.evaluate(d, r, t)['findings'][1]['status'], 'inconclusive')

    def test_react_mapping_cannot_prove_compose_reuse(self):
        d, r, t = evidence()
        d['requirements'] = [{'id': 'map', 'kind': 'code_connect', 'node_id': '10:2', 'state': 'empty'}]
        d['code_connect'] = {'mappings': [{'node_id': '10:2', 'framework': 'react', 'component': 'AppButton', 'source': 'Button.tsx'}]}
        self.assertEqual(self.evaluate(d, r, t)['findings'][0]['status'], 'inconclusive')

    def test_fixture_never_becomes_live_ux_approval(self):
        d, r, t = evidence()
        d['scope'] = ['structure']; d['design']['origin'] = 'fixture'
        result = self.evaluate(d, r, t)
        self.assertEqual(result['overall_status'], 'inconclusive')
        self.assertEqual(result['validation_scope'], 'fixture_only')

    def test_claimed_pass_trace_requires_captures_and_postcondition(self):
        d, r, t = evidence()
        d['requirements'] = [{'id': 'flow', 'kind': 'transition', 'node_id': '10:2', 'from_state': 'valid', 'action': 'click', 'action_tag': 'ci.save', 'to_state': 'success',
                              'postcondition': {'tag': 'ci.confirmation', 'property': 'text', 'expected': 'Saved'}}]
        trace = {'schema_version': 1, 'build_id': 'abc', 'steps': [{'from_capture': 'missing', 'to_capture': 'also-missing', 'action': 'click', 'tag': 'ci.save', 'status': 'passed', 'evidence': ['log']}]}
        self.assertEqual(self.evaluate(d, r, t, trace)['findings'][0]['status'], 'inconclusive')

    def test_observed_transition_passes_and_wrong_postcondition_fails(self):
        d, r, t = evidence()
        d['scope'] = ['behavior']
        d['requirements'] = [{'id': 'flow', 'kind': 'transition', 'node_id': '10:2', 'from_state': 'valid', 'action': 'click', 'action_tag': 'ci.save', 'to_state': 'success',
                              'postcondition': {'tag': 'ci.confirmation', 'property': 'text', 'expected': 'Saved'}}]
        before = copy.deepcopy(r[0]); before.update(state='valid', capture_id='valid-1'); before['nodes'][0]['enabled'] = True
        after = copy.deepcopy(r[0]); after.update(state='success', capture_id='success-1'); after['nodes'] = [{'id': 'n0', 'parent_id': None, 'tag': 'ci.confirmation', 'text': 'Saved'}]
        trace = {'schema_version': 1, 'build_id': 'abc', 'steps': [{'from_capture': 'valid-1', 'to_capture': 'success-1', 'action': 'click', 'tag': 'ci.save', 'status': 'passed', 'evidence': ['trace.log']}]}
        self.assertEqual(self.evaluate(d, [before, after], t, trace)['overall_status'], 'pass')
        after['nodes'][0]['text'] = 'Error'
        self.assertEqual(self.evaluate(d, [before, after], t, trace)['overall_status'], 'fail')

    def test_no_requirements_is_not_a_zero_test_pass(self):
        d, r, t = evidence(); d['requirements'] = []
        self.assertEqual(self.evaluate(d, r, t)['overall_status'], 'inconclusive')

    def test_font_scale_mismatch_is_incomparable_not_a_layout_failure(self):
        d, r, t = evidence(); d['environment'] = {'font_scale': 1}; r[0]['device']['font_scale'] = 1.5
        r[0]['nodes'][0]['bounds_dp'][0] += 8
        result = self.evaluate(d, r, t)
        self.assertEqual(result['overall_status'], 'inconclusive')
        self.assertTrue(all(f['status'] == 'inconclusive' for f in result['findings']))

    def test_unknown_requirement_kind_is_inconclusive(self):
        d, r, t = evidence(); d['requirements'][0]['kind'] = 'mind_reading'
        self.assertEqual(self.evaluate(d, r, t)['findings'][0]['status'], 'inconclusive')


    def test_visual_needs_reference_and_raw_capture_hashes_and_state(self):
        d, r, t = evidence()
        d['scope'] = ['visual']; d['design']['reference_sha256'] = 'a' * 64
        d['requirements'] = [{'id': 'pixels', 'kind': 'pixels', 'node_id': '10:2', 'state': 'empty'}]
        r[0]['image_sha256'] = 'b' * 64
        v = {'runtime_capture_id': 'empty-1', 'design_revision': 'r1', 'passed': True,
             'reference_sha256': 'a' * 64, 'source_image_sha256': 'b' * 64,
             'method': 'pixel_difference', 'reference': 'ref.png', 'actual': 'actual.png', 'diff': 'diff.png',
             'reference_artifact_sha256': 'a' * 64, 'actual_artifact_sha256': 'b' * 64, 'diff_sha256': 'c' * 64,
             'actual_sha256': 'b' * 64, 'width': 360, 'height': 592, 'changed_pixels': 0, 'diff_ratio': 0,
             'channel_tolerance': 0, 'max_diff_ratio': 0}
        self.assertEqual(self.evaluate(d, r, t, visual=v)['findings'][0]['status'], 'pass')
        for key in ('reference_sha256', 'source_image_sha256'):
            wrong = dict(v); wrong[key] = 'c' * 64
            self.assertEqual(self.evaluate(d, r, t, visual=wrong)['findings'][0]['status'], 'inconclusive')
        r[0]['state'] = 'other'
        self.assertEqual(self.evaluate(d, r, t, visual=v)['findings'][0]['status'], 'inconclusive')

    def test_malformed_tag_binding_raises_value_error(self):
        d, r, t = evidence(); t['bindings'] = ['bad']
        with self.assertRaises(ValueError): self.evaluate(d, r, t)


    def test_passed_flag_alone_and_inconsistent_visual_metrics_are_inconclusive(self):
        d, r, t = evidence(); d['scope'] = ['visual']; d['design']['reference_sha256'] = 'a' * 64
        d['requirements'] = [{'id': 'pixels', 'kind': 'pixels', 'node_id': '10:2', 'state': 'empty'}]
        r[0]['image_sha256'] = 'b' * 64
        v = {'runtime_capture_id': 'empty-1', 'design_revision': 'r1', 'passed': True, 'reference_sha256': 'a' * 64, 'source_image_sha256': 'b' * 64}
        self.assertEqual(self.evaluate(d, r, t, visual=v)['findings'][0]['status'], 'inconclusive')
        v.update(method='pixel_difference', reference='ref.png', actual='actual.png', diff='diff.png', reference_artifact_sha256='a'*64, actual_artifact_sha256='b'*64, diff_sha256='c'*64, actual_sha256='b'*64, width=10, height=10, changed_pixels=80, diff_ratio=0.8, channel_tolerance=0, max_diff_ratio=0)
        self.assertEqual(self.evaluate(d, r, t, visual=v)['findings'][0]['status'], 'inconclusive')


    def test_interaction_trace_requires_supported_schema_and_observed_action_status(self):
        d, r, t = evidence()
        with self.assertRaises(ValueError):
            self.evaluate(d, r, t, {'schema_version': 99, 'build_id': 'abc', 'steps': []})
        with self.assertRaises(ValueError):
            self.evaluate(d, r, t, {'schema_version': 1, 'build_id': 'abc', 'steps': ['claimed pass']})
        d['environment'] = []
        with self.assertRaises(ValueError): self.evaluate(d, r, t)


if __name__ == '__main__': unittest.main()
