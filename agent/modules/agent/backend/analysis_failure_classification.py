"""Specific end-of-run causes for a model-scoped, bounded batch stop rule."""

from __future__ import annotations

from collections import Counter

CATEGORIES = {
    'system_defect', 'agent_budget_exhausted', 'review_incomplete', 'contract_failed',
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
    elif metadata.get('system_defects', {}).get('events'):
        category, reason = 'system_defect', 'Host-generated execution instructions failed; actual model charges are retained and planning-quota exemptions are recorded'
    elif (review.get('decision') in {'unreviewed','revise','insufficient_evidence'} or review.get('protocol_valid') is False or status == 'incomplete_review'):
        category, reason = 'review_incomplete', 'A final valid passing internal review was not completed; inspect protocol, transport and protected review-budget counters'
    elif execution.get('automatic_finalization', {}).get('status') == 'artifact_contract_failed':
        category, reason = 'contract_failed', 'Current execution did not produce the sealed filenames/headers/required artifacts; observed serialization diagnostics are attached'
    elif public.get('status') == 'fail':
        category, reason = 'contract_failed', 'Public columns, fixed values, identities or row count did not pass'
    elif numeric.get('status') == 'fail' or validation.get('independent_numeric_status') == 'fail':
        category = 'contract_failed' if numeric.get('identity_mismatch_count', 0) else 'numeric_mismatch'
        reason = 'Host identity binding differs' if category == 'contract_failed' else 'Independent numeric agreement did not pass'
    else:
        error = str(execution.get('agent_error', '')) + ' ' + str(execution.get('error', ''))
        phase = metadata.get('phase_budget', {})
        if 'budget' in error.lower() or metadata.get('review_budget',{}).get('nonreview_model_calls',0) >= metadata.get('review_budget',{}).get('nonreview_limit',float('inf')) or 'planning stage limit' in error.lower() or metadata.get('model_calls', 0) >= 30 or (phase.get('planning_limit') and phase.get('planning_model_calls', 0) >= phase['planning_limit'] and not metadata.get('executions')):
            category, reason = 'agent_budget_exhausted', 'Agent logical/non-review or planning-stage allowance was exhausted without a recorded host defect'
        elif 'transport unavailable' in error.lower():
            category, reason = 'upstream_transport_error', 'Coding model transport retries exhausted'
        else:
            category, reason = 'execution_error', 'No current successful completed analysis was produced'
    review_transport = category == 'review_incomplete' and (review.get('transport_exhausted') is True or
        (status == 'incomplete_review' and not review.get('protocol_attempts') and review.get('decision') not in {'revise','insufficient_evidence'}))
    if review_transport:reason = 'Final passing internal review unavailable after transport; recorded separately and excluded from model failure stops'
    return {'category': category, 'stop_eligible': category not in {None, 'upstream_transport_error'} and not review_transport, 'reason': reason,
            'basis': {'system_defect_codes':[e.get('code') for e in metadata.get('system_defects',{}).get('events',[])],
                      'review_decision':review.get('decision'),'review_protocol_attempts':review.get('protocol_attempts'),
                      'review_transport_exhausted':review.get('transport_exhausted'),'public_contract_status':public.get('status'),
                      'review_budget':metadata.get('review_budget'),'phase_budget':metadata.get('phase_budget')}}


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
