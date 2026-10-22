"""Pure cohort accounting; per-run exhaustion never writes a global stop."""
PER_RUN_HTTP = 30
MAX_RUNS = 6

class RunLimitReached(RuntimeError):
    pass

class BatchLimitReached(RuntimeError):
    pass


def reserve_counts(run_started, batch_started, planned_runs):
    if type(planned_runs) is not int or not 1 <= planned_runs <= MAX_RUNS:
        raise ValueError('Plan 1..6 runs before dispatch')
    if run_started >= PER_RUN_HTTP:
        raise RunLimitReached('Per-run HTTP cap reached')
    if batch_started >= planned_runs * PER_RUN_HTTP:
        raise BatchLimitReached('Batch HTTP cap reached')
    return run_started + 1, batch_started + 1
