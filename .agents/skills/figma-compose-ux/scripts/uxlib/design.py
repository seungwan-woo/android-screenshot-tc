"""Validate normalized design contracts and retain Code Connect provenance.

``prepare_design`` deep-copies the contract and adds top-level ``code_connect``
and ``issues`` objects. Code Connect mappings retain their original fields and
gain ``supported``. Only Compose aliases with an unambiguous node, component,
and safe project-relative Kotlin path are supported. When a source root is
provided, ``source_exists`` and (for existing files) ``source_sha256`` describe
source provenance. Neither a mapping nor its source hash proves runtime reuse.
Embedded mappings are reused when no explicit mapping argument is supplied.
Without a source root, previously recorded source metadata remains a receipt;
with a source root, source metadata is recomputed rather than trusted.

Bounds already represent content-relative dp. Figma and image scales are
validated provenance; they never rescale or clip the supplied bounds.
"""

from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _number(value, label, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite or (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError(f"{label} must be finite and in its allowed range")
    return value


def _json_value(value, label):
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"{label} must contain finite JSON values") from exc


def _bounds(value, label):
    _list(value, label)
    if len(value) != 4:
        raise ValueError(f"{label} must contain four coordinates")
    for coordinate in value:
        _number(coordinate, label)
    if value[2] < value[0] or value[3] < value[1]:
        raise ValueError(f"{label} must be ordered left, top, right, bottom")


def _validate_design(value):
    _object(value, "design contract")
    _json_value(value, "design contract")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("design contract schema_version must be 1")
    provenance = _object(value.get("design"), "design provenance")
    if provenance.get("origin") not in ("fixture", "figma_mcp", "figma_export"):
        raise ValueError("design.origin must be fixture, figma_mcp, or figma_export")
    for key in ("file_key", "node_id", "revision"):
        _text(provenance.get(key), f"design.{key}")
    scopes = _list(value.get("scope"), "scope")
    requirements = _list(value.get("requirements"), "requirements")
    visual = "visual" in scopes or any(
        isinstance(requirement, dict) and requirement.get("kind") == "pixels"
        for requirement in requirements
    )
    if visual or "reference_image" in provenance:
        _text(provenance.get("reference_image"), "design.reference_image")
    if visual or "reference_scale" in provenance:
        _number(provenance.get("reference_scale"), "design.reference_scale", positive=True)
    for receipt in _list(provenance.get("evidence"), "design.evidence"):
        _text(receipt, "design.evidence item")
    viewport = _object(value.get("viewport"), "viewport")
    for key in ("width_dp", "height_dp", "figma_units_per_dp"):
        _number(viewport.get(key), f"viewport.{key}", positive=True)
    for scope in scopes:
        _text(scope, "scope item")

    node_ids = set()
    for node in _list(value.get("nodes"), "nodes"):
        _object(node, "node")
        node_id = _text(node.get("id"), "node.id")
        if node_id in node_ids:
            raise ValueError(f"duplicate design node id: {node_id}")
        node_ids.add(node_id)
        _bounds(node.get("bounds_dp"), f"node {node_id} bounds_dp")

    requirement_ids = set()
    for requirement in requirements:
        _object(requirement, "requirement")
        requirement_id = _text(requirement.get("id"), "requirement.id")
        if requirement_id in requirement_ids:
            raise ValueError(f"duplicate requirement id: {requirement_id}")
        requirement_ids.add(requirement_id)
        kind = _text(requirement.get("kind"), "requirement.kind")
        node_id = _text(requirement.get("node_id"), "requirement.node_id")
        if node_id not in node_ids:
            raise ValueError(f"requirement {requirement_id} references unknown node: {node_id}")
        if "tolerance_dp" in requirement:
            _number(requirement["tolerance_dp"], "requirement.tolerance_dp", nonnegative=True)
        if "state" in requirement:
            _text(requirement["state"], "requirement.state")
        if kind == "property":
            _text(requirement.get("property"), "requirement.property")
            if "expected" not in requirement:
                raise ValueError("property requirement must contain expected")
        elif kind == "parent":
            for key in ("parent_tag", "hierarchy_kind"):
                _text(requirement.get(key), f"requirement.{key}")
        elif kind == "transition":
            for key in ("from_state", "action", "action_tag", "to_state"):
                _text(requirement.get(key), f"requirement.{key}")
            condition = _object(requirement.get("postcondition"), "transition postcondition")
            for key in ("tag", "property"):
                _text(condition.get(key), f"postcondition.{key}")
            if "expected" not in condition:
                raise ValueError("transition postcondition must contain expected")
        # Future requirement kinds remain intact for the evaluator to mark
        # inconclusive. Preparation never assigns requirement verdicts.
    return node_ids


def _safe_source(source):
    if not isinstance(source, str) or not source or "\\" in source or ":" in source or "\x00" in source:
        return False
    path = PurePosixPath(source)
    return (not path.is_absolute() and path.suffix == ".kt"
            and all(part not in ("", ".", "..") for part in source.split("/")))


def _issue(issues, code, message, node_id=None, mapping_index=None):
    issue = {"code": code, "message": message}
    if isinstance(node_id, str) and node_id:
        issue["node_id"] = node_id
    if mapping_index is not None:
        issue["mapping_index"] = mapping_index
    issues.append(issue)


def _source_provenance(mapping, root, issues, index):
    node_id = mapping.get("node_id")
    mapping["source_exists"] = False
    candidate = root / mapping["source"]
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError) as exc:
        mapping["supported"] = False
        _issue(issues, "unsafe_source", f"Source cannot be resolved safely: {exc}", node_id, index)
        return
    if not resolved.is_relative_to(root):
        mapping["supported"] = False
        _issue(issues, "unsafe_source", "Source resolves outside source_root", node_id, index)
        return
    if not resolved.is_file():
        _issue(issues, "source_missing", "Mapped Kotlin source is unavailable or is not a file", node_id, index)
        return
    try:
        content = resolved.read_bytes()
    except OSError as exc:
        _issue(issues, "source_unavailable", f"Mapped Kotlin source could not be read: {exc}", node_id, index)
        return
    mapping["source_exists"] = True
    mapping["source_sha256"] = hashlib.sha256(content).hexdigest()


def _prepare_mappings(raw, node_ids, root, issues):
    if raw is None:
        return {"schema_version": 1, "mappings": []}
    _json_value(raw, "code_connect")
    if not isinstance(raw, dict):
        _issue(issues, "invalid_code_connect", "Code Connect input must be an object")
        return {"schema_version": 1, "mappings": [], "raw": copy.deepcopy(raw)}
    result = copy.deepcopy(raw)
    schema_valid = type(result.get("schema_version")) is int and result["schema_version"] == 1
    if not schema_valid:
        _issue(issues, "invalid_code_connect", "Code Connect schema_version must be 1")
    mappings = result.get("mappings")
    if not isinstance(mappings, list):
        _issue(issues, "invalid_code_connect", "Code Connect mappings must be a list")
        if "mappings" in result:
            result["raw_mappings"] = mappings
        result["mappings"] = []
        return result
    counts = Counter(item.get("node_id") for item in mappings
                     if isinstance(item, dict) and isinstance(item.get("node_id"), str))
    for index, item in enumerate(mappings):
        if not isinstance(item, dict):
            mappings[index] = {"raw": item, "supported": False}
            _issue(issues, "invalid_mapping", "Code Connect mapping must be an object", mapping_index=index)
            continue
        # A source root requests a fresh check. Without one, preserve recorded
        # source metadata as provenance rather than claiming a new file check.
        if root is not None:
            item.pop("source_exists", None)
            item.pop("source_sha256", None)
        item["supported"] = schema_valid
        node_id = item.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            item["supported"] = False
            _issue(issues, "invalid_mapping", "Mapping needs a nonempty node_id", mapping_index=index)
        elif node_id not in node_ids:
            item["supported"] = False
            _issue(issues, "unknown_mapping_node", "Mapping references an unknown design node", node_id, index)
        if isinstance(node_id, str) and counts[node_id] > 1:
            item["supported"] = False
            _issue(issues, "ambiguous_mapping", "Multiple mappings reference the same node", node_id, index)
        if item.get("framework") not in ("compose", "jetpack-compose"):
            item["supported"] = False
            _issue(issues, "incompatible_framework", "Mapping framework is not Compose", node_id, index)
        if not isinstance(item.get("component"), str) or not item["component"].strip():
            item["supported"] = False
            _issue(issues, "invalid_mapping", "Mapping needs an explicit component", node_id, index)
        if not _safe_source(item.get("source")):
            item["supported"] = False
            _issue(issues, "unsafe_source", "Mapping source must be a project-relative .kt path without traversal", node_id, index)
        if item["supported"] and root is not None:
            _source_provenance(item, root, issues, index)
    return result


def prepare_design(design: dict, code_connect: dict | None = None,
                   source_root: Path | None = None) -> dict:
    """Return a validated copy with explicit mapping and provenance issues.

    Invalid design contracts raise ValueError. An unavailable source root
    raises OSError. Optional missing or incompatible Code Connect evidence
    produces issues so other requirements can still be assessed.
    """
    node_ids = _validate_design(design)
    if code_connect is None:
        code_connect = design.get("code_connect")
    root = None
    if source_root is not None:
        try:
            root = Path(source_root).resolve(strict=True)
        except TypeError as exc:
            raise ValueError("source_root must be a filesystem path") from exc
        except RuntimeError as exc:
            raise OSError(f"source_root cannot be resolved: {source_root}") from exc
        if not root.is_dir():
            raise NotADirectoryError(f"source_root is not a directory: {root}")
    result = copy.deepcopy(design)
    issues = []
    result["code_connect"] = _prepare_mappings(code_connect, node_ids, root, issues)
    supported_ids = {mapping.get("node_id") for mapping in result["code_connect"]["mappings"]
                     if mapping.get("supported")}
    required_ids = {requirement["node_id"] for requirement in result["requirements"]
                    if requirement["kind"] == "code_connect"}
    for node_id in sorted(required_ids - supported_ids):
        _issue(issues, "missing_mapping", "No unambiguous supported Compose mapping is available", node_id)
    result["issues"] = issues
    return result
