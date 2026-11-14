"""Parse and collect runtime evidence without changing device configuration.

Collection requires explicit device metadata. Commands have a fixed timeout and
operate on one serial; the only remote write is a unique UIAutomator dump that
is removed in a finally block. Failed commands retain their raw output.
"""
from __future__ import annotations

import copy
import hashlib
import io
import math
from pathlib import Path
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET

from PIL import Image, UnidentifiedImageError


_BOOL_FIELDS = ("enabled", "clickable", "selected", "checkable", "checked", "focusable")
_DEVICE_FIELDS = ("density", "font_scale", "locale", "theme", "rotation", "api", "fingerprint")
_EDGES = ("left", "top", "right", "bottom")
_TIMEOUT_SECONDS = 15
_BRACKET_FRAME = r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]"
_RECT_FRAME = r"Rect\(\s*(-?\d+)\s*,\s*(-?\d+)\s*-\s*(-?\d+)\s*,\s*(-?\d+)\s*\)"


def _number(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be finite numeric data")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError(f"{label} exceeds finite numeric range") from exc
    if not finite:
        raise ValueError(f"{label} must be finite numeric data")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    if nonnegative and value < 0:
        raise ValueError(f"{label} must be nonnegative")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _bounds(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{label} must contain four coordinates")
    result = [_number(v, label) for v in value]
    if result[2] < result[0] or result[3] < result[1]:
        raise ValueError(f"{label} must have ordered bounds")
    return result


def _device(value):
    if value is None:
        raise ValueError("missing device metadata fields: " + ", ".join(_DEVICE_FIELDS))
    if not isinstance(value, dict):
        raise ValueError("device metadata must be an object")
    missing = [key for key in _DEVICE_FIELDS if key not in value]
    if missing:
        raise ValueError("missing device metadata fields: " + ", ".join(missing))
    _number(value["density"], "density", positive=True)
    _number(value["font_scale"], "font_scale", positive=True)
    for field in ("locale", "theme", "fingerprint"):
        _text(value[field], field)
    if isinstance(value["api"], bool) or not isinstance(value["api"], int) or value["api"] < 1:
        raise ValueError("api must be a positive integer")
    if isinstance(value["rotation"], bool) or not isinstance(value["rotation"], int) or value["rotation"] not in (0, 1, 2, 3, 90, 180, 270):
        raise ValueError("rotation must be Android rotation 0..3 or degrees 0/90/180/270")


def _validate_nodes(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("nodes must be a nonempty list")
    ids, tags = set(), set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("each node must be an object")
        node_id = _text(node.get("id"), "node id")
        if node_id in ids:
            raise ValueError(f"duplicate node id: {node_id}")
        ids.add(node_id)
        tag = node.get("tag", "")
        if not isinstance(tag, str):
            raise ValueError("node tag must be a string")
        if tag:
            if tag in tags:
                raise ValueError(f"ambiguous duplicate tag: {tag}")
            tags.add(tag)
        _bounds(node.get("bounds_px"), f"node {node_id} bounds_px")
        for field in _BOOL_FIELDS:
            if field in node and not isinstance(node[field], bool):
                raise ValueError(f"node {node_id} {field} must be boolean")
        for field in ("class", "text", "content_description"):
            if field in node and not isinstance(node[field], str):
                raise ValueError(f"node {node_id} {field} must be a string")
    parents = {}
    for node in nodes:
        parent = node.get("parent_id")
        if parent is not None and (not isinstance(parent, str) or parent not in ids):
            raise ValueError(f"node {node['id']} parent_id must reference an existing node")
        parents[node["id"]] = parent
    for node_id in parents:
        seen, current = set(), node_id
        while current is not None:
            if current in seen:
                raise ValueError(f"cyclic node parent hierarchy: {node_id}")
            seen.add(current)
            current = parents[current]


def parse_uiautomator(xml_text: str) -> list[dict]:
    """Read actual XML node ancestry and only properties present in the dump."""
    if not isinstance(xml_text, str):
        raise ValueError("UIAutomator XML must be text")
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValueError("UIAutomator XML must not contain DTDs or entities")
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError) as exc:
        raise ValueError(f"malformed UIAutomator XML: {exc}") from exc
    if root.tag != "hierarchy":
        raise ValueError("UIAutomator XML root must be hierarchy")
    result = []

    def visit(element, parent_id):
        next_parent = parent_id
        if element.tag == "node":
            match = re.fullmatch(_BRACKET_FRAME, element.get("bounds", ""))
            if match is None:
                raise ValueError("malformed or missing UIAutomator node bounds")
            node = {"id": f"n{len(result)}", "parent_id": parent_id,
                    "bounds_px": _bounds([int(v) for v in match.groups()], "UIAutomator bounds")}
            for source, target in (("resource-id", "tag"), ("class", "class"), ("text", "text"), ("content-desc", "content_description")):
                if source in element.attrib:
                    node[target] = element.attrib[source]
            for field in _BOOL_FIELDS:
                if field in element.attrib:
                    raw = element.attrib[field]
                    if raw not in ("true", "false"):
                        raise ValueError(f"invalid UIAutomator {field} boolean: {raw}")
                    node[field] = raw == "true"
            result.append(node)
            next_parent = node["id"]
        for child in element:
            visit(child, next_parent)

    visit(root, None)
    _validate_nodes(result)
    return result


def _display_id(line):
    patterns = (r"^\s*Display:\s*mDisplayId\s*=\s*(\d+)\b",
                r"^\s*DisplayContent\b.*?\bdisplayId\s*=\s*(\d+)\b",
                r"^\s*Display\s+#?(\d+)\s*[:{]")
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return int(match.group(1))
    return None


def _indent(line):
    return len(line) - len(line.lstrip())


def _controller_sections(dump_text, display_id):
    lines = dump_text.splitlines()
    headers = [(index, _display_id(line)) for index, line in enumerate(lines) if _display_id(line) is not None]
    sections = []
    for pos, (start, actual_id) in enumerate(headers):
        if actual_id != display_id:
            continue
        end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
        display_indent = _indent(lines[start])
        end = next((index for index in range(start + 1, end)
                    if lines[index].strip() and _indent(lines[index]) <= display_indent), end)
        for index in range(start + 1, end):
            if re.match(r"^\s*WindowInsetsStateController\b", lines[index]):
                indent = _indent(lines[index])
                section_end = index + 1
                while section_end < end and (not lines[section_end].strip() or _indent(lines[section_end]) > indent):
                    section_end += 1
                sections.append("\n".join(lines[index + 1:section_end]))
    return sections


def _initial_insets_state(section):
    # Android repeats each source in provider diagnostics after the initial
    # InsetsState. Those repeats describe providers, not additional bar sources.
    lines = section.splitlines()
    end = next((index for index, line in enumerate(lines)
                if re.match(r"^\s*(?:Control map|InsetsSourceProviders)\s*:", line)), len(lines))
    lines = lines[:end]
    starts = [index for index, line in enumerate(lines)
              if re.match(r"^\s*(?:mState\s*=\s*)?InsetsState\b", line)]
    if len(starts) > 1:
        raise ValueError("ambiguous duplicate initial InsetsState sections")
    if not starts:
        return "\n".join(lines)
    start = starts[0]
    indent = _indent(lines[start])
    end = next((index for index in range(start + 1, len(lines))
                if lines[index].strip() and _indent(lines[index]) <= indent), len(lines))
    return "\n".join(lines[start:end])


def parse_insets(dump_text: str, display_id: int = 0) -> dict:
    """Parse one display's controller; refuse incomplete or ambiguous bar data."""
    if not isinstance(dump_text, str):
        raise ValueError("window display dump must be text")
    if isinstance(display_id, bool) or not isinstance(display_id, int) or display_id < 0:
        raise ValueError("display_id must be a nonnegative integer")
    sections = _controller_sections(dump_text, display_id)
    if len(sections) != 1:
        raise ValueError(f"missing or ambiguous WindowInsetsStateController for display {display_id}")
    section = _initial_insets_state(sections[0])
    frame_matches = list(re.finditer(r"\bmDisplayFrame\s*=\s*(?:" + _BRACKET_FRAME + "|" + _RECT_FRAME + ")", section))
    if len(frame_matches) != 1:
        raise ValueError("missing or ambiguous display frame in WindowInsetsStateController")
    display = [int(value) for value in frame_matches[0].groups() if value is not None]
    if display[0:2] != [0, 0] or display[2] <= 0 or display[3] <= 0:
        raise ValueError("display frame must have zero origin and positive dimensions")
    width, height = display[2:]
    sources = {"statusBars": [], "navigationBars": []}
    for record in re.split(r"\bInsetsSource\b\s*:?[ \t]*", section)[1:]:
        types = re.findall(r"\b(?:mType|type)\s*=\s*([^,\s}]+)", record)
        if not any(bar_type in sources for bar_type in types):
            continue
        if len(types) != 1:
            raise ValueError("ambiguous duplicate InsetsSource type fields")
        bar_type = types[0]
        visible = re.findall(r"\b(?:mVisible|visible)\s*=\s*([^,\s}]+)", record)
        frame_fields = re.findall(r"\b(?:mFrame|frame)\s*=", record)
        frames = list(re.finditer(r"\b(?:mFrame|frame)\s*=\s*(?:" + _BRACKET_FRAME + "|" + _RECT_FRAME + ")", record))
        if len(visible) != 1 or visible[0] not in ("true", "false") or len(frames) != 1 or len(frame_fields) != 1:
            raise ValueError(f"missing or ambiguous frame/visibility for {bar_type}")
        bounds = _bounds([int(value) for value in frames[0].groups() if value is not None], f"{bar_type} frame")
        sources[bar_type].append((bounds, visible[0] == "true", re.findall(r"\bsideHint\s*=\s*(TOP|BOTTOM|LEFT|RIGHT)\b", record)))
    insets = dict.fromkeys(_EDGES, 0)
    for bar_type, entries in sources.items():
        if len(entries) != 1:
            raise ValueError(f"missing or ambiguous duplicate {bar_type} source")
        (left, top, right, bottom), visible, hints = entries[0]
        if not visible:
            continue
        if left < 0 or top < 0 or right > width or bottom > height or right <= left or bottom <= top:
            raise ValueError(f"visible {bar_type} frame is outside display or empty")
        candidates = {}
        if left == 0 and right == width:
            if top == 0:
                candidates["top"] = bottom
            if bottom == height:
                candidates["bottom"] = height - top
        if top == 0 and bottom == height:
            if left == 0:
                candidates["left"] = right
            if right == width:
                candidates["right"] = width - left
        if len(candidates) != 1:
            raise ValueError(f"visible {bar_type} frame has ambiguous or detached display edge")
        edge, size = next(iter(candidates.items()))
        if hints and (len(hints) != 1 or hints[0].lower() != edge):
            raise ValueError(f"{bar_type} sideHint disagrees with frame geometry")
        insets[edge] = max(insets[edge], size)
    if insets["left"] + insets["right"] >= width or insets["top"] + insets["bottom"] >= height:
        raise ValueError("bar insets leave no content")
    return {"viewport_px": [width, height], "insets_px": insets}


def normalize_runtime(runtime: dict) -> dict:
    """Normalize screen pixels to content-relative dp without clipping bounds."""
    if not isinstance(runtime, dict):
        raise ValueError("runtime must be an object")
    if type(runtime.get("schema_version")) is not int or runtime["schema_version"] != 1:
        raise ValueError("runtime schema_version must be 1")
    for key in ("build_id", "capture_id", "state", "hierarchy_kind"):
        _text(runtime.get(key), key)
    if runtime.get("origin") not in ("device", "fixture"):
        raise ValueError("runtime origin must be device or fixture")
    _device(runtime.get("device"))
    viewport = runtime.get("viewport_px")
    if not isinstance(viewport, (list, tuple)) or len(viewport) != 2:
        raise ValueError("viewport_px must contain width and height")
    width, height = [_number(value, "viewport_px", positive=True) for value in viewport]
    insets = runtime.get("insets_px")
    if not isinstance(insets, dict) or any(edge not in insets for edge in _EDGES):
        raise ValueError("insets_px must provide left, top, right, bottom")
    for edge in _EDGES:
        _number(insets[edge], f"insets_px.{edge}", nonnegative=True)
    if insets["left"] + insets["right"] >= width or insets["top"] + insets["bottom"] >= height:
        raise ValueError("insets_px must leave positive content dimensions")
    _validate_nodes(runtime.get("nodes"))
    result = copy.deepcopy(runtime)
    density = runtime["device"]["density"]
    result["content_size_dp"] = [(width - insets["left"] - insets["right"]) / density,
                                 (height - insets["top"] - insets["bottom"]) / density]
    for value in result["content_size_dp"]:
        _number(value, "content_size_dp", positive=True)
    for node in result["nodes"]:
        left, top, right, bottom = node["bounds_px"]
        node["bounds_dp"] = [(left - insets["left"]) / density, (top - insets["top"]) / density,
                             (right - insets["left"]) / density, (bottom - insets["top"]) / density]
        _bounds(node["bounds_dp"], "normalized bounds_dp")
    return result


def _raw_bytes(value):
    return value if isinstance(value, bytes) else (value or "").encode("utf-8")


def collect_adb(serial: str, package: str, build_id: str, state: str, output_dir: Path,
                adb: str = "adb", metadata: dict | None = None) -> dict:
    """Collect fresh, bounded evidence and optionally bind a local APK to device.

    ``metadata.apk_path`` enables a read-only installed base APK hash comparison.
    Split installs are unsupported. A caller-provided hash alone is only a claim.
    All seven device metadata fields are required; none are inferred or invented.
    """
    if not isinstance(serial, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}", serial) is None:
        raise ValueError("serial contains unsupported or unsafe characters")
    if not isinstance(package, str) or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", package) is None:
        raise ValueError("package must be a safe Android package identifier")
    _text(build_id, "build_id")
    _text(state, "state")
    _text(adb, "adb")
    _device(metadata)
    display_id = metadata.get("display_id", 0)
    if isinstance(display_id, bool) or not isinstance(display_id, int) or display_id < 0:
        raise ValueError("display_id must be a nonnegative integer")
    # UIAutomator and screencap defaults target the default display. Do not claim
    # alternate display evidence without a display-aware screenshot/UIA method.
    if display_id != 0:
        raise ValueError("collect_adb supports display_id=0 only; parse_insets supports explicit other displays")
    local_apk = None
    if "apk_path" in metadata:
        if not isinstance(metadata["apk_path"], (str, Path)) or not str(metadata["apk_path"]).strip():
            raise ValueError("apk_path must be a nonempty local file path")
        local_apk = Path(metadata["apk_path"])
        local_apk_hash = hashlib.sha256(local_apk.read_bytes()).hexdigest()
    capture_id = "capture-" + uuid.uuid4().hex
    destination = Path(output_dir).resolve() / capture_id
    destination.mkdir(parents=True, exist_ok=False)
    remote = "/data/local/tmp/figma-compose-ux-" + uuid.uuid4().hex + ".xml"
    diagnostics = destination / "command-diagnostics.txt"
    evidence = []

    def diagnose(args, status, stdout=b"", stderr=b""):
        with diagnostics.open("ab") as handle:
            handle.write((f"argv={args!r}\nstatus={status}\nstdout:\n").encode("utf-8"))
            handle.write(_raw_bytes(stdout))
            handle.write(b"\nstderr:\n")
            handle.write(_raw_bytes(stderr))
            handle.write(b"\n")

    def run(*args):
        argv = [adb, "-s", serial, *args]
        try:
            completed = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as exc:
            diagnose(argv, "timeout", exc.stdout, exc.stderr)
            raise ValueError(f"adb command timed out after {_TIMEOUT_SECONDS}s; diagnostics: {diagnostics}") from exc
        except OSError as exc:
            diagnose(argv, f"unavailable: {exc}")
            raise
        if completed.returncode:
            diagnose(argv, completed.returncode, completed.stdout, completed.stderr)
            raise ValueError(f"adb command failed with exit code {completed.returncode}; diagnostics: {diagnostics}")
        return completed.stdout

    image_path = destination / "screen.png"
    image_bytes = run("exec-out", "screencap", "-p")
    image_path.write_bytes(image_bytes)
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                raise ValueError("screencap did not produce a PNG")
            image.load()
            actual_size = list(image.size)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"invalid screencap PNG: {exc}") from exc
    # Mark the path owned before dump: a failed dump can still create a file.
    primary_failure = None
    try:
        dump_stdout = run("shell", "uiautomator", "dump", remote)
        (destination / "uiautomator-dump.txt").write_bytes(dump_stdout)
        xml_bytes = run("exec-out", "cat", remote)
        xml_path = destination / "ui.xml"
        xml_path.write_bytes(xml_bytes)
        try:
            xml_text = xml_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("UIAutomator dump is not UTF-8 XML") from exc
        nodes = parse_uiautomator(xml_text)
    except BaseException as exc:
        primary_failure = exc
        raise
    finally:
        try:
            run("shell", "rm", "-f", remote)
        except (ValueError, OSError):
            if primary_failure is None:
                raise
    window_bytes = run("shell", "dumpsys", "window", "displays")
    window_path = destination / "window.txt"
    window_path.write_bytes(window_bytes)
    try:
        geometry = parse_insets(window_bytes.decode("utf-8"), display_id)
    except UnicodeDecodeError as exc:
        raise ValueError("window dump is not UTF-8 text") from exc
    if geometry["viewport_px"] != actual_size:
        raise ValueError(f"screenshot dimensions {actual_size} disagree with display viewport {geometry['viewport_px']}")
    evidence.extend([str(xml_path), str(window_path), str(destination / "uiautomator-dump.txt")])
    result = {"schema_version": 1, "build_id": build_id, "capture_id": capture_id, "state": state,
              "hierarchy_kind": "accessibility", "origin": "device", "package": package,
              "device": {key: copy.deepcopy(metadata[key]) for key in _DEVICE_FIELDS},
              "viewport_px": actual_size, "insets_px": geometry["insets_px"], "image": str(image_path),
              "image_sha256": hashlib.sha256(image_bytes).hexdigest(), "evidence": evidence,
              "nodes": nodes, "build_binding": "declared"}
    if local_apk is not None:
        pm_output = run("shell", "pm", "path", package)
        receipt = destination / "apk-binding.txt"
        receipt.write_bytes(b"pm path stdout:\n" + pm_output)
        try:
            paths = pm_output.decode("utf-8").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError("installed APK path is not UTF-8") from exc
        if len(paths) != 1 or not paths[0].startswith("package:"):
            raise ValueError("APK binding requires one base APK; split or missing installs are unsupported")
        installed_path = paths[0][len("package:"):]
        if re.fullmatch(r"/[A-Za-z0-9_~./=+@-]+\.apk", installed_path) is None or ".." in Path(installed_path).parts:
            raise ValueError("installed base APK path is unsafe or unsupported")
        hash_output = run("shell", "sha256sum", installed_path)
        with receipt.open("ab") as handle:
            handle.write(b"\ninstalled sha256sum stdout:\n" + hash_output)
            handle.write((f"\nlocal APK: {local_apk.resolve()}\nlocal SHA256: {local_apk_hash}\n").encode("utf-8"))
        try:
            hash_text = hash_output.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("installed APK hash is not UTF-8") from exc
        match = re.fullmatch(r"([0-9a-fA-F]{64})[ \t]+\*?" + re.escape(installed_path) + r"\s*", hash_text)
        if match is None:
            raise ValueError("installed APK sha256sum response is missing or ambiguous")
        if match.group(1).lower() != local_apk_hash:
            raise ValueError(f"installed APK hash mismatch; binding receipt: {receipt}")
        result.update(build_binding="verified", apk_sha256=local_apk_hash)
        evidence.append(str(receipt))
    return result
