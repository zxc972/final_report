"""Mechanical metadata for real outputs; the existing validator remains authoritative.

No analysis algorithm, sample selection, numeric reference, imputation or output
repair lives here. Explicit caller constraints are never replaced by observations.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Any
from .analysis_validation import (
    MANIFEST_NAME, MANIFEST_VERSION, MAX_ARTIFACTS, MAX_ARTIFACT_BYTES,
    MAX_MANIFEST_BYTES, _RULES, _METADATA, _relative_path, _read_bytes,
    _validate_csv, _validate_json, _validate_png,
)


def derive_manifest(root: Path, artifacts: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Check explicit constraints first, fill only missing mechanical fields."""
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= MAX_ARTIFACTS:
        raise ValueError('Declare 1..32 actual output artifacts')
    root = Path(root).resolve(strict=True)
    specs = copy.deepcopy(artifacts)
    seen: set[str] = set()
    observed: dict[str, Any] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            raise ValueError('Each artifact needs a path and kind')
        kind = spec.get('kind')
        if not isinstance(kind, str) or kind not in _RULES:
            raise ValueError('Unsupported artifact kind')
        if set(spec) - (_RULES[kind] | _METADATA):
            raise ValueError('Unsupported artifact declaration fields')
        path = _relative_path(root, spec.get('path'))
        identity = path.relative_to(root).as_posix()
        if identity.casefold() in seen or identity == MANIFEST_NAME:
            raise ValueError('Duplicate artifact or manifest declared as output')
        seen.add(identity.casefold())
        raw = _read_bytes(path, MAX_ARTIFACT_BYTES, root)
        fill: dict[str, Any] = {}
        details: dict[str, Any] = {}
        if kind in ('csv', 'tsv'):
            # Existing parsing and all explicit row/column/range/finite checks.
            details, _ = _validate_csv(spec, raw)
            fill = {'columns': details['columns'], 'row_count': details['row_count'],
                    'shape': [details['row_count'], len(details['columns'])]}
        elif kind == 'png':
            # Existing CRC/stream/decompression bounds and explicit shape checks.
            details, _ = _validate_png(spec, raw)
            fill = {'shape': [details['height'], details['width']]}
        elif kind == 'json':
            details, _ = _validate_json(spec, raw)
        elif kind in ('text', 'markdown'):
            text = raw.decode('utf-8-sig')
            if not text.strip() or '\x00' in text:
                raise ValueError('Text artifact is empty or contains NUL')
            details = {'characters': len(text)}
            # Caller min_chars/max_chars remain unchanged for final validator.
        added = []
        for key, value in fill.items():
            if key not in spec:
                spec[key] = value
                added.append(key)
        observed[identity] = {'derived_fields': added, 'observed': details}
    manifest = {'schema_version': MANIFEST_VERSION, 'artifacts': specs,
                'metadata_origin': 'actual_files_only_missing_mechanical_fields'}
    if len(json.dumps(manifest, ensure_ascii=False).encode('utf-8')) > MAX_MANIFEST_BYTES:
        raise ValueError('Manifest is too large')
    return manifest, observed
