"""The same model-independent planning and execution reservation for each run."""

from __future__ import annotations

PLANNING_FRACTION = 0.60
EXECUTION_RESERVE = 9


def planning_limit(maximum):
    return max(1, min(int(maximum * PLANNING_FRACTION), max(1, maximum - EXECUTION_RESERVE)))


def before_reserve(tools):
    from .analysis_agent import MAX_MODEL_CALLS, BudgetExceeded
    session = tools.session
    phase = session.state()['phase']
    used = session.record.setdefault('planning_model_calls', max(0, tools.model_calls))
    limit = planning_limit(MAX_MODEL_CALLS)
    session.record['planning_model_limit'] = limit
    session.record.setdefault('postseal_model_calls', 0)
    if phase in {'unplanned', 'planned'} and used >= limit:
        session.record['planning_exhausted'] = True
        tools.control_store.save('phase_budget', snapshot(session))
        raise BudgetExceeded(f'Planning stage limit reached ({limit}); no sealed plan. Report why planning could not be completed.')
    return phase


def after_reserve(tools, phase):
    session = tools.session
    if phase in {'unplanned', 'planned'}:
        session.record['planning_model_calls'] += 1
    else:
        session.record['postseal_model_calls'] = session.record.get('postseal_model_calls', 0) + 1
    counts = session.record.setdefault('model_calls_by_phase', {})
    counts[phase] = counts.get(phase, 0) + 1
    tools.control_store.save('phase_budget', snapshot(session))


def planning_tools(session, registered):
    from .analysis_agent import MAX_MODEL_CALLS
    phase = session.state()['phase']
    used = session.record.get('planning_model_calls', 0)
    limit = planning_limit(MAX_MODEL_CALLS)
    if phase not in {'unplanned', 'planned'}:
        return None
    if getattr(session.tools, "execution_required", True) is False:
        return frozenset({"read_file", "ls"})
    if used >= limit:
        saved = session.tools.control_store.latest("planning_result")
        return frozenset({"commit_plan"}) if saved and saved["record"].get("candidates") else frozenset()
    from .analysis_planning_tools import selection
    return selection(session)[0]



def budget_hint(tools):
    from .analysis_agent import MAX_MODEL_CALLS
    session = tools.session
    phase = session.state()['phase']
    used = session.record.get('planning_model_calls', 0)
    limit = planning_limit(MAX_MODEL_CALLS)
    if phase not in {'unplanned', 'planned'} or used < limit-1:
        return None
    return (
        f'Planning budget: {used}/{limit} logical calls. Choose and seal an existing feasible candidate now; '
        'if none is feasible, explain why planning cannot be completed. '
        f'At least {EXECUTION_RESERVE} calls are reserved for code, execution, repair and review. '
        'No additional browsing after the planning limit.'
    )


def snapshot(session):
    return {key: session.record.get(key) for key in (
        'planning_model_calls', 'planning_model_limit', 'postseal_model_calls',
        'planning_exhausted', 'model_calls_by_phase') if key in session.record}
