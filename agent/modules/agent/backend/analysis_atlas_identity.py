"""Exact source-backed naming and explicit requested-atlas selection."""
from pathlib import Path
import hashlib
import json
import re


def mappings():
    path = Path(__file__).resolve().parent.parent / "knowledge_analysis/atlas_identifiers_r13.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Atlas identifier mapping digest mismatch")
    return json.loads(raw)["mappings"]


def identify(stem):
    return next((dict(row) for row in mappings() if row["file_stem"] == stem), None)


def requested(regions, task_request=""):
    tokens = [regions] if isinstance(regions, str) else regions
    for token in [*(tokens or []), task_request]:
        direct = identify(token)
        if direct:
            return direct["canonical_name"]
        for name in ("DKT", "Destrieux", "DK"):
            if re.search(r"(?<![A-Za-z0-9])" + name + r"(?![A-Za-z0-9])", token, re.I):
                return name
    return None
