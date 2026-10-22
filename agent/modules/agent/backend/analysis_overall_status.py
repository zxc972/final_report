"""One overall decision with explicit, separately inspectable component states."""

from __future__ import annotations

import copy

PRIORITY = ('blocked', 'environment_auth_failed', 'environment_rate_limited', 'failed', 'incomplete_review', 'deferred', 'qualified', 'accepted')


def review_status(validation):
    if validation.get('scope') in {'data_inspection', 'pipeline_submission', 'analysis_job_submission'}:
        return 'not_required'
    review = validation.get('internal_review', {})
    if review.get('decision') == 'pass' and review.get('protocol_valid') is True:
        return 'reviewed'
    if review.get('decision') == 'revise':
        return 'revision_incomplete'
    return 'unreviewed'


def overall_status(native_status, verdict, validation):
    statuses = []
    if native_status in {'environment_rate_limited', 'environment_auth_failed'}:
        return native_status
    if native_status == 'blocked' or verdict in {'blocked', 'rejected'}:
        statuses.append('blocked')
    if native_status in {'failed', 'cancelled', 'output_integrity_failed', 'unknown_after_worker_exit'}:
        statuses.append('failed')
    if native_status == 'incomplete_review':
        statuses.append('incomplete_review')
    if review_status(validation) not in {'reviewed', 'not_required'}:
        statuses.append('deferred')
    statuses.append(verdict if verdict in PRIORITY else 'deferred')
    return next(value for value in PRIORITY if value in statuses)


def finalize_card(card, validation, native_status, execution, artifact_phase=None):
    result = copy.deepcopy(card)
    reviewed = review_status(validation)
    review = validation.get('internal_review', {})
    review_check = {
        'constraint_id': 'internal_review', 'severity': 'soft',
        'verdict': 'pass' if reviewed in {'reviewed', 'not_required'} else 'warn',
        'tool_observed': {'status': reviewed, 'review_id': review.get('review_id'),
                          'reason': 'Final source/output review passed' if reviewed == 'reviewed'
                          else 'No completed valid final review; Agent text is a draft' if reviewed != 'not_required'
                          else 'Review is not required for inspection/submission'},
    }
    result.setdefault('checks_passed', [])
    result.setdefault('checks_not_passed', [])
    for key in ['checks_passed', 'checks_not_passed']:
        result[key] = [row for row in result[key] if row.get('constraint_id') != 'internal_review']
    result['checks_passed' if review_check['verdict'] == 'pass' else 'checks_not_passed'].append(review_check)
    result['not_passed_count'] = len(result['checks_not_passed'])
    if reviewed not in {'reviewed', 'not_required'} and result.get('verdict') not in {'blocked', 'rejected', 'deferred'}:
        result['prior_component_verdict'] = result['verdict']
        result['verdict'] = 'deferred'
        result['reason'] = 'Internal review is unfinished or unavailable; a reviewed conclusion cannot be issued.'
    result['review_status'] = reviewed
    result['text_label'] = 'Reviewed' if reviewed == 'reviewed' else 'Agent draft (unreviewed)' if reviewed != 'not_required' else 'Inspection/submission reply'
    result['overall_status'] = overall_status(native_status, result['verdict'], validation)
    numeric = validation.get('independent_numeric', {})
    public = validation.get('public_output_contract', {})
    result['component_statuses'] = {
        'artifacts': 'finalized' if artifact_phase == 'finalized' else artifact_phase or 'not_finalized',
        'public_contract': public.get('status', 'not_performed'),
        'independent_numeric': numeric.get('status', validation.get('independent_numeric_status', 'not_configured')),
        'internal_review': reviewed,
        'execution': 'passed' if execution.get('exit_code') == 0 and execution.get('status') == 'success' else 'failed' if execution.get('exit_code') is not None else 'not_run',
        'last_exit_code': execution.get('exit_code'),
        'identity_mismatch_count': (public.get('identity_mismatch_count', 0) + numeric.get('identity_mismatch_count', 0)) if public.get('status') in {'pass', 'fail'} or numeric.get('status') in {'pass', 'fail'} else None,
        'numeric_mismatch_count': numeric.get('numeric_mismatch_count', 0) if numeric.get('status') in {'pass', 'fail'} else None,
    }
    return result
