"""Apply exact, reversible source patches without using git or subprocesses.

Sessions retain private backups and a journal. Cleanup only changes a source
whose bytes still match the journal's postimage; completed entries stay complete
so a later cleanup cannot overwrite subsequent user work.
"""

from contextlib import contextmanager, ExitStack
import errno
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import stat


_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_STATES = {"pending", "applying", "applied", "restored", "deleted", "unapplied", "conflict"}
_DONE = {"restored", "deleted", "unapplied"}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _absolute(value):
    try:
        raw = os.fspath(value)
        if not isinstance(raw, str) or not raw or "\0" in raw:
            raise ValueError("expected a filesystem path")
        return Path(os.path.abspath(raw))
    except TypeError as error:
        raise ValueError("expected a filesystem path") from error


def _relative(value):
    if (not isinstance(value, str) or not value or "\0" in value or "\\" in value
            or value.startswith("/") or PureWindowsPath(value).drive
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("patch paths must be unambiguous project-relative paths")
    return value


def _hash_value(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("expected a SHA256 hexadecimal digest")
    return value.lower()


def _open_child(parent_fd, name):
    info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("symlink paths are not allowed")
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("a parent path is not a directory")
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except OSError as error:
        if error.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise ValueError("symlink or non-directory parent") from error
        raise


@contextmanager
def _directory(path, create_parents=False):
    """Walk absolute paths with no-follow directory descriptors."""
    descriptor = os.open("/", _DIR_FLAGS)
    try:
        for part in path.parts[1:]:
            try:
                child = _open_child(descriptor, part)
            except FileNotFoundError:
                if not create_parents:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                child = _open_child(descriptor, part)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def _parent(root_fd, relative, created_dirs=None):
    descriptor = os.dup(root_fd)
    prefix = []
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            prefix.append(part)
            try:
                child = _open_child(descriptor, part)
            except FileNotFoundError:
                if created_dirs is None:
                    raise
                os.mkdir(part, mode=0o755, dir_fd=descriptor)
                child = _open_child(descriptor, part)
                info = os.fstat(child)
                created_dirs.append({"path": "/".join(prefix),
                                     "device": info.st_dev, "inode": info.st_ino,
                                     "state": "created"})
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def _read_at(parent_fd, name):
    """Return bytes and mode, or None if absent; never open a symlink or FIFO."""
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("source and session files must be regular files, never symlinks")
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=parent_fd)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError("symlink files are not allowed") from error
        raise
    with os.fdopen(descriptor, "rb") as handle:
        current = os.fstat(handle.fileno())
        if not stat.S_ISREG(current.st_mode):
            raise ValueError("source and session files must be regular files")
        return handle.read(), stat.S_IMODE(current.st_mode)


def _snapshot(root_fd, relative):
    try:
        with _parent(root_fd, relative) as (parent_fd, name):
            return _read_at(parent_fd, name)
    except FileNotFoundError:
        return None


def _expect(snapshot, expected):
    if expected is None:
        if snapshot is not None:
            raise ValueError("new file patch would overwrite an existing file")
    elif snapshot is None or _sha(snapshot[0]) != expected:
        raise ValueError("source SHA256 changed or does not match the patch")


def _atomic_file(parent_fd, name, data, mode, expected, committed=None):
    """Write through an owned temporary file; new destinations use exclusive link."""
    _expect(_read_at(parent_fd, name), expected)
    temporary = ".uxpatch-" + secrets.token_hex(16) + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent_fd)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), mode)
            handle.flush()
            os.fsync(handle.fileno())
        _expect(_read_at(parent_fd, name), expected)
        if expected is None:
            # Unlike replace(), link() cannot overwrite a newly appeared target.
            os.link(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                    follow_symlinks=False)
        else:
            os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        if committed is not None:
            committed()
        os.fsync(parent_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def _store(session, manifest):
    data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with _directory(session) as session_fd:
        current = _read_at(session_fd, "manifest.json")
        _atomic_file(session_fd, "manifest.json", data, 0o600,
                     None if current is None else _sha(current[0]))


def _overlaps(first, second):
    return first == second or first in second.parents or second in first.parents


def _preflight(root, root_fd, patches, session):
    if not isinstance(patches, list):
        raise ValueError("patches must be a list")
    prepared = []
    seen = set()
    for patch in patches:
        if not isinstance(patch, dict) or not {"path", "before_sha256", "search", "replace"} <= patch.keys():
            raise ValueError("each patch requires path, before_sha256, search and replace")
        relative = _relative(patch["path"])
        if relative in seen:
            raise ValueError("each source file may be patched only once")
        if any(relative.startswith(other + "/") or other.startswith(relative + "/") for other in seen):
            raise ValueError("patch targets cannot be ancestors of other patch targets")
        seen.add(relative)
        if _overlaps(root / relative, session):
            raise ValueError("a source target cannot overlap the session directory")
        before = patch["before_sha256"]
        if before is not None:
            before = _hash_value(before)
        if not isinstance(patch["search"], str) or not isinstance(patch["replace"], str):
            raise ValueError("search and replace must be strings")
        try:
            search = patch["search"].encode("utf-8")
            replacement = patch["replace"].encode("utf-8")
        except UnicodeEncodeError as error:
            raise ValueError("patch strings must be valid UTF-8") from error
        original = _snapshot(root_fd, relative)
        if before is None:
            if search:
                raise ValueError("new file patches require an empty search")
            _expect(original, None)
            after, mode = replacement, 0o644
        else:
            if original is None:
                raise FileNotFoundError(f"source file does not exist: {relative}")
            _expect(original, before)
            if not search:
                raise ValueError("existing file patches require a nonempty search")
            offset = original[0].find(search)
            if offset < 0 or original[0].find(search, offset + 1) >= 0:
                raise ValueError("search literal must occur exactly once, including overlaps")
            after = original[0][:offset] + replacement + original[0][offset + len(search):]
            mode = original[1]
        prepared.append((relative, before, original, after, mode))
    return prepared


def _remove_owned_dirs(root_fd, manifest):
    for entry in sorted(manifest["created_dirs"], key=lambda item: item["path"].count("/"), reverse=True):
        if entry["state"] != "created":
            continue
        entry["state"] = "preserved"
        try:
            with _parent(root_fd, entry["path"]) as (parent_fd, name):
                info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (stat.S_ISDIR(info.st_mode) and info.st_dev == entry["device"]
                        and info.st_ino == entry["inode"]):
                    os.rmdir(name, dir_fd=parent_fd)
                    entry["state"] = "removed"
        except (OSError, ValueError):
            # Nonempty, replaced, or inaccessible directories remain user-owned.
            pass


def _reconcile(root_fd, session, manifest, originals, best_effort_journal=False):
    result = {"status": "clean", "restored": [], "deleted": [], "conflicts": [], "skipped": []}
    journal_errors = []

    def record():
        try:
            _store(session, manifest)
        except (OSError, ValueError) as error:
            if not best_effort_journal:
                raise
            journal_errors.append(error)

    for entry in manifest["patches"]:
        relative = entry["path"]
        state = entry["state"]
        if state in _DONE or state == "pending":
            if state == "pending":
                entry["state"] = "unapplied"
            result["skipped"].append(relative)
            continue
        try:
            current = _snapshot(root_fd, relative)
            if current is None:
                if entry["before_sha256"] is not None:
                    raise ValueError("patched source was removed")
                entry["state"] = "deleted"
                result["skipped"].append(relative)
            elif entry["before_sha256"] is not None and _sha(current[0]) == entry["before_sha256"]:
                entry["state"] = "restored"
                result["skipped"].append(relative)
            else:
                _expect(current, entry["after_sha256"])
                with _parent(root_fd, relative) as (parent_fd, name):
                    if entry["before_sha256"] is None:
                        _expect(_read_at(parent_fd, name), entry["after_sha256"])
                        os.unlink(name, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                        entry["state"] = "deleted"
                        result["deleted"].append(relative)
                    else:
                        _atomic_file(parent_fd, name, originals[relative], entry["mode"],
                                     entry["after_sha256"])
                        entry["state"] = "restored"
                        result["restored"].append(relative)
            entry.pop("conflict", None)
        except (ValueError, OSError) as error:
            entry["state"] = "conflict"
            entry["conflict"] = str(error)
            result["conflicts"].append(relative)
        record()
    _remove_owned_dirs(root_fd, manifest)
    if result["conflicts"]:
        result["status"] = "conflict"
    manifest["state"] = result["status"]
    record()
    if journal_errors:
        raise journal_errors[0]
    return result


def apply_patches(project_root: Path, patches: list[dict], session_dir: Path) -> dict:
    """Preflight every exact patch, save private backups, and journal source writes.

    Errors trigger hash-guarded rollback. The retained session remains available
    for cleanup if an interrupted write or a conflicting edit needs attention.
    """
    root = _absolute(project_root)
    session = _absolute(session_dir)
    if _overlaps(root, session) and session in (root, *root.parents):
        raise ValueError("the session cannot alias or contain the project root")
    # Validate existing session ancestors without creating them during preflight.
    probe = session
    while not probe.exists() and not probe.is_symlink():
        probe = probe.parent
    with _directory(probe):
        pass
    if session.exists() or session.is_symlink():
        raise ValueError("an existing session cannot be overwritten")
    with _directory(root) as root_fd:
        prepared = _preflight(root, root_fd, patches, session)
        with _directory(session.parent, create_parents=True) as parent_fd:
            os.mkdir(session.name, mode=0o700, dir_fd=parent_fd)
        manifest = {"schema_version": 1, "project_root": str(root), "state": "applying",
                    "created": [], "created_dirs": [], "patches": []}
        originals = {}
        with _directory(session) as session_fd:
            os.mkdir("backups", mode=0o700, dir_fd=session_fd)
            with _parent(session_fd, "backups/file") as (backups_fd, _):
                for index, (relative, before, original, after, mode) in enumerate(prepared):
                    backup = None
                    if original is not None:
                        backup = f"backups/{index:06d}.bin"
                        _atomic_file(backups_fd, f"{index:06d}.bin", original[0], 0o600, None)
                        originals[relative] = original[0]
                    else:
                        manifest["created"].append(relative)
                    manifest["patches"].append({"path": relative, "before_sha256": before,
                        "after_sha256": _sha(after), "backup": backup, "mode": mode,
                        "state": "pending"})
        _store(session, manifest)
        active = None
        try:
            for entry, (_, _, _, after, _) in zip(manifest["patches"], prepared):
                active = entry
                entry["state"] = "applying"
                _store(session, manifest)
                with _parent(root_fd, entry["path"], manifest["created_dirs"]) as (parent_fd, name):
                    _store(session, manifest)
                    _atomic_file(parent_fd, name, after, entry["mode"], entry["before_sha256"],
                                 committed=lambda: entry.update(state="applied"))
                entry["state"] = "applied"
                _store(session, manifest)
            manifest["state"] = "applied"
            _store(session, manifest)
        except BaseException as error:
            # A failed attempt is not ownership. In-process rollback can tell
            # whether rename/link committed even when a later fsync failed.
            if active is not None and active["state"] == "applying":
                active["state"] = "unapplied"
            try:
                _reconcile(root_fd, session, manifest, originals, best_effort_journal=True)
            except (OSError, ValueError) as rollback_error:
                error.add_note(f"Rollback could not finish; retain session {session}: {rollback_error}")
            raise
    return {"status": "clean", "session_dir": str(session),
            "manifest": str(session / "manifest.json"),
            "applied": [entry["path"] for entry in manifest["patches"]],
            "created": list(manifest["created"])}


def _load_manifest(session):
    with _directory(session) as session_fd:
        raw = _read_at(session_fd, "manifest.json")
        if raw is None:
            raise FileNotFoundError("session manifest does not exist")
        try:
            manifest = json.loads(raw[0])
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("invalid session manifest JSON") from error
        if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
                or manifest["schema_version"] != 1 or not isinstance(manifest.get("patches"), list)
                or not isinstance(manifest.get("created_dirs"), list)):
            raise ValueError("invalid session manifest schema")
        root_value = manifest.get("project_root")
        if not isinstance(root_value, str) or not Path(root_value).is_absolute():
            raise ValueError("invalid manifest project root")
        root = _absolute(root_value)
        if str(root) != root_value or root == session:
            raise ValueError("invalid manifest project root")
        seen = set()
        originals = {}
        for entry in manifest["patches"]:
            if not isinstance(entry, dict):
                raise ValueError("invalid manifest patch")
            relative = _relative(entry.get("path"))
            if relative in seen or _overlaps(root / relative, session):
                raise ValueError("duplicate or session-overlapping manifest path")
            seen.add(relative)
            before = entry.get("before_sha256")
            if before is not None:
                before = _hash_value(before)
            after = _hash_value(entry.get("after_sha256"))
            mode = entry.get("mode")
            if (entry.get("state") not in _STATES or type(mode) is not int
                    or not 0 <= mode <= 0o7777):
                raise ValueError("invalid manifest patch state or permissions")
            entry["before_sha256"], entry["after_sha256"] = before, after
            backup = entry.get("backup")
            if before is None:
                if backup is not None:
                    raise ValueError("new files cannot have original backups")
            else:
                _relative(backup)
                if len(backup.split("/")) != 2 or not backup.startswith("backups/"):
                    raise ValueError("invalid backup path")
                original = _snapshot(session_fd, backup)
                if original is None:
                    raise FileNotFoundError(f"original backup does not exist: {relative}")
                if _sha(original[0]) != before:
                    raise ValueError("original backup SHA256 does not match the manifest")
                originals[relative] = original[0]
        for entry in manifest["created_dirs"]:
            if (not isinstance(entry, dict) or type(entry.get("device")) is not int
                    or type(entry.get("inode")) is not int
                    or entry.get("state") not in {"created", "removed", "preserved"}):
                raise ValueError("invalid created-directory record")
            _relative(entry.get("path"))
    return manifest, root, originals


def cleanup(session_dir: Path) -> dict:
    """Restore/delete matching owned postimages, preserving every conflicting edit."""
    session = _absolute(session_dir)
    manifest, root, originals = _load_manifest(session)
    with ExitStack() as stack:
        try:
            root_fd = stack.enter_context(_directory(root))
        except (OSError, ValueError) as error:
            # If the entire project moved or became a symlink, no source is safe.
            result = {"status": "clean", "restored": [], "deleted": [], "conflicts": [], "skipped": []}
            for entry in manifest["patches"]:
                if entry["state"] in _DONE or entry["state"] == "pending":
                    result["skipped"].append(entry["path"])
                else:
                    entry["state"] = "conflict"
                    entry["conflict"] = str(error)
                    result["conflicts"].append(entry["path"])
            if result["conflicts"]:
                result["status"] = "conflict"
            manifest["state"] = result["status"]
            _store(session, manifest)
        else:
            result = _reconcile(root_fd, session, manifest, originals)
    return {**result, "session_dir": str(session), "manifest": str(session / "manifest.json")}
