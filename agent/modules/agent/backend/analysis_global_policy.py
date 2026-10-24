"""Source-bound species policy for global morphometry, never filename inference."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path


def policy():
    path = (
        Path(__file__).resolve().parent.parent
        / "knowledge_analysis/global_morphometry_species_policy.json"
    )
    raw = path.read_bytes()
    expected = path.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Global species policy digest mismatch")
    return json.loads(raw), expected


def is_macaque(species):
    body, _ = policy()
    declared = str(species or "").strip().casefold()
    return declared in {name.casefold() for name in body["species_aliases"]}


def specialize(spec, entries):
    """Specialize only the registered single-macaque global method."""
    if spec.get("method_id") != "method:v15:global_morphometry" or len(entries) != 1:
        return spec
    if not is_macaque(entries[0].get("species_declared")):
        return spec
    body, sha = policy()
    result = copy.deepcopy(spec)
    result.update(copy.deepcopy(body["requirements"]))
    result["species_policy_sha256"] = sha
    result["species_policy"] = "macaque_direct_native"
    return result
