"""Offline runtime evidence tests; the adb double executes as a real subprocess."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from uxlib import runtime


def window_dump(width=1080, height=1920, nav="[0,1848][1080,1920]", visible="true"):
    return f"""WINDOW MANAGER DISPLAY CONTENTS
  Display: mDisplayId=0
    WindowInsetsStateController
      mState=InsetsState: {{mDisplayFrame=Rect(0, 0 - {width}, {height})}}
        InsetsSource id=1 type=statusBars frame=[0,0][{width},72] visible=true sideHint=TOP
        InsetsSource id=2 type=navigationBars frame={nav} visible={visible}
        InsetsSource id=3 type=ime frame=[0,900][1080,1920] visible=true
        InsetsSource id=4 type=systemGestures frame=[0,0][32,1920] visible=true
    OtherController
      InsetsSource id=9 type=statusBars frame=[0,0][1080,999] visible=true
"""


def device_metadata():
    return {"density": 3, "font_scale": 1, "locale": "en-US", "theme": "light",
            "rotation": 0, "api": 35, "fingerprint": "fixture/device:35"}


def raw_capture():
    return {"schema_version": 1, "build_id": "abc", "capture_id": "empty-1", "state": "empty",
            "hierarchy_kind": "accessibility", "origin": "fixture", "device": device_metadata(),
            "viewport_px": [1080, 1920], "insets_px": {"left": 0, "top": 72, "right": 0, "bottom": 72},
            "image": "screen.png", "evidence": ["ui.xml", "window.txt"],
            "nodes": [{"id": "n0", "parent_id": None, "tag": "ci.save", "class": "Button",
                       "bounds_px": [72, 444, 360, 564], "enabled": False}]}


class UiautomatorTests(unittest.TestCase):
    def test_recursive_hierarchy_and_present_properties(self):
        nodes = runtime.parse_uiautomator('''<?xml version="1.0"?><hierarchy rotation="0">
          <node resource-id="" class="Frame" bounds="[0,0][1080,1920]">
            <node resource-id="ci.save" class="Button" text="Save &amp; close" content-desc="Save"
              bounds="[72,444][360,564]" enabled="false" clickable="true" selected="false"
              checkable="true" checked="false" focusable="true"/>
          </node></hierarchy>''')
        self.assertEqual([n["id"] for n in nodes], ["n0", "n1"])
        self.assertEqual([n["parent_id"] for n in nodes], [None, "n0"])
        self.assertNotIn("enabled", nodes[0])
        self.assertEqual(nodes[1], {"id": "n1", "parent_id": "n0", "tag": "ci.save", "class": "Button",
                                    "text": "Save & close", "content_description": "Save",
                                    "bounds_px": [72, 444, 360, 564], "enabled": False, "clickable": True,
                                    "selected": False, "checkable": True, "checked": False, "focusable": True})

    def test_rejects_duplicate_nonempty_tags(self):
        with self.assertRaisesRegex(ValueError, "ambiguous|duplicate"):
            runtime.parse_uiautomator('<hierarchy><node resource-id="x" bounds="[0,0][1,1]"/><node resource-id="x" bounds="[0,0][2,2]"/></hierarchy>')

    def test_malformed_xml_bounds_and_boolean_fail(self):
        fixtures = ['<hierarchy>', '<hierarchy><node/></hierarchy>',
                    '<hierarchy><node bounds="[3,0][1,2]"/></hierarchy>',
                    '<hierarchy><node bounds="[0,0][nan,2]"/></hierarchy>',
                    '<hierarchy><node bounds="[0,0][1,2] garbage"/></hierarchy>',
                    '<hierarchy><node bounds="[0,0][1,2]" enabled="perhaps"/></hierarchy>']
        for xml in fixtures:
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                runtime.parse_uiautomator(xml)

    def test_empty_or_non_hierarchy_document_fails(self):
        for xml in ['<hierarchy/>', '<wrong><node bounds="[0,0][1,1]"/></wrong>']:
            with self.subTest(xml=xml), self.assertRaises(ValueError):
                runtime.parse_uiautomator(xml)


class InsetsTests(unittest.TestCase):
    def test_display_and_controller_isolation(self):
        dump = window_dump() + '''  Display: mDisplayId=7
    WindowInsetsStateController
      mState=InsetsState: {mDisplayFrame=Rect(0, 0 - 1600, 900)}
        InsetsSource id=a type=statusBars frame=[0,0][1600,40] visible=true
        InsetsSource id=b type=navigationBars frame=[1540,0][1600,900] visible=true sideHint=RIGHT
'''
        self.assertEqual(runtime.parse_insets(dump), {"viewport_px": [1080, 1920], "insets_px": {"left": 0, "top": 72, "right": 0, "bottom": 72}})
        self.assertEqual(runtime.parse_insets(dump, 7), {"viewport_px": [1600, 900], "insets_px": {"left": 0, "top": 40, "right": 60, "bottom": 0}})

    def test_hidden_bars_are_zero_with_no_invented_height(self):
        dump = window_dump(visible="false").replace("visible=true sideHint=TOP", "visible=false sideHint=TOP")
        self.assertEqual(runtime.parse_insets(dump)["insets_px"], {"left": 0, "top": 0, "right": 0, "bottom": 0})

    def test_left_navigation_and_alternative_source_notation(self):
        dump = '''DisplayContent{abcd displayId=2}
  WindowInsetsStateController
    mState=InsetsState: {mDisplayFrame=[0,0][1920,1080]}
      InsetsSource: {mType=statusBars, mFrame=[0,0][1920,63], mVisible=true}
      InsetsSource: {mType=navigationBars, mFrame=[0,0][81,1080], mVisible=true}
'''
        self.assertEqual(runtime.parse_insets(dump, 2)["insets_px"], {"left": 81, "top": 63, "right": 0, "bottom": 0})

    def test_missing_visibility_sources_display_or_frame_fail(self):
        base = window_dump()
        fixtures = [base.replace("visible=true sideHint=TOP", "sideHint=TOP"),
                    base.replace("type=navigationBars", "type=systemGestures"),
                    base.replace("mDisplayFrame=Rect(0, 0 - 1080, 1920)", "noDisplayFrame"),
                    base.replace("WindowInsetsStateController", "UnrelatedState"),
                    base.replace("frame=[0,0][1080,72]", "frame=bogus"),
                    base.replace("mDisplayId=0", "mDisplayId=3")]
        for dump in fixtures:
            with self.subTest(dump=dump), self.assertRaises(ValueError):
                runtime.parse_insets(dump)

    def test_duplicate_sources_or_controllers_are_ambiguous(self):
        base = window_dump()
        extra = "        InsetsSource id=8 type=statusBars frame=[0,0][1080,20] visible=true\n"
        for dump in [base.replace("    OtherController", extra + "    OtherController"), base + base]:
            with self.subTest(dump=dump), self.assertRaisesRegex(ValueError, "ambiguous|duplicate"):
                runtime.parse_insets(dump)

    def test_visible_detached_or_outside_frames_fail(self):
        for nav in ["[0,100][1080,150]", "[-1,0][60,1920]", "[0,0][1080,1920]"]:
            with self.subTest(nav=nav), self.assertRaises(ValueError):
                runtime.parse_insets(window_dump(nav=nav))

    def test_duplicate_frame_and_type_fields_are_ambiguous(self):
        for suffix in [" frame=[0,0][1080,31]", " type=navigationBars", " frame=garbage", " visible=0", " type=0"]:
            dump = window_dump().replace("sideHint=TOP", "sideHint=TOP" + suffix)
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "ambiguous|duplicate"):
                runtime.parse_insets(dump)

    def test_controller_outside_display_scope_is_excluded(self):
        dump = window_dump().replace("    WindowInsetsStateController", "UnrelatedRootSection\n    WindowInsetsStateController")
        with self.assertRaisesRegex(ValueError, "missing|ambiguous"):
            runtime.parse_insets(dump)

    def test_provider_and_control_map_diagnostics_are_not_state_sources(self):
        diagnostics = '''      Control map:
        target=Window type=statusBars frame=[0,0][1080,22] visible=false
      InsetsSourceProviders:
        InsetsSourceProvider
          mSource=InsetsSource id=1 type=statusBars frame=[0,0][1080,72] visible=true
        InsetsSourceProvider
          mSource=InsetsSource id=2 type=navigationBars frame=[0,1848][1080,1920] visible=true
'''
        dump = window_dump().replace("    OtherController", diagnostics + "    OtherController")
        self.assertEqual(runtime.parse_insets(dump)["insets_px"], {"left": 0, "top": 72, "right": 0, "bottom": 72})

    def test_initial_multiline_insets_state_ignores_other_controller_diagnostics(self):
        dump = '''  Display: mDisplayId=0
    WindowInsetsStateController
      InsetsState
        mDisplayFrame=Rect(0, 0 - 1080, 1920)
        InsetsSource id=1 type=statusBars frame=[0,0][1080,72] visible=true
        InsetsSource id=2 type=navigationBars frame=[0,1848][1080,1920] visible=true
      OtherDiagnostic
        mDisplayFrame=Rect(0, 0 - 200, 200)
        InsetsSource id=1 type=statusBars frame=[0,0][200,10] visible=true
'''
        self.assertEqual(runtime.parse_insets(dump)["viewport_px"], [1080, 1920])


class NormalizationTests(unittest.TestCase):
    def test_density_and_crop_are_applied_without_mutating_input(self):
        value = raw_capture()
        original = copy.deepcopy(value)
        normalized = runtime.normalize_runtime(value)
        self.assertEqual(normalized["content_size_dp"], [360, 592])
        self.assertEqual(normalized["nodes"][0]["bounds_dp"], [24, 124, 120, 164])
        self.assertNotIn("clickable", normalized["nodes"][0])
        self.assertEqual(normalized["hierarchy_kind"], "accessibility")
        self.assertEqual(value, original)

    def test_left_crop_and_outside_bounds_are_not_clipped(self):
        value = raw_capture()
        value["insets_px"] = {"left": 60, "top": 30, "right": 0, "bottom": 0}
        value["nodes"][0]["bounds_px"] = [0, 0, 1110, 1950]
        self.assertEqual(runtime.normalize_runtime(value)["nodes"][0]["bounds_dp"], [-20, -10, 350, 640])

    def test_invalid_numbers_and_content_geometry_fail(self):
        variants = []
        for field, bad in [("density", 0), ("density", float("nan")), ("density", True), ("font_scale", float("inf")), ("font_scale", -1)]:
            value = raw_capture(); value["device"][field] = bad; variants.append(value)
        for key, bad in [("viewport_px", [0, 1920]), ("viewport_px", [1080, float("inf")]),
                         ("insets_px", {"left": 0, "top": 1920, "right": 0, "bottom": 0}),
                         ("insets_px", {"left": -1, "top": 0, "right": 0, "bottom": 0})]:
            value = raw_capture(); value[key] = bad; variants.append(value)
        for bounds in [[1, 0, 0, 2], [0, 0, float("nan"), 2]]:
            value = raw_capture(); value["nodes"][0]["bounds_px"] = bounds; variants.append(value)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime.normalize_runtime(value)

    def test_missing_metadata_and_ambiguous_nodes_fail(self):
        values = []
        value = raw_capture(); del value["device"]["density"]; values.append(value)
        value = raw_capture(); value["nodes"][0]["parent_id"] = "missing"; values.append(value)
        value = raw_capture(); value["nodes"].append(copy.deepcopy(value["nodes"][0])); values.append(value)
        value = raw_capture(); node = copy.deepcopy(value["nodes"][0]); node["id"] = "n1"; value["nodes"].append(node); values.append(value)
        value = raw_capture(); value["nodes"][0]["parent_id"] = "n0"; values.append(value)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime.normalize_runtime(value)

    def test_overflowing_normalized_coordinates_are_rejected(self):
        value = raw_capture(); value["device"]["density"] = 1e-320
        with self.assertRaisesRegex(ValueError, "finite|overflow"):
            runtime.normalize_runtime(value)

    def test_unrepresentable_integer_metadata_raises_value_error(self):
        value = raw_capture(); value["device"]["density"] = 10 ** 1000
        with self.assertRaises(ValueError):
            runtime.normalize_runtime(value)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.png = self.root / "fixture.png"
        Image.new("RGB", (1080, 1920), "white").save(self.png)
        self.config = self.root / "fake.json"
        self.log = self.root / "calls.jsonl"
        self.adb = self.root / "fake-adb"
        self.adb.write_text("#!" + sys.executable + "\n" + '''import json, pathlib, sys, time
root = pathlib.Path(__file__).parent
cfg = json.loads((root / "fake.json").read_text())
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if len(args) < 3 or args[:2] != ["-s", "emulator-5554"]:
    sys.exit(91)
cmd = args[2:]
if cmd[:3] == ["shell", "uiautomator", "dump"] and len(cmd) == 4:
    (root / "owned-path").write_text(cmd[3])
failure = cfg.get("fail")
if failure and cmd[:len(failure.split())] == failure.split():
    sys.stdout.write("fixture stdout failure\\n")
    sys.stderr.write("fixture stderr failure\\n")
    sys.exit(17)
if cmd == ["exec-out", "screencap", "-p"]:
    sys.stdout.buffer.write((root / "fixture.png").read_bytes())
elif cmd[:3] == ["shell", "uiautomator", "dump"] and len(cmd) == 4:
    (root / "owned-path").write_text(cmd[3])
    print("UI hierchary dumped to: " + cmd[3])
elif cmd[:2] == ["exec-out", "cat"] and len(cmd) == 3:
    if cmd[2] != (root / "owned-path").read_text(): sys.exit(92)
    sys.stdout.write(cfg.get("xml", '<hierarchy><node resource-id="ci.save" bounds="[72,444][360,564]" enabled="false"/></hierarchy>'))
elif cmd == ["shell", "dumpsys", "window", "displays"]:
    sys.stdout.write(cfg["window"])
elif cmd[:3] == ["shell", "rm", "-f"] and len(cmd) == 4:
    if cmd[3] != (root / "owned-path").read_text(): sys.exit(93)
    (root / "removed-path").write_text(cmd[3])
elif cmd == ["shell", "pm", "path", "com.example.app"]:
    print(cfg.get("pm", "package:/data/app/com.example.app/base.apk"))
elif cmd[:2] == ["shell", "sha256sum"] and len(cmd) == 3 and cmd[2] == cfg.get("installed_path", "/data/app/com.example.app/base.apk"):
    print(cfg.get("apk_hash", "0" * 64) + "  " + cmd[2])
else:
    sys.stderr.write("unrecognized argv: " + repr(cmd))
    sys.exit(94)
''')
        self.adb.chmod(0o700)
        self.settings = {"window": window_dump()}
        self.write_config()

    def write_config(self):
        self.config.write_text(json.dumps(self.settings))

    def collect(self, **kwargs):
        options = {"serial": "emulator-5554", "package": "com.example.app", "build_id": "abc",
                   "state": "empty", "output_dir": self.root / "captures", "adb": str(self.adb),
                   "metadata": device_metadata()}
        options.update(kwargs)
        return runtime.collect_adb(**options)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_collects_fresh_evidence_actual_dimensions_hash_and_declared_build(self):
        first = self.collect()
        second = self.collect()
        self.assertEqual(first["viewport_px"], [1080, 1920])
        self.assertEqual(first["insets_px"]["top"], 72)
        self.assertEqual(first["build_binding"], "declared")
        self.assertEqual(first["image_sha256"], hashlib.sha256(self.png.read_bytes()).hexdigest())
        self.assertEqual(runtime.normalize_runtime(first)["nodes"][0]["bounds_dp"], [24, 124, 120, 164])
        self.assertNotEqual(first["capture_id"], second["capture_id"])
        self.assertNotEqual(first["image"], second["image"])
        self.assertTrue(all(Path(path).is_file() for path in first["evidence"]))
        remotes = [args[-1] for args in self.calls() if args[2:5] == ["shell", "uiautomator", "dump"]]
        removals = [args[-1] for args in self.calls() if args[2:5] == ["shell", "rm", "-f"]]
        self.assertEqual(removals, remotes)
        self.assertEqual(len(set(remotes)), 2)
        self.assertTrue(all(path.startswith("/data/local/tmp/") and path.endswith(".xml") for path in remotes))

    def test_failed_dump_preserves_nonzero_diagnostics_and_cleans_owned_path(self):
        self.settings["fail"] = "shell uiautomator dump"; self.write_config()
        with self.assertRaisesRegex(ValueError, "17"):
            self.collect()
        self.assertTrue((self.root / "removed-path").is_file())
        diagnostic_bytes = b"\n".join(p.read_bytes() for p in (self.root / "captures").rglob("*diagnostic*"))
        self.assertIn(b"fixture stdout failure\n", diagnostic_bytes)
        self.assertIn(b"fixture stderr failure\n", diagnostic_bytes)
        self.assertIn(b"17", diagnostic_bytes)

    def test_invalid_current_xml_does_not_reuse_existing_capture(self):
        old = self.collect()
        self.settings["xml"] = "not XML"; self.write_config()
        with self.assertRaises(ValueError):
            self.collect()
        self.assertTrue(Path(old["image"]).is_file())
        self.assertEqual((self.root / "removed-path").read_text(), (self.root / "owned-path").read_text())

    def test_metadata_is_required_before_any_adb_call(self):
        with self.assertRaisesRegex(ValueError, "density.*font_scale|font_scale.*density"):
            self.collect(metadata={})
        self.assertFalse(self.log.exists())

    def test_none_metadata_and_invalid_apk_path_are_input_errors(self):
        with self.assertRaisesRegex(ValueError, "density.*font_scale|font_scale.*density"):
            self.collect(metadata=None)
        for bad in [None, 17, ""]:
            metadata = device_metadata(); metadata["apk_path"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.collect(metadata=metadata)
        self.assertFalse(self.log.exists())

    def test_unsafe_identifiers_are_rejected_before_collection(self):
        for overrides in [{"serial": "-s"}, {"serial": "dev;id"}, {"package": "com.app;id"}, {"package": "-x"}]:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.collect(**overrides)
        self.assertFalse(self.log.exists())

    def test_mismatched_display_and_screenshot_are_rejected(self):
        self.settings["window"] = window_dump(width=1200, nav="[0,1848][1200,1920]"); self.write_config()
        with self.assertRaisesRegex(ValueError, "dimension|viewport|screenshot"):
            self.collect()

    def test_provided_hash_alone_does_not_verify_installed_build(self):
        metadata = device_metadata(); metadata["apk_sha256"] = "f" * 64
        self.assertEqual(self.collect(metadata=metadata)["build_binding"], "declared")

    def test_apk_binding_requires_installed_hash_equality_and_records_receipt(self):
        apk = self.root / "app.apk"; apk.write_bytes(b"local-built-apk")
        digest = hashlib.sha256(b"local-built-apk").hexdigest()
        self.settings["apk_hash"] = digest; self.write_config()
        metadata = device_metadata(); metadata["apk_path"] = str(apk)
        capture = self.collect(metadata=metadata)
        self.assertEqual(capture["build_binding"], "verified")
        self.assertEqual(capture["apk_sha256"], digest)
        receipt = "\n".join(Path(p).read_text() for p in capture["evidence"] if "binding" in Path(p).name)
        self.assertIn(digest, receipt)
        self.assertIn("package:/data/app/com.example.app/base.apk", receipt)

    def test_mismatched_apk_and_split_apk_fail(self):
        apk = self.root / "app.apk"; apk.write_bytes(b"local-built-apk")
        metadata = device_metadata(); metadata["apk_path"] = str(apk)
        with self.assertRaisesRegex(ValueError, "hash|mismatch"):
            self.collect(metadata=metadata)
        self.settings["pm"] = "package:/data/app/com.example.app/base.apk\npackage:/data/app/com.example.app/split.apk"; self.write_config()
        with self.assertRaisesRegex(ValueError, "split|one|single"):
            self.collect(metadata=metadata)

    def test_installed_android_hashed_base_path_is_supported(self):
        apk = self.root / "app.apk"; apk.write_bytes(b"local-built-apk")
        installed = "/data/app/~~abc==/com.example.app-hash_123==/base.apk"
        self.settings.update(pm="package:" + installed, installed_path=installed,
                             apk_hash=hashlib.sha256(b"local-built-apk").hexdigest())
        self.write_config()
        metadata = device_metadata(); metadata["apk_path"] = str(apk)
        self.assertEqual(self.collect(metadata=metadata)["build_binding"], "verified")

    def test_single_preinstalled_apk_path_is_a_valid_base(self):
        apk = self.root / "app.apk"; apk.write_bytes(b"local-built-apk")
        installed = "/system/app/Example/Example.apk"
        self.settings.update(pm="package:" + installed, installed_path=installed,
                             apk_hash=hashlib.sha256(b"local-built-apk").hexdigest())
        self.write_config()
        metadata = device_metadata(); metadata["apk_path"] = str(apk)
        self.assertEqual(self.collect(metadata=metadata)["build_binding"], "verified")

    def test_cleanup_failure_is_nonzero_and_keeps_cleanup_diagnostic(self):
        self.settings["fail"] = "shell rm -f"; self.write_config()
        with self.assertRaisesRegex(ValueError, "17"):
            self.collect()
        diagnostic_bytes = b"\n".join(p.read_bytes() for p in (self.root / "captures").rglob("*diagnostic*"))
        self.assertIn(b"fixture stdout failure\n", diagnostic_bytes)
        self.assertIn(b"rm", diagnostic_bytes)

    def test_cat_failure_still_removes_only_owned_remote_xml(self):
        self.settings["fail"] = "exec-out cat"; self.write_config()
        with self.assertRaisesRegex(ValueError, "17"):
            self.collect()
        self.assertEqual((self.root / "removed-path").read_text(), (self.root / "owned-path").read_text())

    def test_other_displays_fail_before_unsupported_transport(self):
        metadata = device_metadata(); metadata["display_id"] = 2
        with self.assertRaisesRegex(ValueError, "display_id=0|display"):
            self.collect(metadata=metadata)
        self.assertFalse(self.log.exists())

    def test_subprocesses_are_bounded_and_transport_failure_is_reported(self):
        import subprocess
        with patch.object(runtime.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adb"], 15, output=b"partial adb stdout\n")) as run:
            with self.assertRaisesRegex(ValueError, "timed out|timeout"):
                self.collect()
            self.assertGreater(run.call_args.kwargs["timeout"], 0)
            self.assertLessEqual(run.call_args.kwargs["timeout"], 60)
        diagnostics = b"\n".join(p.read_bytes() for p in (self.root / "captures").rglob("*diagnostic*"))
        self.assertIn(b"partial adb stdout\n", diagnostics)


if __name__ == "__main__":
    unittest.main()
