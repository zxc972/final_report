"""Bounded structured internal review; prose never counts as an approval."""

from __future__ import annotations
import json

REVIEW_SCHEMA = {
    "type": "object",
    "required": ["decision", "findings", "limitations", "hard_block_disclosure"],
    "properties": {
        "decision": {"enum": ["pass", "revise", "insufficient_evidence"]},
        "findings": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": [
                    "severity",
                    "claim",
                    "observation",
                    "evidence_files",
                    "question",
                ],
                "properties": {
                    "severity": {"enum": ["blocking", "warning"]},
                    **{
                        name: {"type": "string", "minLength": 1, "maxLength": 1800}
                        for name in ("claim", "observation", "question")
                    },
                    "evidence_files": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "limitations": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 1800},
        },
        "hard_block_disclosure": {
            "type": "object",
            "required": [
                "complete",
                "undisclosed_constraint_ids",
                "evidence_files",
                "reason",
            ],
            "properties": {
                "complete": {"type": "boolean"},
                "undisclosed_constraint_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "evidence_files": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
            },
        },
    },
}
PROTOCOL_PROMPT = """
The first evidence_card is complete and host-owned. Its hard_blocks include
rejected requested methods, not just the selected alternative. Check that the
report discloses ALL those observed hard blockers. A missing reconstruction
completion record is distinct from a missing executable. Do not certify prose
semantics using keyword presence alone. Supplement the required JSON with:
"hard_block_disclosure":{"complete":true,"undisclosed_constraint_ids":[],
"evidence_files":["evidence_card","report.md"],"reason":"..."}.
Use the observed method-qualified constraint_id as its identity. A local ID is
accepted only if it uniquely identifies one observed blocker; never invent IDs.
If any material hard blocker is undisclosed, set complete=false, list its id,
and return revise with a grounded blocking finding. With no blockers, state
that explicitly. Return only the JSON object. JSON output is not a waiver of
the evidence-identity, findings or decision validation rules.
"""


def first_object(content):
    if not isinstance(content, str) or len(content) > 40000:
        raise ValueError("Invalid bounded review response")
    decoder = json.JSONDecoder()
    text = content.strip()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if not isinstance(value, dict):
            raise ValueError("Review must be an object")
        warnings = []
        if text[:index].strip():
            warnings.append("leading_text")
        if text[end:].strip():
            warnings.append("trailing_text")
        return value, warnings
    raise ValueError("No complete review JSON object")


def parse_structured_review(content, registered, card):
    from .analysis_internal_review import parse_review

    value, warnings = first_object(content)
    from .analysis_constraint_ids import observed_aliases, resolve_observed, register_observed_constraints
    registered = register_observed_constraints(card, set(registered))
    aliases = observed_aliases(card)
    for item in [*value.get("findings", []), value.get("hard_block_disclosure", {})]:
        if isinstance(item, dict) and isinstance(item.get("evidence_files"), list):
            item["evidence_files"] = [resolve_observed(key, card) if isinstance(key, str) and key in aliases else key
                                      for key in item["evidence_files"]]
    result = parse_review(json.dumps(value), registered)
    if any(
        not isinstance(text, str) or len(text) > 1800 for text in result["limitations"]
    ):
        raise ValueError("Limitations must contain bounded strings")
    disclosure = result.get("hard_block_disclosure")
    if not isinstance(disclosure, dict) or type(disclosure.get("complete")) is not bool:
        raise ValueError("Missing hard_block_disclosure.complete boolean")
    ids = disclosure.get("undisclosed_constraint_ids")
    from .analysis_constraint_ids import normalize_disclosure
    ids = normalize_disclosure(ids, card)
    disclosure["undisclosed_constraint_ids"] = ids
    if disclosure["complete"] != (not ids):
        raise ValueError("Disclosure completeness contradicts undisclosed ids")
    paths = disclosure.get("evidence_files")
    if (
        not isinstance(paths, list)
        or not paths
        or any(path not in registered for path in paths)
    ):
        raise ValueError("Disclosure cites unavailable evidence")
    reason = disclosure.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 1800:
        raise ValueError("Disclosure reason must be bounded text")
    if ids and result["decision"] == "pass":
        raise ValueError("Pass contradicts undisclosed hard blockers")
    return result, warnings


def run_structured_review(
    workdir,
    request,
    validation,
    model,
    reserve,
    method_reader,
    register_execution_receipts,
    deadline,
    card,
):
    import hashlib
    import os
    import time
    import uuid
    from .analysis_internal_review import collect_context, REVIEW_PROMPT
    from .analysis_transport import model_deadline, TransportExhausted
    from .agent_router import unsupported_json_format

    context, registered = collect_context(
        workdir, request, validation, method_reader, register_execution_receipts
    )
    registered.add("evidence_card")
    from .analysis_constraint_ids import canonical_row, register_observed_constraints
    card = {**card, **{name: [canonical_row(row) for row in card.get(name, [])]
                      for name in ("hard_conditions", "hard_blocks")}}
    register_observed_constraints(card, registered)
    # These ids are explicitly present in the supplied, protected summary.
    # Register them just like actual execution-receipt ids, not as full files.
    for name in ("software_observations", "hard_conditions", "hard_blocks"):
        registered.update(
            row["evidence_ref"] for row in card.get(name, []) if row.get("evidence_ref")
        )
    profile = card.get("protected_profile")
    if profile and profile.get("record_id"):
        registered.add(profile["record_id"])
    card = {**card, "available_record_ids": sorted(registered)}
    context = {"evidence_card": card, **context}
    context["registered_evidence_ids"] = sorted(registered)
    context_sha = hashlib.sha256(
        json.dumps(context, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    messages = [
        {"role": "system", "content": REVIEW_PROMPT + PROTOCOL_PROMPT},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    attempts = []
    parsed = None
    transport = None
    current_model = model
    for index in range(2):
        item = {"attempt": index + 1, "raw_model_content": "", "parse_warnings": []}
        try:
            reserve()
            from .analysis_call_context import model_source
            with model_deadline(deadline), model_source("internal_review"):
                response = current_model.invoke(messages)
            item["raw_model_content"] = getattr(response, "content", "")
            parsed, item["parse_warnings"] = parse_structured_review(
                item["raw_model_content"], registered, card
            )
            attempts.append(item)
            break
        except TransportExhausted as error:
            transport = {
                "attempts": error.attempts,
                "upstream_status": error.status_code,
                "reason": error.reason,
            }
            item["transport"] = transport
            attempts.append(item)
            break
        except Exception as error:
            item["protocol_error"] = str(error)[:1500]
            item["error_type"] = type(error).__name__
            attempts.append(item)
            if unsupported_json_format(error) and hasattr(current_model, "bound"):
                current_model = current_model.bound
                item["json_format_fallback"] = True
            elif not isinstance(error, (ValueError, TypeError, KeyError)):
                break
            if index == 0:
                messages.append(
                    {
                        "role": "user",
                        "content": "Previous review failed strict validation: "
                        + item["protocol_error"]
                        + ". Available evidence IDs: " + json.dumps(sorted(registered))
                        + ". Retry once with only a complete JSON object including hard_block_disclosure. "
                        "Do not alter findings to obtain approval; review the same supplied evidence.",
                    }
                )
    review = parsed or {
        "decision": "unreviewed",
        "findings": [],
        "limitations": [
            "Internal review was not completed after bounded protocol/transport attempts; Agent text remains an unreviewed draft."
        ],
    }
    if parsed is not None:
        from .analysis_group_reporting import enforce_report_review
        review = enforce_report_review(review, card, workdir)
    root = workdir.parent
    for part in (".analysis_reviews", workdir.name):
        root = root / part
        if root.is_symlink():
            raise ValueError("Review record cannot use symlinks")
        root.mkdir(exist_ok=True)
    rid = uuid.uuid4().hex
    record = {
        "schema": "primatex.internal_review.v2",
        "id": rid,
        "time": time.time(),
        "context_sha256": context_sha,
        "evidence_card": card,
        "response_schema": REVIEW_SCHEMA,
        "attempts": attempts,
        "raw_model_content": attempts[-1]["raw_model_content"] if attempts else "",
        "review": review,
        "transport": transport,
    }
    if parsed is None:
        record["protocol_error"] = attempts[-1].get(
            "protocol_error", "Review unavailable"
        )
    descriptor = os.open(
        root / (rid + ".json"),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "w") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    return {
        **review,
        "status": "reviewed" if parsed else "unreviewed",
        "protocol_valid": parsed is not None,
        "transport_exhausted": transport is not None,
        "transport": transport,
        "review_id": rid,
        "context_sha256": context_sha,
        "protocol_attempts": len(attempts),
        "parse_warnings": [
            warning for item in attempts for warning in item["parse_warnings"]
        ],
        "scope": "AI-assisted source/code/output consistency only; not independent numerical validity, visual review or expert QC.",
    }
