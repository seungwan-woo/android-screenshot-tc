"""Safety checks for source instrumentation without a device or a git checkout."""

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from uxlib import instrumentation


def digest(data):
    return hashlib.sha256(data).hexdigest()


class InstrumentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self.session = self.base / "session"

    def source(self, name, content=b"old value\n"):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def change(self, name, content=b"old value\n", search="old", replace="new"):
        return {"path": name, "before_sha256": digest(content),
                "search": search, "replace": replace}

    def create(self, name, content="new file\n"):
        return {"path": name, "before_sha256": None, "search": "", "replace": content}

    def apply(self, patches):
        return instrumentation.apply_patches(self.root, patches, self.session)

    def test_cleanup_restores_dirty_bytes_and_mode_exactly(self):
        original = b"// dirty\xff\r\nold value\r\n"
        target = self.source("app/Main.kt", original)
        target.chmod(0o640)
        result = self.apply([self.change("app/Main.kt", original)])
        self.assertEqual(target.read_bytes(), b"// dirty\xff\r\nnew value\r\n")
        self.assertEqual(result["applied"], ["app/Main.kt"])
        self.assertEqual(result["status"], "clean")
        cleaned = instrumentation.cleanup(self.session)
        self.assertEqual(cleaned["status"], "clean")
        self.assertEqual(cleaned["restored"], ["app/Main.kt"])
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)

    def test_new_file_is_deleted_and_only_owned_empty_directories_removed(self):
        self.apply([self.create("generated/deep/Probe.kt")])
        unrelated = self.source("generated/user.txt", b"user")
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["deleted"], ["generated/deep/Probe.kt"])
        self.assertFalse((self.root / "generated/deep").exists())
        self.assertEqual(unrelated.read_bytes(), b"user")

    def test_backups_and_manifest_are_private_and_record_hashes(self):
        original = b"old value\n"
        self.source("Main.kt", original)
        self.apply([self.change("Main.kt"), self.create("Probe.kt")])
        for path in [self.session, *self.session.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0, str(path))
        manifest = json.loads((self.session / "manifest.json").read_text())
        self.assertEqual(manifest["patches"][0]["before_sha256"], digest(original))
        self.assertEqual(manifest["patches"][0]["after_sha256"], digest(b"new value\n"))
        self.assertIsNone(manifest["patches"][1]["before_sha256"])
        self.assertEqual(manifest["created"], ["Probe.kt"])

    def test_hash_mismatch_preflights_every_file_before_any_mutation(self):
        first = self.source("First.kt")
        second = self.source("Second.kt", b"dirty value\n")
        with self.assertRaises(ValueError):
            self.apply([self.change("First.kt"), self.change("Second.kt")])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual(second.read_bytes(), b"dirty value\n")
        self.assertFalse(self.session.exists())

    def test_missing_existing_source_is_an_oserror_without_session(self):
        with self.assertRaises(OSError):
            self.apply([self.change("Missing.kt")])
        self.assertFalse(self.session.exists())

    def test_ambiguous_or_absent_literals_are_rejected_without_changes(self):
        for data, search in [(b"old old", "old"), (b"aaa", "aa"), (b"other", "old")]:
            with self.subTest(data=data):
                target = self.source("Main.kt", data)
                with self.assertRaises(ValueError):
                    self.apply([self.change("Main.kt", data, search=search)])
                self.assertEqual(target.read_bytes(), data)
                self.assertFalse(self.session.exists())

    def test_existing_file_cannot_use_empty_search(self):
        target = self.source("Main.kt")
        with self.assertRaises(ValueError):
            self.apply([self.change("Main.kt", search="")])
        self.assertEqual(target.read_bytes(), b"old value\n")

    def test_new_file_patch_never_overwrites_existing_file(self):
        target = self.source("Main.kt", b"user bytes")
        with self.assertRaises(ValueError):
            self.apply([self.create("Main.kt")])
        self.assertEqual(target.read_bytes(), b"user bytes")

    def test_duplicate_target_preflight_is_atomic(self):
        target = self.source("Main.kt")
        with self.assertRaises(ValueError):
            self.apply([self.change("Main.kt"), self.change("Main.kt")])
        self.assertEqual(target.read_bytes(), b"old value\n")
        self.assertFalse(self.session.exists())

    def test_file_and_its_descendant_cannot_both_be_patch_targets(self):
        with self.assertRaises(ValueError):
            self.apply([self.create("generated"), self.create("generated/Probe.kt")])
        self.assertFalse((self.root / "generated").exists())
        self.assertFalse(self.session.exists())

    def test_absolute_traversal_and_platform_ambiguous_paths_are_rejected(self):
        for name in ["../escape.kt", "a/../../escape.kt", "/tmp/escape.kt",
                     "a/../Main.kt", "./Main.kt", "a//Main.kt", "", ".",
                     "C:\\escape.kt", "a\\Main.kt", "C:/escape.kt"]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.apply([self.create(name)])
                self.assertFalse(self.session.exists())

    def test_symlink_source_and_parent_and_dangling_link_are_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        real = outside / "Real.kt"
        real.write_bytes(b"old value\n")
        (self.root / "Link.kt").symlink_to(real)
        (self.root / "linked").symlink_to(outside, target_is_directory=True)
        (self.root / "Dangling.kt").symlink_to(outside / "missing.kt")
        for item in [self.change("Link.kt"), self.create("linked/New.kt"),
                     self.create("Dangling.kt")]:
            with self.subTest(path=item["path"]):
                with self.assertRaises(ValueError):
                    self.apply([item])
                self.assertFalse(self.session.exists())
        self.assertEqual(real.read_bytes(), b"old value\n")
        self.assertFalse((outside / "New.kt").exists())

    def test_nonregular_source_is_rejected(self):
        (self.root / "Directory.kt").mkdir()
        with self.assertRaises(ValueError):
            self.apply([self.change("Directory.kt")])

    def test_invalid_patch_shapes_are_valueerrors(self):
        self.source("Main.kt")
        good = self.change("Main.kt")
        cases = [None, {}, [None], [{}], [{**good, "path": 1}],
                 [{**good, "before_sha256": "wrong"}],
                 [{**good, "before_sha256": 3}], [{**good, "search": None}],
                 [{**good, "replace": None}], [{**good, "replace": "\ud800"}],
                 [{**self.create("New.kt"), "search": "old"}]]
        for patches in cases:
            with self.subTest(patches=repr(patches)):
                with self.assertRaises(ValueError):
                    self.apply(patches)
                self.assertFalse(self.session.exists())

    def test_existing_session_is_never_overwritten(self):
        self.source("Main.kt")
        self.session.mkdir()
        marker = self.session / "user-file"
        marker.write_bytes(b"preserve")
        with self.assertRaises(ValueError):
            self.apply([self.change("Main.kt")])
        self.assertEqual(marker.read_bytes(), b"preserve")
        self.assertEqual((self.root / "Main.kt").read_bytes(), b"old value\n")

    def test_symlink_project_or_session_parent_is_rejected(self):
        link = self.base / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            instrumentation.apply_patches(link, [], self.session)
        self.session = link / "session"
        with self.assertRaises(ValueError):
            self.apply([])
        self.assertFalse((self.root / "session").exists())

    def test_session_cannot_overlap_a_source_target(self):
        self.session = self.root / "generated/session"
        with self.assertRaises(ValueError):
            self.apply([self.create("generated")])
        self.assertFalse((self.root / "generated").exists())

    def test_cleanup_preserves_user_edits_while_restoring_other_files(self):
        first = self.source("First.kt")
        second = self.source("Second.kt")
        self.apply([self.change("First.kt"), self.change("Second.kt"), self.create("Probe.kt")])
        second.write_bytes(b"user changes after instrumentation")
        probe = self.root / "Probe.kt"
        probe.write_bytes(b"user probe")
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["restored"], ["First.kt"])
        self.assertEqual(result["conflicts"], ["Second.kt", "Probe.kt"])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual(second.read_bytes(), b"user changes after instrumentation")
        self.assertEqual(probe.read_bytes(), b"user probe")
        again = instrumentation.cleanup(self.session)
        self.assertEqual(again["status"], "conflict")
        self.assertEqual(again["conflicts"], ["Second.kt", "Probe.kt"])
        self.assertEqual(again["restored"], [])

    def test_successful_cleanup_is_idempotent(self):
        target = self.source("Main.kt")
        self.apply([self.change("Main.kt"), self.create("Probe.kt")])
        instrumentation.cleanup(self.session)
        target.write_bytes(b"new independent user work")
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["restored"], [])
        self.assertEqual(result["deleted"], [])
        self.assertEqual(target.read_bytes(), b"new independent user work")

    def test_missing_patched_source_conflicts_but_missing_created_source_is_clean(self):
        original = self.source("Main.kt")
        self.apply([self.change("Main.kt"), self.create("Probe.kt")])
        original.unlink()
        (self.root / "Probe.kt").unlink()
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["conflicts"], ["Main.kt"])
        self.assertFalse(original.exists())

    def test_cleanup_never_follows_replaced_source_symlink(self):
        target = self.source("Main.kt")
        self.apply([self.change("Main.kt")])
        outside = self.base / "user.kt"
        outside.write_bytes(b"new value\n")
        target.unlink()
        target.symlink_to(outside)
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["conflicts"], ["Main.kt"])
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_bytes(), b"new value\n")

    def test_cleanup_rejects_tampered_backup_before_restoring_any_file(self):
        first = self.source("First.kt")
        second = self.source("Second.kt")
        self.apply([self.change("First.kt"), self.change("Second.kt")])
        manifest = json.loads((self.session / "manifest.json").read_text())
        (self.session / manifest["patches"][1]["backup"]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            instrumentation.cleanup(self.session)
        self.assertEqual(first.read_bytes(), b"new value\n")
        self.assertEqual(second.read_bytes(), b"new value\n")

    def test_cleanup_rejects_manifest_traversal_without_touching_sources(self):
        target = self.source("Main.kt")
        self.apply([self.change("Main.kt")])
        manifest_path = self.session / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["patches"][0]["path"] = "../outside.kt"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            instrumentation.cleanup(self.session)
        self.assertEqual(target.read_bytes(), b"new value\n")

    def test_midapply_error_rolls_back_owned_changes_and_leaves_recoverable_manifest(self):
        first = self.source("First.kt", b"dirty\xff old\r\n")
        second = self.source("Second.kt")
        real_replace = os.replace
        failed = False

        def fail_second(src, dst, *args, **kwargs):
            nonlocal failed
            if str(dst) == "Second.kt" and not failed:
                failed = True
                raise OSError("injected second write failure")
            return real_replace(src, dst, *args, **kwargs)

        with patch.object(instrumentation.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected second write failure"):
                self.apply([self.change("First.kt", b"dirty\xff old\r\n"),
                            self.create("generated/Probe.kt"), self.change("Second.kt")])
        self.assertEqual(first.read_bytes(), b"dirty\xff old\r\n")
        self.assertEqual(second.read_bytes(), b"old value\n")
        self.assertFalse((self.root / "generated/Probe.kt").exists())
        self.assertTrue((self.session / "manifest.json").exists())
        self.assertEqual(instrumentation.cleanup(self.session)["status"], "clean")

    def test_change_after_preflight_is_preserved_and_prior_patch_rolled_back(self):
        first = self.source("First.kt")
        second = self.source("Second.kt")
        real_replace = os.replace
        changed = False

        def edit_second(src, dst, *args, **kwargs):
            nonlocal changed
            result = real_replace(src, dst, *args, **kwargs)
            if str(dst) == "First.kt" and not changed:
                changed = True
                second.write_bytes(b"concurrent user edit")
            return result

        with patch.object(instrumentation.os, "replace", side_effect=edit_second):
            with self.assertRaises(ValueError):
                self.apply([self.change("First.kt"), self.change("Second.kt")])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual(second.read_bytes(), b"concurrent user edit")

    def test_rollback_does_not_restore_an_unapplied_user_edit_matching_the_postimage(self):
        first = self.source("First.kt")
        second = self.source("Second.kt")
        real_replace = os.replace

        def edit_second(src, dst, *args, **kwargs):
            result = real_replace(src, dst, *args, **kwargs)
            if str(dst) == "First.kt":
                second.write_bytes(b"new value\n")
            return result

        with patch.object(instrumentation.os, "replace", side_effect=edit_second):
            with self.assertRaises(ValueError):
                self.apply([self.change("First.kt"), self.change("Second.kt")])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual(second.read_bytes(), b"new value\n")
        self.assertEqual(instrumentation.cleanup(self.session)["status"], "clean")
        self.assertEqual(second.read_bytes(), b"new value\n")

    def test_rollback_does_not_delete_an_unapplied_user_created_postimage(self):
        first = self.source("First.kt")
        real_replace = os.replace

        def create_probe(src, dst, *args, **kwargs):
            result = real_replace(src, dst, *args, **kwargs)
            if str(dst) == "First.kt":
                (self.root / "Probe.kt").write_bytes(b"new file\n")
            return result

        with patch.object(instrumentation.os, "replace", side_effect=create_probe):
            with self.assertRaises(ValueError):
                self.apply([self.change("First.kt"), self.create("Probe.kt")])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual((self.root / "Probe.kt").read_bytes(), b"new file\n")
        instrumentation.cleanup(self.session)
        self.assertEqual((self.root / "Probe.kt").read_bytes(), b"new file\n")

    def test_repeated_cleanup_does_not_remove_a_previously_preserved_directory(self):
        self.apply([self.create("generated/Probe.kt")])
        user_file = self.source("generated/user.txt", b"user")
        instrumentation.cleanup(self.session)
        user_file.unlink()
        instrumentation.cleanup(self.session)
        self.assertTrue((self.root / "generated").is_dir())

    def test_interrupted_applying_journal_can_restore_matching_postimage(self):
        target = self.source("Main.kt")
        self.apply([self.change("Main.kt")])
        manifest_path = self.session / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["state"] = "applying"
        manifest["patches"][0]["state"] = "applying"
        manifest_path.write_text(json.dumps(manifest))
        result = instrumentation.cleanup(self.session)
        self.assertEqual(result["restored"], ["Main.kt"])
        self.assertEqual(target.read_bytes(), b"old value\n")

    def test_journal_failure_does_not_stop_rollback_of_other_owned_files(self):
        first = self.source("First.kt")
        second = self.source("Second.kt")
        real_replace = os.replace
        source_writes = 0

        def fail_journal(src, dst, *args, **kwargs):
            nonlocal source_writes
            if str(dst) == "manifest.json" and source_writes >= 2:
                raise OSError("journal unavailable")
            result = real_replace(src, dst, *args, **kwargs)
            if str(dst) in {"First.kt", "Second.kt"}:
                source_writes += 1
            return result

        with patch.object(instrumentation.os, "replace", side_effect=fail_journal):
            with self.assertRaisesRegex(OSError, "journal unavailable"):
                self.apply([self.change("First.kt"), self.change("Second.kt")])
        self.assertEqual(first.read_bytes(), b"old value\n")
        self.assertEqual(second.read_bytes(), b"old value\n")
        self.assertEqual(instrumentation.cleanup(self.session)["status"], "clean")

    def test_cleanup_reports_journal_write_error_instead_of_hiding_it(self):
        target = self.source("Main.kt")
        self.apply([self.change("Main.kt")])
        real_replace = os.replace
        restored = False
        failed = False

        def fail_once(src, dst, *args, **kwargs):
            nonlocal restored, failed
            if str(dst) == "manifest.json" and restored and not failed:
                failed = True
                raise OSError("journal write failed")
            result = real_replace(src, dst, *args, **kwargs)
            if str(dst) == "Main.kt":
                restored = True
            return result

        with patch.object(instrumentation.os, "replace", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "journal write failed"):
                instrumentation.cleanup(self.session)
        self.assertEqual(target.read_bytes(), b"old value\n")
        self.assertEqual(instrumentation.cleanup(self.session)["status"], "clean")


if __name__ == "__main__":
    unittest.main()
