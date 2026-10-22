"""Evidence-bound inspection replies, with no execution/manifest requirement."""

from __future__ import annotations
import json
from .analysis_control_store import digest


def records(tools):
    available = {}
    for kind in ("data_card", "inspection_observation"):
        for path in tools.control_store.versions(kind):
            saved = tools.control_store.read(path.name)
            if saved["sha256"] != digest(saved["record"]):
                raise ValueError("Inspection record digest mismatch")
            record = dict(saved["record"])
            if kind == "data_card":
                record = {key: record[key] for key in ("subjects", "software", "scope")}
            available[path.name] = record
    return available


def pointer(record, path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Use an absolute JSON pointer")
    value = record
    for part in path.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def instructions(tools):
    available = records(tools)
    return (
        "TASK_KIND=data_inspection. Do not plan, seal, write code, execute or submit preprocessing. "
        "You may inspect approved files and directories. Your final reply MUST be one JSON object "
        '{"claims":[{"record_id":"data_card.v000001.json","pointer":"/subjects","value":...}]}. '
        "Copy exact observed values, including null/unknown limitations. For this inventory question cite the full "
        "/subjects array or all individual subject entries so every registered subject and available product type is covered. "
        "The host checks every value against protected observations and renders the reply; do not add unsupported prose. "
        "Available protected observations:\n" + json.dumps(available, ensure_ascii=False)
    )


def validate(tools, draft):
    available = records(tools)
    errors, verified = [], []
    try:
        content = json.loads(draft)
        claims = content["claims"]
        if not isinstance(claims, list) or not 1 <= len(claims) <= 64:
            raise ValueError("claims must contain 1..64 observations")
        for claim in claims:
            rid = claim["record_id"]
            target = pointer(available[rid], claim["pointer"])
            if json.dumps(target, sort_keys=True, ensure_ascii=False) != json.dumps(claim["value"], sort_keys=True, ensure_ascii=False):
                raise ValueError("Claim differs from protected observation: " + rid + claim["pointer"])
            verified.append({"record_id": rid, "pointer": claim["pointer"], "value": target})
        # A complete inventory must include each subject's product observations,
        # not just its identifier. Exact copies preserve declared/verified status.
        covered = []
        for claim in verified:
            if claim["pointer"] == "/subjects" and isinstance(claim["value"], list):
                covered.extend(claim["value"])
            elif claim["pointer"].startswith("/subjects/") and isinstance(claim["value"], dict):
                covered.append(claim["value"])
        expected = next((record["subjects"] for record in available.values() if "subjects" in record), [])
        if any(row not in covered for row in expected):
            raise ValueError("Inventory must cover all registered subject entries and product types")
    except (ValueError, KeyError, TypeError, IndexError) as error:
        errors.append(str(error))
    result = {"valid": not errors, "passed": not errors, "scope": "data_inspection",
              "execution_required": False, "scientific_status": "not_evaluated", "errors": errors,
              "verified_claims": verified, "available_record_ids": sorted(available),
              "validation_scope": "Exact protected identities and values; free-prose entailment is not certified"}
    saved = tools.control_store.save("inspection_result", result)
    result["evidence_ref"] = "inspection_result.v%06d.json" % saved["version"]
    return result


def render(validation):
    lines = ["### Registered data", "No processing was started."]
    for claim in validation.get("verified_claims", []):
        value = claim["value"]
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if isinstance(row, dict) and "subject" in row:
                lines.append(
                    f"- **{row['subject']}** ({row['root']}): {row['files']} observed files; "
                    f"types: {', '.join(row['formats'])}; atlases: {', '.join(row['atlases']) or 'none observed'}; "
                    f"declared species: {row['species_declared'] or 'unknown'}; verified: {row['species_verified'] or 'unknown'}; "
                    f"space: {row['space']}. Source: {claim['record_id']}{claim['pointer']}"
                )
    lines.append("Metadata inventory does not establish reconstruction completion, anatomical QC or physical scale.")
    return "\n\n".join(lines)
