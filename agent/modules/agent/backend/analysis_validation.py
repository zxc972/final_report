"""Independent, bounded artifact checking outside the model loop.

Model-written rules define a structural output contract, not an independent gold
standard. Optional numerical references are configured by the server via the
constructor; their values are never returned in validation feedback.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import struct
import zlib
from pathlib import Path
from typing import Any

MANIFEST_NAME = "analysis_manifest.json"
MANIFEST_VERSION = "primatex.analysis_manifest.v1"
REFERENCE_VERSION = "primatex.analysis_reference.v1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACTS = 32
MAX_ROWS = 100000
MAX_COLUMNS = 256
MAX_JSON_NODES = 100000
MAX_JSON_DEPTH = 32
MAX_PNG_BYTES_DECODED = 64 * 1024 * 1024
MAX_PNG_PIXELS = 16 * 1024 * 1024

MANIFEST_SCHEMA = {
    "schema_version": MANIFEST_VERSION,
    "artifacts": [
        {
            "path": "stats.csv", "kind": "csv",
            "columns": ["region", "mean"], "row_count": 2,
            "finite_columns": ["mean"], "unique_columns": ["region"],
        },
        {"path": "summary.json", "kind": "json", "required_keys": ["methods", "limitations"]},
        {"path": "plot.png", "kind": "png"},
    ],
    "note": "Example only. Rules validate structure and declared values, not scientific correctness.",
}


def _relative_path(root: Path, value: Any, *, must_exist: bool = True) -> Path:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError("Artifact path must be a bounded relative string")
    if "\\" in value or ":" in value or any(ord(char) < 32 or ord(char) == 127 for char in value) or value.startswith("/"):
        raise ValueError("Absolute or platform-specific paths are not permitted")
    components = value.split("/")
    if any(part in ("", ".", "..") for part in components):
        raise ValueError("Path traversal or empty path components are not permitted")
    candidate = root.joinpath(*components)
    current = root
    for component in components:
        current = current / component
        if current.is_symlink():
            raise ValueError("Symlink artifacts are not permitted")
    resolved = candidate.resolve(strict=must_exist)
    if not resolved.is_relative_to(root):
        raise ValueError("Artifact path escapes its work directory")
    if must_exist and not resolved.is_file():
        raise ValueError("Artifact must be a regular file")
    return resolved


def _read_bytes(path: Path, limit: int, root: Path | None = None) -> bytes:
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    parents: list[int] = []
    try:
        if root is not None and os.name == "posix" and os.open in os.supports_dir_fd:
            # Open each parent without following links: a model can replace a
            # directory between path validation and reading an artifact.
            parts = path.relative_to(root).parts
            if not parts or any(part in ("", ".", "..") for part in parts):
                raise ValueError("Read path must stay beneath its root")
            directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
            parent = os.open(root, directory_flags)
            parents.append(parent)
            for part in parts[:-1]:
                parent = os.open(part, directory_flags, dir_fd=parent)
                parents.append(parent)
            before_open = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(before_open.st_mode):
                raise ValueError("Only regular files can be validated")
            descriptor = os.open(parts[-1], flags, dir_fd=parent)
        else:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("Only regular files can be validated")
            descriptor = os.open(path, flags)
    finally:
        for parent in reversed(parents):
            os.close(parent)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Only regular files can be validated")
        if before.st_size > limit:
            raise ValueError("File exceeds the bounded read limit")
        raw = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if len(raw) > limit:
        raise ValueError("File exceeds the bounded read limit")
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("Artifact changed during validation")
    if not raw:
        raise ValueError("Artifact is empty")
    return raw


def _parse_json(raw: bytes) -> Any:
    def bad_constant(value: str) -> Any:
        raise ValueError("Non-finite JSON number")
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON object key")
            result[key] = value
        return result
    try:
        obj = json.loads(
            raw.decode("utf-8-sig"), parse_constant=bad_constant,
            object_pairs_hook=unique_object,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid JSON artifact") from exc
    pending = [(obj, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if visited > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("JSON artifact exceeds the complexity limit")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("scientific_validated", "scientifically_verified") and child is True:
                    raise ValueError("Model-authored scientific validation claims are not accepted")
                pending.append((child, depth + 1))
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return obj


def _string_list(value: Any, name: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_COLUMNS:
        raise ValueError(name + " must be a bounded string list")
    if any(not isinstance(item, str) or not item or len(item) > 200 for item in value):
        raise ValueError(name + " contains an invalid column/key")
    if len(set(value)) != len(value) or (nonempty and not value):
        raise ValueError(name + " must contain unique nonempty values")
    return value


def _count(value: Any, name: str, limit: int = MAX_ROWS) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= limit:
        raise ValueError(name + " must be a bounded nonnegative integer")
    return value


def _check_rows(spec: dict[str, Any], rows: int) -> None:
    if "row_count" in spec and rows != _count(spec["row_count"], "row_count"):
        raise ValueError("Row count does not match the declared contract")
    minimum = spec.get("min_rows", 0 if spec.get("row_count") == 0 else 1)
    if rows < _count(minimum, "min_rows"):
        raise ValueError("Table has fewer rows than required")
    if rows > _count(spec.get("max_rows", MAX_ROWS), "max_rows"):
        raise ValueError("Table has too many rows")


def _shape(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    if not value:
        return [0]
    first = _shape(value[0])
    if any(_shape(child) != first for child in value[1:]):
        raise ValueError("JSON array is not rectangular")
    return [len(value)] + first


def _check_shape(spec: dict[str, Any], actual: list[int]) -> None:
    if "shape" not in spec:
        return
    expected = spec["shape"]
    if not isinstance(expected, list) or len(expected) > MAX_JSON_DEPTH:
        raise ValueError("shape must be a bounded dimension list")
    expected = [_count(item, "shape dimension", MAX_JSON_NODES) for item in expected]
    if actual != expected:
        raise ValueError("Shape does not match the declared contract")


def _csv_table(raw: bytes, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = next(reader)
        if not headers or len(headers) > MAX_COLUMNS or any(not key for key in headers):
            raise ValueError("CSV header is empty or too wide")
        if len(set(headers)) != len(headers):
            raise ValueError("CSV has duplicate column names")
        if any(len(key) > 200 for key in headers):
            raise ValueError("CSV column name is too long")
        rows = []
        for values in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError("CSV exceeds the row limit")
            if len(values) != len(headers):
                raise ValueError("CSV contains a ragged row")
            rows.append(dict(zip(headers, values)))
        return headers, rows
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise ValueError("Invalid CSV artifact") from exc


def _validate_csv(spec: dict[str, Any], raw: bytes) -> tuple[dict[str, Any], Any]:
    headers, rows = _csv_table(raw, "\t" if spec["kind"] == "tsv" else ",")
    _check_rows(spec, len(rows))
    _check_shape(spec, [len(rows), len(headers)])
    if "columns" in spec:
        expected = _string_list(spec["columns"], "columns", nonempty=True)
        if not set(expected).issubset(headers):
            raise ValueError("Required CSV columns are missing")
        if spec.get("exact_columns", False) and headers != expected:
            raise ValueError("CSV columns/order do not exactly match the contract")
    elif spec.get("exact_columns"):
        raise ValueError("exact_columns requires columns")
    if "exact_columns" in spec and not isinstance(spec["exact_columns"], bool):
        raise ValueError("exact_columns must be boolean")
    finite = _string_list(spec.get("finite_columns", []), "finite_columns")
    unique = _string_list(spec.get("unique_columns", []), "unique_columns")
    ranges = spec.get("numeric_ranges", {})
    if not isinstance(ranges, dict) or len(ranges) > MAX_COLUMNS:
        raise ValueError("numeric_ranges must be a bounded object")
    if not set(finite + unique + list(ranges)).issubset(headers):
        raise ValueError("A validation rule names a missing CSV column")
    seen: set[tuple[str, ...]] = set()
    numeric_cells = 0
    bounds: dict[str, tuple[float | None, float | None]] = {}
    for column, rule in ranges.items():
        if not isinstance(rule, dict) or set(rule) - {"min", "max"}:
            raise ValueError("Numeric range supports only min/max")
        low, high = rule.get("min"), rule.get("max")
        for bound in (low, high):
            if bound is not None and (
                isinstance(bound, bool) or not isinstance(bound, (int, float))
                or not math.isfinite(bound)
            ):
                raise ValueError("Numeric bounds must be finite numbers")
        if low is not None and high is not None and low > high:
            raise ValueError("Numeric range is reversed")
        bounds[column] = (low, high)
    for row in rows:
        if unique:
            key = tuple(row[column] for column in unique)
            if any(not value.strip() for value in key) or key in seen:
                raise ValueError("CSV key is missing or duplicated")
            seen.add(key)
        for column, text in row.items():
            try:
                value = float(text)
            except (ValueError, OverflowError):
                if column in finite or column in bounds:
                    raise ValueError("CSV column must be numeric and finite: " + column)
                continue
            numeric_cells += 1
            if not math.isfinite(value):
                raise ValueError("CSV contains a non-finite numeric value: " + column)
            if column in bounds:
                low, high = bounds[column]
                if (low is not None and value < low) or (high is not None and value > high):
                    raise ValueError("CSV value violates a declared range: " + column)
    return {
        "row_count": len(rows), "columns": headers,
        "numeric_cells_checked": numeric_cells,
        "rules_trust": "model_declared_not_independent_gold",
    }, (headers, rows)


def _validate_json(spec: dict[str, Any], raw: bytes) -> tuple[dict[str, Any], Any]:
    obj = _parse_json(raw)
    keys = _string_list(spec.get("required_keys", []), "required_keys")
    if keys and (not isinstance(obj, dict) or not set(keys).issubset(obj)):
        raise ValueError("Required JSON keys are missing")
    data = obj
    if "data_key" in spec:
        key = spec["data_key"]
        if not isinstance(key, str) or not isinstance(obj, dict) or key not in obj:
            raise ValueError("JSON data_key is missing")
        data = obj[key]
    if any(key in spec for key in ("row_count", "min_rows", "max_rows")):
        if not isinstance(data, list):
            raise ValueError("JSON row checks require an array")
        _check_rows(spec, len(data))
    if "finite" in spec and not isinstance(spec["finite"], bool):
        raise ValueError("finite must be boolean")
    if spec.get("finite"):
        pending = [data]
        numeric_leaves = 0
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("JSON finite rule requires numeric finite leaves")
            else:
                numeric_leaves += 1
        if not numeric_leaves:
            raise ValueError("JSON finite rule requires numeric values")
    actual_shape = _shape(data) if "shape" in spec else None
    if actual_shape is not None:
        _check_shape(spec, actual_shape)
    return {
        "json_type": type(obj).__name__,
        "shape": actual_shape,
        "finite_json_numbers": True,
        "rules_trust": "model_declared_not_independent_gold",
    }, obj


def _validate_png(spec: dict[str, Any], raw: bytes) -> tuple[dict[str, Any], None]:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Invalid PNG signature")
    offset = 8
    header = None
    palette = None
    image_data = bytearray()
    ended = False
    chunks = 0
    while offset < len(raw):
        chunks += 1
        if chunks > 100000 or offset + 12 > len(raw):
            raise ValueError("PNG is truncated or has too many chunks")
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        tag = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError("PNG chunk is truncated")
        data = raw[offset + 8:offset + 8 + length]
        crc = struct.unpack(">I", raw[offset + 8 + length:end])[0]
        if zlib.crc32(tag + data) & 0xFFFFFFFF != crc:
            raise ValueError("PNG chunk checksum failed")
        if chunks == 1 and tag != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if tag == b"IHDR":
            if header is not None or length != 13:
                raise ValueError("Invalid PNG header")
            header = struct.unpack(">IIBBBBB", data)
        elif tag == b"PLTE":
            if not length or length % 3 or length > 768:
                raise ValueError("Invalid PNG palette")
            palette = data
        elif tag == b"IDAT":
            image_data.extend(data)
        elif tag == b"IEND":
            if length != 0 or end != len(raw):
                raise ValueError("Invalid PNG end")
            ended = True
            break
        offset = end
    if header is None or not ended or not image_data:
        raise ValueError("PNG is missing required image chunks")
    width, height, depth, color, compression, filtering, interlace = header
    allowed_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (
        not width or not height or width * height > MAX_PNG_PIXELS
        or depth not in allowed_depths.get(color, set())
        or compression != 0 or filtering != 0 or interlace not in (0, 1)
    ):
        raise ValueError("Unsupported or invalid PNG dimensions/header")
    if color == 3 and palette is None:
        raise ValueError("Indexed PNG is missing its palette")
    decompressor = zlib.decompressobj()
    try:
        decoded = decompressor.decompress(bytes(image_data), MAX_PNG_BYTES_DECODED + 1)
    except zlib.error as exc:
        raise ValueError("PNG image stream is invalid") from exc
    if len(decoded) > MAX_PNG_BYTES_DECODED or decompressor.unconsumed_tail:
        raise ValueError("PNG decompression exceeds the limit")
    if not decompressor.eof or decompressor.unused_data:
        raise ValueError("PNG compressed image stream is incomplete")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    passes = [(0, 0, 1, 1)] if interlace == 0 else [
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8),
        (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
    ]
    cursor = 0
    for x, y, dx, dy in passes:
        pass_width = max(0, (width - x + dx - 1) // dx)
        pass_height = max(0, (height - y + dy - 1) // dy)
        if not pass_width or not pass_height:
            continue
        stride = (pass_width * channels * depth + 7) // 8 + 1
        end = cursor + pass_height * stride
        if end > len(decoded) or any(decoded[i] > 4 for i in range(cursor, end, stride)):
            raise ValueError("PNG scanline data is invalid")
        cursor = end
    if cursor != len(decoded):
        raise ValueError("PNG scanline length is invalid")
    _check_shape(spec, [height, width])
    return {
        "width": width, "height": height, "png_stream_checked": True,
        "visual_quality": "not_evaluated",
    }, None


_RULES = {
    "csv": {"columns", "exact_columns", "row_count", "min_rows", "max_rows",
            "shape", "finite_columns", "unique_columns", "numeric_ranges"},
    "tsv": {"columns", "exact_columns", "row_count", "min_rows", "max_rows",
            "shape", "finite_columns", "unique_columns", "numeric_ranges"},
    "json": {"required_keys", "data_key", "shape", "row_count", "min_rows", "max_rows", "finite"},
    "png": {"shape"},
    "text": {"min_chars", "max_chars"},
    "markdown": {"min_chars", "max_chars"},
}
_METADATA = {"path", "kind", "title", "description", "units"}


class ArtifactValidator:
    """Validate declared outputs; optional reference_manifest is server-owned.

    Reference manifest:
      {"schema_version": "primatex.analysis_reference.v1", "tables": [{
        "artifact_path": "stats.csv", "reference_path": "reference.csv",
        "key_columns": ["region"], "value_columns": ["mean"],
        "exact_columns": ["count"], "rtol": 1e-7, "atol": 1e-9
      }]}
    reference_path is relative to the trusted manifest directory. Neither the
    reference manifest nor its tables may live in the model work directory.
    """

    def __init__(self, reference_manifest: Path | None = None) -> None:
        self.reference_manifest = Path(reference_manifest) if reference_manifest is not None else None

    def validate(self, workdir: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "valid": False, "passed": False,
            "status": "artifact_contract_failed",
            "validation_scope": "structure_and_declared_checks",
            "scientific_status": "not_evaluated",
            "independent_numeric_status": "not_configured",
            "checks": [], "errors": [], "artifacts": [],
            "limits": [
                "Model-declared rows/columns/ranges are structural checks, not independent gold.",
                "A numerical reference pass does not certify method applicability, anatomy, prose, or visual quality.",
                "Only declared artifacts are checked; this validator is not a code sandbox.",
            ],
        }
        tables: dict[str, Any] = {}
        try:
            raw_root = Path(workdir)
            if raw_root.is_symlink():
                raise ValueError("Work directory must not be a symlink")
            root = raw_root.resolve(strict=True)
            if not root.is_dir():
                raise ValueError("Work directory is unavailable")
            path = _relative_path(root, MANIFEST_NAME)
            manifest = _parse_json(_read_bytes(path, MAX_MANIFEST_BYTES, root))
            if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_VERSION:
                raise ValueError("Unsupported analysis manifest schema_version")
            if any(key in manifest for key in ("reference_manifest", "reference_path", "independent_reference")):
                raise ValueError("Independent references must be configured by the server")
            specs = manifest.get("artifacts")
            if not isinstance(specs, list) or not 1 <= len(specs) <= MAX_ARTIFACTS:
                raise ValueError("Manifest must declare between 1 and 32 artifacts")
            seen: set[str] = set()
            for spec in specs:
                label = spec.get("path", "<invalid>") if isinstance(spec, dict) else "<invalid>"
                try:
                    if not isinstance(spec, dict):
                        raise ValueError("Artifact specification must be an object")
                    kind = spec.get("kind")
                    if kind not in _RULES:
                        raise ValueError("Unsupported artifact kind")
                    if set(spec) - (_RULES[kind] | _METADATA):
                        raise ValueError("Unsupported artifact validation fields")
                    file_path = _relative_path(root, spec.get("path"))
                    identity = file_path.relative_to(root).as_posix()
                    if identity.casefold() in seen or identity == MANIFEST_NAME:
                        raise ValueError("Duplicate artifact or manifest declared as an artifact")
                    seen.add(identity.casefold())
                    raw = _read_bytes(file_path, MAX_ARTIFACT_BYTES, root)
                    if kind in ("csv", "tsv"):
                        details, table = _validate_csv(spec, raw)
                        tables[identity] = table
                    elif kind == "json":
                        details, _ = _validate_json(spec, raw)
                    elif kind in ("text", "markdown"):
                        try:
                            text = raw.decode("utf-8-sig")
                        except UnicodeError as exc:
                            raise ValueError("Text artifact must be valid UTF-8") from exc
                        minimum, maximum = spec.get("min_chars", 1), spec.get("max_chars", MAX_ARTIFACT_BYTES)
                        if (type(minimum) is not int or type(maximum) is not int
                                or not 1 <= minimum <= maximum <= MAX_ARTIFACT_BYTES):
                            raise ValueError("Invalid text character bounds")
                        if "\x00" in text or not minimum <= len(text.strip()) <= maximum:
                            raise ValueError("Text artifact is empty, binary or outside declared bounds")
                        details = {"characters": len(text), "content_validation": "UTF-8 and nonempty; prose correctness not evaluated"}
                    else:
                        details, _ = _validate_png(spec, raw)
                    result["artifacts"].append({
                        "path": identity, "kind": kind, "bytes": len(raw),
                        "sha256": hashlib.sha256(raw).hexdigest(), **details,
                    })
                    result["checks"].append({"artifact": identity, "check": "artifact_contract", "passed": True})
                except (OSError, ValueError, TypeError, RecursionError) as exc:
                    result["checks"].append({"artifact": str(label)[:240], "check": "artifact_contract", "passed": False})
                    result["errors"].append({"artifact": str(label)[:240], "message": str(exc)[:500]})
            if self.reference_manifest is not None:
                result["validation_scope"] = "structure_declared_rules_and_server_reference"
                if result["errors"]:
                    result["independent_numeric_status"] = "not_evaluated"
                else:
                    self._check_references(root, tables, result)
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            result["errors"].append({"artifact": MANIFEST_NAME, "message": str(exc)[:500]})
        result["valid"] = result["passed"] = bool(result["artifacts"]) and not result["errors"]
        if result["passed"]:
            result["status"] = "artifact_contract_pass"
        return result

    def _check_references(self, root: Path, tables: dict[str, Any], result: dict[str, Any]) -> None:
        result["independent_numeric_status"] = "failed"
        try:
            configured = self.reference_manifest
            assert configured is not None
            if configured.is_symlink():
                raise ValueError("Trusted reference manifest must not be a symlink")
            reference_manifest = configured.resolve(strict=True)
            if reference_manifest.is_relative_to(root):
                raise ValueError("Trusted references must be outside the model work directory")
            config = _parse_json(_read_bytes(reference_manifest, MAX_MANIFEST_BYTES, reference_manifest.parent))
            if not isinstance(config, dict) or config.get("schema_version") != REFERENCE_VERSION:
                raise ValueError("Unsupported trusted reference schema")
            specs = config.get("tables")
            if not isinstance(specs, list) or not 1 <= len(specs) <= MAX_ARTIFACTS:
                raise ValueError("Trusted references must declare bounded table checks")
            for spec in specs:
                if not isinstance(spec, dict):
                    raise ValueError("Invalid trusted table check")
                artifact = spec.get("artifact_path")
                if not isinstance(artifact, str) or artifact not in tables:
                    raise ValueError("Trusted check names an undeclared or invalid table")
                reference = _relative_path(reference_manifest.parent, spec.get("reference_path"))
                if reference.is_relative_to(root):
                    raise ValueError("Reference tables must be outside the model work directory")
                expected_headers, expected_rows = _csv_table(
                    _read_bytes(reference, MAX_ARTIFACT_BYTES, reference_manifest.parent),
                    "\t" if spec.get("reference_kind") == "tsv" else ",",
                )
                actual_headers, actual_rows = tables[artifact]
                keys = _string_list(spec.get("key_columns"), "reference key_columns", nonempty=True)
                values = _string_list(spec.get("value_columns"), "reference value_columns", nonempty=True)
                exact = _string_list(spec.get("exact_columns", []), "reference exact_columns")
                required = set(keys + values + exact)
                if not required.issubset(expected_headers) or not required.issubset(actual_headers):
                    raise ValueError("Trusted comparison columns are missing")
                rtol, atol = spec.get("rtol", 1e-7), spec.get("atol", 1e-9)
                for tolerance in (rtol, atol):
                    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
                        raise ValueError("Trusted numeric tolerances must be finite and nonnegative")
                def keyed(rows: list[dict[str, str]]) -> dict[tuple[str, ...], dict[str, str]]:
                    index = {}
                    for row in rows:
                        key = tuple(row[column] for column in keys)
                        if any(not cell.strip() for cell in key) or key in index:
                            raise ValueError("Reference comparison requires unique nonempty keys")
                        index[key] = row
                    return index
                expected, actual = keyed(expected_rows), keyed(actual_rows)
                if not expected or expected.keys() != actual.keys():
                    raise ValueError("Independent table key set does not match")
                mismatched = set()
                for key, row in expected.items():
                    for column in exact:
                        if row[column] != actual[key][column]:
                            mismatched.add(column)
                    for column in values:
                        try:
                            left, right = float(row[column]), float(actual[key][column])
                        except (ValueError, OverflowError):
                            mismatched.add(column)
                            continue
                        if not math.isfinite(left) or not math.isfinite(right) or abs(left - right) > atol + rtol * abs(left):
                            mismatched.add(column)
                if mismatched:
                    raise ValueError("Independent numeric comparison failed for columns: " + ", ".join(sorted(mismatched)))
                result["checks"].append({
                    "artifact": artifact, "check": "server_reference_table",
                    "passed": True, "matched_rows": len(expected),
                })
            result["independent_numeric_status"] = "passed"
        except (OSError, ValueError, TypeError, RecursionError, AssertionError) as exc:
            result["checks"].append({"check": "server_reference_table", "passed": False})
            result["errors"].append({"artifact": "server_reference", "message": str(exc)[:500]})

