"""Offline validation and source provenance tests for design contracts."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from uxlib import design


def contract():
    return {
        "schema_version": 1,
        "design": {
            "origin": "fixture", "file_key": "demo", "node_id": "10:1",
            "revision": "r1", "reference_image": "design.png",
            "reference_scale": 1, "evidence": ["figma-context.json"],
        },
        "viewport": {"width_dp": 360, "height_dp": 592, "figma_units_per_dp": 1},
        "scope": ["visual", "structure", "behavior"],
        "nodes": [{"id": "10:2", "name": "Save", "bounds_dp": [24, 124, 120, 164], "text": "Save"}],
        "requirements": [{"id": "save.bounds", "kind": "bounds", "node_id": "10:2", "state": "empty", "tolerance_dp": 0}],
    }


def links(framework="compose", source="app/AppButton.kt"):
    return {"schema_version": 1, "mappings": [{
        "node_id": "10:2", "framework": framework,
        "component": "AppButton", "source": source,
    }]}


class _PrepareMixin:
    def prepare(self, *args, **kwargs):
        return design.prepare_design(*args, **kwargs)


class PrepareDesignTests(_PrepareMixin, unittest.TestCase):
    def test_deep_copies_contract_and_preserves_provenance(self):
        original = contract()
        original["design"]["receipt"] = {"connector": "figma_mcp", "arguments": ["10:1"]}
        snapshot = copy.deepcopy(original)
        prepared = self.prepare(original)
        self.assertEqual(prepared["design"], snapshot["design"])
        self.assertEqual(prepared["nodes"], snapshot["nodes"])
        self.assertEqual(prepared["issues"], [])
        self.assertEqual(prepared["code_connect"], {"schema_version": 1, "mappings": []})
        prepared["design"]["receipt"]["arguments"].append("changed")
        prepared["nodes"][0]["bounds_dp"][0] = 0
        self.assertEqual(original, snapshot)
        json.dumps(prepared, allow_nan=False)

    def test_dp_bounds_are_not_scaled_or_clipped(self):
        value = contract()
        value["viewport"]["figma_units_per_dp"] = 2
        value["design"]["reference_scale"] = 3
        value["nodes"][0]["bounds_dp"] = [-4, 124.5, 400, 164.5]
        prepared = self.prepare(value)
        self.assertEqual(prepared["nodes"][0]["bounds_dp"], [-4, 124.5, 400, 164.5])
        self.assertEqual(prepared["viewport"]["width_dp"], 360)

    def test_nonvisual_contract_can_omit_image_metadata(self):
        value = contract()
        value["scope"] = ["structure", "behavior"]
        del value["design"]["reference_image"]
        del value["design"]["reference_scale"]
        try:
            prepared = self.prepare(value)
        except ValueError as error:
            self.fail(f"nonvisual design must accept omitted image metadata: {error}")
        self.assertEqual(prepared["design"], value["design"])

    def test_visual_scope_or_pixels_requirement_requires_image_and_scale(self):
        for visual_scope in (True, False):
            for omitted in ("reference_image", "reference_scale"):
                with self.subTest(visual_scope=visual_scope, omitted=omitted):
                    value = contract()
                    if not visual_scope:
                        value["scope"] = ["structure"]
                        value["requirements"][0]["kind"] = "pixels"
                    del value["design"][omitted]
                    with self.assertRaises(ValueError):
                        self.prepare(value)

    def test_all_documented_origins_are_accepted(self):
        for origin in ("fixture", "figma_mcp", "figma_export"):
            with self.subTest(origin=origin):
                value = contract()
                value["design"]["origin"] = origin
                self.assertEqual(self.prepare(value)["design"]["origin"], origin)

    def test_schema_provenance_and_container_types_are_required(self):
        mutations = [
            ([], None), ({}, None), (None, None),
            (("schema_version",), 2), (("schema_version",), True),
            (("design",), []), (("design", "origin"), "figma"),
            (("design", "file_key"), ""), (("design", "node_id"), "  "),
            (("design", "revision"), None), (("design", "reference_image"), ""),
            (("design", "evidence"), "context.json"), (("design", "evidence"), [""]),
            (("scope",), "visual"), (("scope",), [""]),
            (("nodes",), {}), (("requirements",), {}), (("viewport",), []),
        ]
        for path, replacement in mutations:
            with self.subTest(path=path, replacement=replacement):
                if not isinstance(path, tuple):
                    value = path
                else:
                    value = contract()
                    target = value
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = replacement
                with self.assertRaises(ValueError):
                    self.prepare(value)
        for section, field in ((None, "schema_version"), (None, "design"),
                               (None, "viewport"), (None, "scope"),
                               (None, "nodes"), (None, "requirements"),
                               ("design", "file_key"), ("design", "evidence"),
                               ("viewport", "figma_units_per_dp")):
            with self.subTest(missing=(section, field)):
                value = contract()
                del (value if section is None else value[section])[field]
                with self.assertRaises(ValueError):
                    self.prepare(value)

    def test_viewport_and_scales_reject_nonfinite_nonpositive_and_booleans(self):
        fields = (("viewport", "width_dp"), ("viewport", "height_dp"),
                  ("viewport", "figma_units_per_dp"), ("design", "reference_scale"))
        for section, field in fields:
            for bad in (0, -1, float("nan"), float("inf"), True, "2", None):
                with self.subTest(field=field, bad=bad):
                    value = contract()
                    value[section][field] = bad
                    with self.assertRaises(ValueError):
                        self.prepare(value)

    def test_bounds_require_four_finite_ordered_coordinates(self):
        for bounds in ([1, 2, 3], [1, 2, 3, 4, 5], [3, 2, 1, 4],
                       [1, 4, 3, 2], [1, 2, float("nan"), 4],
                       [1, 2, 3, float("inf")], [False, 2, 3, 4],
                       ["1", 2, 3, 4], "1,2,3,4", None):
            with self.subTest(bounds=bounds):
                value = contract()
                value["nodes"][0]["bounds_dp"] = bounds
                with self.assertRaises(ValueError):
                    self.prepare(value)

    def test_node_ids_bounds_and_unique_requirement_ids_are_required(self):
        variants = []
        for key in ("id", "bounds_dp"):
            value = contract()
            del value["nodes"][0][key]
            variants.append(value)
        for field in ("id", "kind", "node_id"):
            value = contract()
            del value["requirements"][0][field]
            variants.append(value)
        for group in ("nodes", "requirements"):
            value = contract()
            value[group].append(copy.deepcopy(value[group][0]))
            variants.append(value)
        for group in ("nodes", "requirements"):
            value = contract()
            value[group][0]["id"] = ""
            variants.append(value)
        value = contract()
        value["requirements"][0]["node_id"] = "unknown"
        variants.append(value)
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.prepare(value)

    def test_unsupported_requirement_kind_is_retained_without_a_verdict(self):
        value = contract()
        value["requirements"][0]["kind"] = "future-spatial-intent"
        prepared = self.prepare(value)
        self.assertEqual(prepared["requirements"], value["requirements"])
        self.assertNotIn("status", prepared["requirements"][0])

    def test_requirement_tolerances_must_be_finite_nonnegative_numbers(self):
        for bad in (-1, True, "1", float("nan"), float("inf")):
            with self.subTest(tolerance=bad):
                value = contract()
                value["requirements"][0]["tolerance_dp"] = bad
                with self.assertRaises(ValueError):
                    self.prepare(value)

    def test_property_parent_and_transition_requirement_shapes_are_validated(self):
        valid = [
            {"id": "p", "kind": "property", "node_id": "10:2", "state": "empty", "property": "enabled", "expected": False},
            {"id": "h", "kind": "parent", "node_id": "10:2", "state": "empty", "parent_tag": "ci.form", "hierarchy_kind": "unmerged_semantics"},
            {"id": "t", "kind": "transition", "node_id": "10:2", "from_state": "valid", "action": "click", "action_tag": "ci.save", "to_state": "success", "postcondition": {"tag": "ci.confirmation", "property": "text", "expected": "Saved"}},
        ]
        value = contract()
        value["requirements"] = valid
        self.assertEqual(self.prepare(value)["requirements"], valid)
        for index, key in ((0, "property"), (0, "expected"), (1, "parent_tag"),
                           (1, "hierarchy_kind"), (2, "from_state"), (2, "to_state"),
                           (2, "action"), (2, "action_tag"), (2, "postcondition")):
            with self.subTest(index=index, missing=key):
                invalid = copy.deepcopy(value)
                del invalid["requirements"][index][key]
                with self.assertRaises(ValueError):
                    self.prepare(invalid)
        invalid = copy.deepcopy(value)
        del invalid["requirements"][2]["postcondition"]["expected"]
        with self.assertRaises(ValueError):
            self.prepare(invalid)

    def test_non_json_input_and_nonfinite_unknown_fields_fail(self):
        for extra in (object(), {1, 2}, float("nan")):
            with self.subTest(extra=extra):
                value = contract()
                value["extra"] = extra
                with self.assertRaises(ValueError):
                    self.prepare(value)


class CodeConnectTests(_PrepareMixin, unittest.TestCase):
    def mapping_contract(self):
        value = contract()
        value["requirements"].append({"id": "save.mapping", "kind": "code_connect", "node_id": "10:2", "state": "empty"})
        return value

    def test_missing_mapping_produces_an_issue_for_the_referenced_node(self):
        prepared = self.prepare(self.mapping_contract())
        self.assertEqual(prepared["code_connect"]["mappings"], [])
        self.assertTrue(any(issue.get("node_id") == "10:2" and issue.get("code") == "missing_mapping" for issue in prepared["issues"]))

    def test_compose_aliases_are_supported_and_preserve_raw_mapping(self):
        for framework in ("compose", "jetpack-compose"):
            with self.subTest(framework=framework):
                raw = links(framework)
                raw["mappings"][0]["url"] = "https://figma.com/design/demo?node-id=10-2"
                snapshot = copy.deepcopy(raw)
                prepared = self.prepare(self.mapping_contract(), raw)
                mapping = prepared["code_connect"]["mappings"][0]
                for key, expected in snapshot["mappings"][0].items():
                    self.assertEqual(mapping[key], expected)
                self.assertTrue(mapping["supported"])
                self.assertEqual(prepared["issues"], [])
                self.assertNotIn("source_exists", mapping)
                self.assertNotIn("source_sha256", mapping)
                mapping["component"] = "Changed"
                self.assertEqual(raw, snapshot)

    def test_embedded_mappings_survive_prepare_assess_reuse(self):
        first = self.prepare(self.mapping_contract(), links())
        snapshot = copy.deepcopy(first)
        second = self.prepare(first)
        self.assertEqual(second["code_connect"], first["code_connect"])
        self.assertEqual(second["issues"], [])
        self.assertEqual(first, snapshot)

    def test_explicit_mapping_argument_replaces_embedded_mappings(self):
        value = self.mapping_contract()
        value["code_connect"] = links("react")
        prepared = self.prepare(value, links())
        self.assertEqual(prepared["code_connect"]["mappings"][0]["framework"], "compose")
        self.assertEqual(prepared["issues"], [])

    def test_recorded_source_metadata_is_preserved_without_a_source_root(self):
        value = self.mapping_contract()
        value["code_connect"] = links()
        value["code_connect"]["mappings"][0].update(
            source_exists=True,
            source_sha256="8b3369944dd2a3fab39e32d1aeb1f763946a458ae3e6368a46432adc8f3a0860",
        )
        prepared = self.prepare(value, value["code_connect"])
        self.assertIn("source_exists", prepared["code_connect"]["mappings"][0])
        mapping = prepared["code_connect"]["mappings"][0]
        self.assertTrue(mapping["source_exists"])
        self.assertEqual(mapping["source_sha256"], value["code_connect"]["mappings"][0]["source_sha256"])

    def test_a_source_root_recomputes_recorded_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            value = self.mapping_contract()
            value["code_connect"] = links()
            value["code_connect"]["mappings"][0].update(source_exists=True, source_sha256="0" * 64)
            prepared = self.prepare(value, source_root=Path(directory))
            self.assertEqual(len(prepared["code_connect"]["mappings"]), 1)
            mapping = prepared["code_connect"]["mappings"][0]
            self.assertFalse(mapping["source_exists"])
            self.assertNotIn("source_sha256", mapping)
            self.assertTrue(any(issue["code"] == "source_missing" for issue in prepared["issues"]))
            self.assertTrue(value["code_connect"]["mappings"][0]["source_exists"])

    def test_react_mapping_is_not_guessed_from_its_component_name(self):
        prepared = self.prepare(self.mapping_contract(), links("react"))
        mapping = prepared["code_connect"]["mappings"][0]
        self.assertEqual(mapping["framework"], "react")
        self.assertFalse(mapping["supported"])
        self.assertTrue(any(issue["code"] == "incompatible_framework" for issue in prepared["issues"]))

    def test_absent_component_source_or_node_reference_stays_unresolved(self):
        for field in ("node_id", "component", "source"):
            with self.subTest(field=field):
                raw = links()
                del raw["mappings"][0][field]
                prepared = self.prepare(self.mapping_contract(), raw)
                self.assertFalse(prepared["code_connect"]["mappings"][0]["supported"])
                self.assertTrue(prepared["issues"])

    def test_malformed_code_connect_is_an_explicit_partial_result(self):
        for raw in ({"schema_version": 2, "mappings": []}, {"schema_version": True, "mappings": []},
                    {"schema_version": 1, "mappings": {}}, {"schema_version": 1, "mappings": [None]}):
            with self.subTest(raw=raw):
                prepared = self.prepare(self.mapping_contract(), raw)
                self.assertTrue(prepared["issues"])

    def test_duplicate_and_unknown_mapping_node_ids_are_unresolved(self):
        duplicate = links()
        duplicate["mappings"].append(copy.deepcopy(duplicate["mappings"][0]))
        prepared = self.prepare(self.mapping_contract(), duplicate)
        self.assertTrue(all(not item["supported"] for item in prepared["code_connect"]["mappings"]))
        self.assertTrue(any(issue["code"] == "ambiguous_mapping" for issue in prepared["issues"]))
        unknown = links()
        unknown["mappings"][0]["node_id"] = "10:404"
        prepared = self.prepare(self.mapping_contract(), unknown)
        self.assertFalse(prepared["code_connect"]["mappings"][0]["supported"])
        self.assertTrue(any(issue["code"] == "unknown_mapping_node" for issue in prepared["issues"]))

    def test_sources_reject_traversal_absolute_urls_windows_and_non_kotlin(self):
        for source in ("../escape.kt", "app/../../escape.kt", "/tmp/Escape.kt",
                       "https://host/Button.kt", "file:///tmp/Button.kt", "C:/Button.kt",
                       "app\\Button.kt", "app/Button.tsx", "", "app/../Button.kt", "app/\x00Button.kt"):
            with self.subTest(source=source):
                prepared = self.prepare(self.mapping_contract(), links(source=source))
                self.assertFalse(prepared["code_connect"]["mappings"][0]["supported"])
                self.assertTrue(any(issue["code"] == "unsafe_source" for issue in prepared["issues"]))

    def test_source_hash_is_provenance_without_a_usage_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app").mkdir()
            content = b"// AppButton is mentioned but not composed.\n"
            (root / "app" / "AppButton.kt").write_bytes(content)
            raw = links()
            snapshot = copy.deepcopy(raw)
            prepared = self.prepare(self.mapping_contract(), raw, root)
            mapping = prepared["code_connect"]["mappings"][0]
            self.assertTrue(mapping["source_exists"])
            self.assertEqual(mapping["source_sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(mapping["source"], "app/AppButton.kt")
            self.assertNotIn("usage_verified", mapping)
            self.assertNotIn("reused", mapping)
            self.assertEqual(raw, snapshot)

    def test_missing_source_is_an_issue_in_a_partial_result(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = self.prepare(self.mapping_contract(), links(), Path(directory))
            mapping = prepared["code_connect"]["mappings"][0]
            self.assertFalse(mapping["source_exists"])
            self.assertNotIn("source_sha256", mapping)
            self.assertTrue(any(issue["code"] == "source_missing" for issue in prepared["issues"]))

    def test_escaping_file_and_directory_symlinks_are_not_read(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            root.mkdir()
            outside = base / "outside"
            outside.mkdir()
            (outside / "Button.kt").write_text("secret provenance must not be read")
            (root / "file.kt").symlink_to(outside / "Button.kt")
            (root / "linked").symlink_to(outside, target_is_directory=True)
            for source in ("file.kt", "linked/Button.kt"):
                with self.subTest(source=source):
                    prepared = self.prepare(self.mapping_contract(), links(source=source), root)
                    mapping = prepared["code_connect"]["mappings"][0]
                    self.assertFalse(mapping["supported"])
                    self.assertNotIn("source_sha256", mapping)
                    self.assertTrue(any(issue["code"] == "unsafe_source" for issue in prepared["issues"]))

    def test_internal_symlink_can_supply_source_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Real.kt").write_bytes(b"safe")
            (root / "Alias.kt").symlink_to(root / "Real.kt")
            prepared = self.prepare(self.mapping_contract(), links(source="Alias.kt"), root)
            mapping = prepared["code_connect"]["mappings"][0]
            self.assertTrue(mapping["source_exists"])
            self.assertEqual(mapping["source_sha256"], "8b3369944dd2a3fab39e32d1aeb1f763946a458ae3e6368a46432adc8f3a0860")

    def test_unavailable_source_root_raises_oserror(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(OSError):
                self.prepare(self.mapping_contract(), links(), Path(directory) / "absent")

    def test_looping_source_root_is_reported_as_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            looping_root = Path(directory) / "loop"
            looping_root.symlink_to(looping_root, target_is_directory=True)
            try:
                self.prepare(self.mapping_contract(), links(), looping_root)
            except Exception as error:
                self.assertIsInstance(error, OSError)
            else:
                self.fail("an unavailable source root must fail")


if __name__ == "__main__":
    unittest.main()
