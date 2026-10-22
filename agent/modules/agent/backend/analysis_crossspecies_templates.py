"""Seven parameterized, deterministic cross-species checks over host observations."""

from __future__ import annotations

import math
import re
from statistics import NormalDist


def result(verdict, reason, evidence=None, **tags):
    return {"verdict": verdict, "reason": reason, "evidence": evidence or {}, **tags}


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def species_atlas(parameters, environment, severity="hard"):
    bindings = environment.get("atlas_bindings")
    if bindings:
        expected = set(environment.get("species", []))
        covered = {row.get("species") for row in bindings}
        if covered != expected:
            return result(
                "block",
                "Atlas bindings do not cover all declared species",
                {"expected": sorted(expected), "covered": sorted(covered)},
            )
        checks = [
            species_atlas(
                parameters,
                {
                    **environment,
                    "atlas_bindings": None,
                    "atlas": row["atlas"],
                    "species": [row["species"]],
                },
                severity,
            )
            for row in bindings
        ]
        verdict = (
            "block"
            if any(row["verdict"] == "block" for row in checks)
            else "warn" if any(row["verdict"] == "warn" for row in checks) else "pass"
        )
        return result(
            verdict,
            "Check species-specific atlas bindings separately",
            {"bindings": checks},
        )
    atlas = environment.get("atlas", {})
    if atlas.get("applicable") is False:
        return result("pass", "This method uses no parcellation", {"applicable": False})
    name = parameters.get("aliases", {}).get(atlas.get("name"), atlas.get("name"))
    species = environment.get("species", [])
    unknown = [value for value in species if value not in parameters["allowed"]]
    mismatched = [
        value
        for value in species
        if value in parameters["allowed"] and name not in parameters["allowed"][value]
    ]
    if mismatched:
        return result(
            "block",
            "Atlas is outside the declared species system",
            {
                "atlas": name,
                "species": species,
                "required_atlases": parameters["allowed"],
                "species_source": environment.get("species_source"),
            },
        )
    if not species or unknown:
        return result(
            "block",
            "Species identity is not established for this atlas",
            {"species": species, "atlas": name, "missing": unknown},
            defer_evidence=True,
        )
    tissue = parameters.get("tissue", {}).get(name)
    if tissue and atlas.get("tissue", "cortical") != tissue:
        return result(
            "block",
            "Atlas tissue scope does not match the measurement",
            {"atlas": name, "atlas_tissue": tissue},
        )
    return result(
        "pass",
        "Atlas matches the declared species and tissue",
        {
            "atlas": name,
            "species": species,
            "identity_verified": environment.get("species_verified", False),
        },
    )


def homology_evidence(parameters, environment, severity="hard"):
    if not environment.get("cross_species"):
        return result("pass", "Not a cross-species comparison")
    accepted = []
    for record in environment.get("homology", []):
        if (
            record.get("host_verified") is True
            and record.get("kind") in parameters["required_kinds"]
            and record.get("source_url")
            and re.fullmatch(r"[a-f0-9]{64}", str(record.get("mapping_sha256", "")))
            and record.get("scope_matches") is True
        ):
            accepted.append(record)
    if not accepted:
        return result(
            "block",
            "Missing sourced and scope-matched homology evidence",
            {
                "missing": [
                    "Cited correspondence or cross-species registration",
                    "Host-verified mapping hash and matching regions/species/spaces",
                ]
            },
            missing_homology=True,
        )
    return result(
        "pass",
        "A host-verified correspondence supports this scope",
        {"correspondences": accepted},
    )


def scale_check(parameters, environment, severity="hard"):
    scale = environment.get("scale", {})
    k = scale.get("k")
    if (
        scale.get("host_verified") is not True
        or type(scale.get("rescaled")) is not bool
        or not finite_number(k)
        or k <= 0
    ):
        return result(
            "warn",
            "Rescale status or factor is unverified",
            {"scale": scale},
            conclusion_ceiling="qualified",
        )
    if not scale["rescaled"] and k != 1:
        return result("block", "Unrescaled data must have k=1", {"scale": scale})
    checked = []
    for row in environment.get("measurements", []):
        power = parameters["powers"].get(row.get("metric"))
        if power is None:
            continue
        stored, reported = row.get("stored_value"), row.get("value")
        if not finite_number(stored) or not finite_number(reported):
            return result(
                "block",
                "Scale conversion lacks finite stored/reported values",
                {"measurement": row},
            )
        expected = stored / k**power
        ok = math.isclose(
            reported, expected, rel_tol=parameters["rtol"], abs_tol=parameters["atol"]
        )
        checked.append(
            {
                "metric": row["metric"],
                "power": power,
                "k": k,
                "expected": expected,
                "reported": reported,
                "pass": ok,
                "source_ref": row.get("source_ref"),
            }
        )
    if any(not row["pass"] for row in checked):
        return result(
            "block",
            "Reported measurement omits the verified rescale correction",
            {"conversions": checked},
        )
    if environment.get("scale_check_required") and not checked:
        return result(
            "warn",
            "Scale metadata is known but no conversion was checked",
            {"scale": scale},
        )
    return result(
        "pass",
        "Stored values and verified rescale conversion agree",
        {"scale": scale, "conversions": checked},
    )


def plausibility(parameters, environment, severity="soft"):
    measurements = environment.get("measurements", [])
    if not measurements:
        return result(
            "pass" if not environment.get("plausibility_required") else "warn",
            "No global physical measurement to compare",
        )
    checked = []
    for row in measurements:
        refs = [
            ref
            for ref in environment.get("references", [])
            if ref["species"] == row.get("species")
            and ref["metric"] == row.get("metric")
            and ref["scope"] == row.get("scope")
            and ref["unit"] == row.get("unit")
        ]
        if (
            row.get("physical_scale_verified") is not True
            or not refs
            or not finite_number(row.get("value"))
        ):
            checked.append(
                {
                    "status": "warn",
                    "reason": "No matching global physical-scale reference",
                    "source_ref": row.get("source_ref"),
                }
            )
            continue
        ref = refs[0]
        delta = abs(row["value"] - ref["mean"])
        relative = delta / abs(ref["mean"])
        sd = ref.get("sd")
        z = (
            delta / sd
            if finite_number(sd)
            and sd > 0
            and ref.get("sd_scope") == row.get("sampling_scope")
            else None
        )
        flagged = relative > parameters["relative_threshold"] or (
            z is not None and z > parameters["sigma_threshold"]
        )
        checked.append(
            {
                "status": "warn" if flagged else "pass",
                "reference_id": ref["id"],
                "relative_deviation": relative,
                "z": z,
                "sd_comparable": z is not None,
                "source": ref["source"],
                "source_ref": row.get("source_ref"),
            }
        )
    return result(
        "warn" if any(row["status"] == "warn" for row in checked) else "pass",
        "Coarse reference check; not expert anatomical validation",
        {"comparisons": checked},
    )


def asymmetry_flip(parameters, environment, severity="soft"):
    if not environment.get("asymmetry"):
        return result("pass", "Not an asymmetry analysis")
    checks = environment.get("bias_checks", [])
    accepted = [
        row
        for row in checks
        if row.get("kind") in parameters["alternatives"]
        and row.get("host_verified") is True
        and row.get("passed") is True
        and row.get("evidence_ref")
    ]
    if not accepted:
        return result(
            "warn",
            "No observed flip or symmetric-atlas check",
            {"required_alternatives": parameters["alternatives"]},
            conclusion_ceiling="qualified",
        )
    return result("pass", "An observed bias-control check passed", {"checks": accepted})


def cross_species_measure(parameters, environment, severity="soft"):
    if not environment.get("cross_species"):
        return result("pass", "Not a cross-species comparison")
    species = set(environment.get("species", []))
    if not species or any(
        s not in {"human", "macaque", "chimpanzee", "marmoset"} for s in species
    ):
        return result(
            "warn",
            "Species count is not verified for this comparison",
            {"species": sorted(species)},
            conclusion_ceiling="qualified",
        )
    kind = environment.get("measure_kind")
    count = len(species)
    if count < 2:
        return result(
            "block",
            "Cross-species analysis requires at least two declared species",
            {"species": sorted(species)},
        )
    if kind == "loglog_residual":
        if count < parameters["minimum_species_loglog"]:
            return result(
                "block",
                "Too few species for the registered allometric residual analysis",
                {
                    "species_count": count,
                    "required": parameters["minimum_species_loglog"],
                },
            )
        return result(
            "pass",
            "Species count permits the registered residual method",
            {"species_count": count, "model_fit_qc": "Must be checked separately"},
        )
    if kind in parameters["two_species_allowed"]:
        return result(
            "pass",
            "Dimensionless within-species ratios used",
            {
                "species_count": count,
                "normalization_ref": environment.get("normalization_ref"),
            },
        )
    return result(
        "warn",
        "Absolute or unregistered cross-species measure limits interpretation",
        {"measure_kind": kind, "species_count": count},
        conclusion_ceiling="qualified",
    )


def min_detectable_effect(parameters, environment, severity="soft"):
    if not environment.get("group_inference"):
        return result("pass", "No group inference requested")
    groups = environment.get("groups", {})
    counts = {name: len(set(values)) for name, values in groups.items()}
    if len(counts) != 2 or min(counts.values(), default=0) < 1:
        return result(
            "warn",
            "Independent-subject group counts missing",
            {"group_counts": counts},
            missing_required_evidence=True,
        )
    lists = list(groups.values())
    if set(lists[0]) & set(lists[1]):
        return result(
            "warn",
            "Independent-group assumption fails: repeated subjects across groups",
            {"group_counts": counts},
            missing_required_evidence=True,
        )
    n = min(counts.values())
    d = (
        NormalDist().inv_cdf(1 - parameters["alpha"] / 2)
        + NormalDist().inv_cdf(parameters["power"])
    ) * math.sqrt(2 / n)
    negative = environment.get("negative_result") is True
    defer = negative and d > parameters["defer_threshold"]
    return result(
        "warn" if defer else "pass",
        "Normal-approximation minimum detectable standardized effect",
        {
            "d_min": d,
            "n_per_group_conservative": n,
            "group_counts": counts,
            "alpha": parameters["alpha"],
            "power": parameters["power"],
            "assumptions": "Two independent groups, common variance; unequal groups use minimum n conservatively; repeats deduplicated",
        },
        underpowered_negative=defer,
    )


CHECKERS = {
    fn.__name__: fn
    for fn in (
        species_atlas,
        homology_evidence,
        scale_check,
        plausibility,
        asymmetry_flip,
        cross_species_measure,
        min_detectable_effect,
    )
}
