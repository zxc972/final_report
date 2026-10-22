"""Specific end-of-run causes for a model-scoped, bounded batch stop rule."""

from __future__ import annotations

from collections import Counter

CATEGORIES = {
    'contract_mismatch', 'numeric_mismatch', 'review_revision_unfinished',
    'upstream_transport_error', 'environment_auth_failed', 'environment_rate_limited', 'expected_safety_block', 'route_failed', 'budget_exhausted', 'execution_error',
}


def classify(metadata, expected_route='analysis'):
    validation = metadata.get('validation', {})
    execution = metadata.get('execution', {})
    review = validation.get('internal_review', {})
    public = validation.get('public_output_contract', {})
    numeric = validation.get('independent_numeric', {})
    status = metadata.get('status')
    category = None
    reason = 'No terminal failure'
    if (status == "environment_auth_failed" or validation.get("scope") == "environment_auth_failed"
            or execution.get("environment_auth_failed")
            or metadata.get("routing", {}).get("failureKind") == "environment_auth_failed"):
        return {"category": "environment_auth_failed", "stop_eligible": False,
                "reason": "Upstream permission denied; pause the batch without retry"}
    if (status == "environment_rate_limited" or validation.get("scope") == "environment_rate_limited"
            or execution.get("environment_rate_limited")
            or metadata.get("routing", {}).get("failureKind") == "environment_rate_limited"):
        return {"category": "environment_rate_limited", "stop_eligible": False, "reason": "Upstream 429 retries exhausted; environment failure"}
    if status == "blocked" and validation.get("scope") == "method_constraint_block":
        return {"category": "expected_safety_block", "stop_eligible": False, "reason": "Observed prerequisites prevented execution"}
    if metadata.get('routing', {}).get('failureKind') == 'upstream_transport_error' and metadata.get('route') is None:
        category, reason = 'upstream_transport_error', 'Router transport retries exhausted before a routing decision'
    elif metadata.get('routing', {}).get('parseStatus') == 'route_failed' or (expected_route and metadata.get('route') != expected_route):
        category, reason = 'route_failed', 'No valid dispatch to the requested task type'
    elif status in {'completed', 'inspected'}:
        return {'category': None, 'stop_eligible': False, 'reason': reason}
    elif review.get('decision') == 'unreviewed' and review.get('protocol_attempts') and not review.get('transport_exhausted'):
        category, reason = 'review_revision_unfinished', 'Structured review remained invalid after bounded protocol attempts'
    elif review.get('transport_exhausted') or review.get('decision') == 'unreviewed' or status == 'incomplete_review':
        category, reason = 'upstream_transport_error', 'Final review remained unavailable after bounded retries'
    elif public.get('status') == 'fail':
        category, reason = 'contract_mismatch', 'Public columns, fixed values, identities or row count did not pass'
    elif numeric.get('status') == 'fail' or validation.get('independent_numeric_status') == 'fail':
        category = 'contract_mismatch' if numeric.get('identity_mismatch_count', 0) else 'numeric_mismatch'
        reason = 'Host identity binding differs' if category == 'contract_mismatch' else 'Independent numeric agreement did not pass'
    elif review.get('decision') in {'revise', 'insufficient_evidence'} or review.get('protocol_valid') is False:
        category, reason = 'review_revision_unfinished', 'A valid final passing review was not obtained'
    else:
        error = str(execution.get('agent_error', '')) + ' ' + str(execution.get('error', ''))
        phase = metadata.get('phase_budget', {})
        if 'budget' in error.lower() or 'planning stage limit' in error.lower() or metadata.get('model_calls', 0) >= 30 or (phase.get('planning_limit') and phase.get('planning_model_calls', 0) >= phase['planning_limit'] and not metadata.get('executions')):
            category, reason = 'budget_exhausted', 'Logical or planning-stage budget was exhausted'
        elif 'transport unavailable' in error.lower():
            category, reason = 'upstream_transport_error', 'Coding model transport retries exhausted'
        else:
            category, reason = 'execution_error', 'No current successful completed analysis was produced'
    return {'category': category, 'stop_eligible': category not in {None, 'upstream_transport_error'}, 'reason': reason}


def failure_counts(results):
    return dict(Counter(row['category'] for row in results if row.get('stop_eligible') and row.get('category') in CATEGORIES))


def should_stop(results):
    return any(count >= 2 for count in failure_counts(results).values())


def rate_limit_batch_action(previous_consecutive, classification):
    """Driver pauses between cases; it never repeats an already-paid case."""
    if classification.get("category") == "environment_auth_failed":
        return {"consecutive_rate_limited": 0, "stop_batch": True,
                "pause_seconds": 0, "reason": "environment_auth_failed"}
    count = previous_consecutive + 1 if classification.get("category") == "environment_rate_limited" else 0
    return {"consecutive_rate_limited": count, "stop_batch": count >= 2,
            "pause_seconds": 300 if count == 1 else 0}
