"""Resolve the immutable constraint snapshot that authorized or blocked a run."""


def by_sha(store, expected):
    for path in reversed(store.versions("constraints")):
        saved = store.read(path.name)
        if saved["sha256"] == expected:
            from .analysis_control_store import digest
            if digest(saved["record"]) != expected:
                raise ValueError("Bound constraint digest mismatch")
            return saved
    raise ValueError("Bound constraint snapshot is unavailable")


def resolve(tools):
    execution = getattr(tools, "report_execution", None) or tools.last_execution
    reference = execution.get("constraints_sha256")
    source = "execution_or_failure_snapshot"
    plan = tools.control_store.latest("plan")
    executed_version = execution.get("plan_gate", {}).get("plan_version")
    if not reference and executed_version is not None:
        executed_plan = tools.control_store.read("plan.v%06d.json" % executed_version)
        if executed_plan is None:
            raise ValueError("Executed plan snapshot is unavailable")
        reference = executed_plan["record"]["plan"]["constraints"]["sha256"]
        source = "executed_plan"
    if not reference and plan:
        declared = plan["record"]["plan"].get("constraints", {})
        reference = declared.get("sha256")
        source = "sealed_plan"
    if reference:
        snapshot = by_sha(tools.control_store, reference)
    else:
        failure = tools.control_store.latest("planning_failure")
        if failure:
            snapshot = by_sha(tools.control_store, failure["record"]["constraints_sha256"])
            source = "planning_failure"
        else:
            snapshot = tools.control_store.latest("constraints")
            source = "latest_observed_before_seal"
    binding = {"sha256": snapshot["sha256"], "version": snapshot["version"], "source": source} if snapshot else None
    return snapshot, binding
