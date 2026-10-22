"""Explicit sourced human lobes; no label-name inference across species."""

from __future__ import annotations
import re
from .analysis_product_planner import load_knowledge


def resolve_lobes(entry, atlas_name, regions, names, tools=None):
    tokens = [regions] if isinstance(regions, str) else regions
    aliases = {
        name + suffix: name
        for name in (
            "frontal",
            "temporal",
            "parietal",
            "occipital",
            "cingulate",
            "insula",
        )
        for suffix in ("", " lobe", " cortex")
    }
    aliases.update(
        {"额叶": "frontal", "颞叶": "temporal", "顶叶": "parietal", "枕叶": "occipital"}
    )
    # A literal label on this annotation has precedence over a broader group
    # alias. In particular, the aparc parcel "insula" is not a request to apply
    # human lobar grouping to a nonhuman reconstruction.
    actual_names = {name.casefold() for name in names}
    requested = [
        (
            None
            if token.casefold().strip() in actual_names
            else aliases.get(token.lower().strip())
        )
        for token in tokens
    ]
    if not any(requested):
        return regions, [], None
    if entry.get("species_declared") != "human":
        return (
            regions,
            [],
            (
                "Missing corresponding CHARM parcellation and subject-mesh/space binding; "
                "human-named aparc labels cannot establish macaque lobes. "
                "Species remains declaration-only; CHARM is defined in NMT v2 space."
            ),
        )
    atlas = (
        "DKT"
        if atlas_name
        in {"aparc.DKTatlas", "aparc.DKTatlas40", "aparc.DKTatlas31", "DKT"}
        else "DK" if atlas_name in {"aparc", "DK"} else None
    )
    if atlas is None:
        return (
            regions,
            [],
            "No sourced human lobar mapping for this explicit annotation protocol",
        )
    mapping, sha = load_knowledge("lobar_mapping", tools)
    expanded, evidence = [], []
    for token, lobe in zip(tokens, requested):
        if lobe is None:
            expanded.append(token)
            continue
        row = next(
            row
            for row in mapping["records"]
            if row["atlas"] == atlas and row["region"] == lobe
        )
        absent = set(row["labels"]) - set(names)
        if absent:
            return (
                regions,
                [],
                "Required labels missing from declared protocol: "
                + ", ".join(sorted(absent)),
            )
        expanded.extend(row["labels"])
        evidence.append(
            {
                "kind": "lobar_name_set",
                "atlas": atlas,
                "region": lobe,
                "labels": row["labels"],
                "source_url": row["source_url"],
                "author_code_url": row["author_code_url"],
                "mapping_sha256": sha,
                "adaptation": row["adaptation"],
            }
        )
    return list(dict.fromkeys(expanded)), evidence, None
