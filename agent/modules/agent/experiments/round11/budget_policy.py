"""Bound six trials by logical calls, with at most three HTTP attempts per call."""
PER_RUN_LOGICAL = 30
MAX_RUNS = 6
ATTEMPTS_PER_CALL = 3


class RunLimitReached(RuntimeError):
    pass


class BatchLimitReached(RuntimeError):
    pass


def reserve_counts(run_logical, batch_logical, run_http, batch_http, planned_runs, previous_attempts):
    if type(planned_runs) is not int or not 1 <= planned_runs <= MAX_RUNS:
        raise ValueError("Plan 1..6 trials before dispatch")
    if not 0 <= previous_attempts < ATTEMPTS_PER_CALL:
        raise RunLimitReached("Logical call exhausted its three HTTP attempts")
    new_call = previous_attempts == 0
    if (new_call and run_logical >= PER_RUN_LOGICAL) or run_http >= PER_RUN_LOGICAL * ATTEMPTS_PER_CALL:
        raise RunLimitReached("Per-trial budget exhausted")
    if (new_call and batch_logical >= planned_runs * PER_RUN_LOGICAL) or batch_http >= planned_runs * PER_RUN_LOGICAL * ATTEMPTS_PER_CALL:
        raise BatchLimitReached("Cohort budget exhausted")
    return run_logical + new_call, batch_logical + new_call, run_http + 1, batch_http + 1


def active_budget(context, active_chat):
    """Routing reserves before ChatSession.activate; keep the same native object."""
    return active_chat.budget if active_chat is not None else context.get('chat_budget')
