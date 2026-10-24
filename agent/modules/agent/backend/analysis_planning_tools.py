"""Host-owned planning exposure and atomic read/replan quotas."""

INITIAL = frozenset({"read_file", "ls", "read_operations", "plan_analysis"})
AFTER_PLAN = frozenset({"commit_plan", "plan_analysis", "read_operations"})
READ_TOOLS = frozenset({"read_file", "ls"})
MAX_READS = 4
MAX_PLANS = 3  # Actual entries into the planner.
MAX_ARGUMENT_ERRORS = 3  # Rejected before entering the planner.


def selection(session):
    saved = session.tools.control_store.latest("planning_result")
    reads = session.record.get("planning_read_calls", 0)
    plans = session.record.get("planning_attempts", 0)
    if saved:
        names = {"commit_plan", "plan_analysis"}
        if not session.record.get("commit_argument_error"):
            names.add("read_operations")
        if plans >= MAX_PLANS:
            names.discard("plan_analysis")
        choice = "commit_plan" if saved["record"].get("candidates") else None
        return frozenset(names), choice
    if reads >= MAX_READS:
        return frozenset({"plan_analysis"}), "plan_analysis"
    return INITIAL, None


def reserve_action(tools, name):
    if tools.session.state()["phase"] not in {"unplanned", "planned"}:
        return
    if getattr(tools, "execution_required", True) is False:
        return
    with tools._lock:
        record = tools.session.record
        if name in READ_TOOLS:
            if record.get("planning_read_calls", 0) >= MAX_READS:
                raise ValueError("Planning read quota exhausted (4); call plan_analysis")
            record["planning_read_calls"] = record.get("planning_read_calls", 0) + 1
        elif name == "plan_analysis":
            if record.get("planning_attempts", 0) >= MAX_PLANS:
                raise ValueError("Initial plan plus two replans exhausted; seal or report missing prerequisites")
            record["planning_attempts"] = record.get("planning_attempts", 0) + 1
        else:
            return
        tools.control_store.save("planning_control", {
            key: record.get(key, False if key == "commit_argument_error" else 0) for key in ("planning_read_calls", "planning_attempts", "planning_argument_errors", "commit_argument_error")
        })


def reserve_argument_error(tools):
    """Separate malformed requests from actual plans; preserve all global budgets."""
    with tools._lock:
        record = tools.session.record
        used = record.get("planning_argument_errors", 0)
        if used >= MAX_ARGUMENT_ERRORS:
            raise ValueError("Planning argument correction limit reached (3); no planner attempt was consumed")
        record["planning_argument_errors"] = used + 1
        tools.control_store.save("planning_control", {
            key: record.get(key, False if key == "commit_argument_error" else 0) for key in ("planning_read_calls", "planning_attempts", "planning_argument_errors", "commit_argument_error")
        })
