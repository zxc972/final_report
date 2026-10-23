"""Host-owned phase exposure; neither generates nor edits scientific code."""

from pathlib import PurePosixPath

SEALED_TOOLS = frozenset(
    {"write_code", "run_python", "read_operations", "finalize_artifacts"}
)
FAILED_TOOLS = SEALED_TOOLS | {"read_file", "record_analysis_reflection"}


def tool_name(tool):
    if isinstance(tool, dict):
        return tool.get("name", tool.get("function", {}).get("name"))
    return tool.name


def phase_tools(session, registered):
    phase = session.state()["phase"]
    if getattr(session.tools, "execution_required", True) is False:
        return frozenset({"ls", "read_file"})
    if phase == "sealed":
        return SEALED_TOOLS
    if phase == "executed_failed":
        return FAILED_TOOLS
    if phase == "finalized":
        from .analysis_crossspecies import enabled

        return frozenset(
            {"finalize_artifacts", "submit_conclusion"}
            if enabled(session.tools)
            else {"finalize_artifacts"}
        )
    from .analysis_planning_budget import planning_tools
    return planning_tools(session, registered)


def read_error_allowed(tools, arguments):
    path = arguments.get("path", "")
    if not isinstance(path, str) or not path.startswith("/work/"):
        return False
    target = tools.resolve(path)
    if not target.is_relative_to(tools.workdir):
        return False
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if tools.session.record.get("review_pending"):
        plan = tools.control_store.latest("plan")
        if plan:
            declared = plan["record"]["plan"]
            readable = {declared["code_path"], *[
                item if str(item).startswith("/work/") else "/work/" + str(item)
                for item in declared.get("outputs", [])]}
            readable.update({"/work/report.md", "/work/self_checks.json", "/work/analysis_plan.json", "/work/repair_log.json"})
            if path in readable:
                return True
    return (
        "tool_results" in parts
        or name.startswith(("stderr", "stdout", "error"))
        or name.endswith((".log", ".stderr", ".stdout"))
    )


def restrict_request(tools, request):
    allowed = phase_tools(tools.session, [tool_name(t) for t in request.tools])
    phase = tools.session.state()["phase"]
    selected = [tool for tool in request.tools if tool_name(tool) in allowed]
    if phase == "finalized":
        from .analysis_conclusion_tools import restrict_schema
        selected = [restrict_schema(tool, tools) if tool_name(tool) == "submit_conclusion"
                    else tool for tool in selected]
    force_write = (
        phase == "sealed"
        and tools.session.record.get("written_plan_version")
        != tools.session.record["plan_version"]
    )
    force_write = force_write and tools.session.record.get(
        "tool_choice_supported", True
    )
    choice = (
        {"type": "function", "function": {"name": "write_code"}}
        if force_write
        else None
    )
    if phase in {"unplanned", "planned"} and getattr(tools, "execution_required", True):
        from .analysis_planning_tools import selection
        forced = selection(tools.session)[1]
        if forced and tools.session.record.get("tool_choice_supported", True):
            choice = {"type": "function", "function": {"name": forced}}
    from .analysis_crossspecies import enabled as cross_enabled

    if (
        phase == "finalized"
        and cross_enabled(tools)
        and tools.session.record.get("tool_choice_supported", True)
    ):
        latest = tools.control_store.latest("conclusion")
        if (latest is None or latest["record"].get("must_rewrite")
                or latest["record"].get("analysis_execution_receipt_id") != tools.last_execution.get("receipt_id")):
            choice = {"type": "function", "function": {"name": "submit_conclusion"}}
    tools.events.append(
        "code" if phase == "sealed" else "review",
        "done",
        (
            "Plan sealed: writing analysis code"
            if phase == "sealed"
            else "Phase tools: " + phase
        ),
        {
            "phase": phase,
            "available_tools": sorted(allowed),
            "tool_choice": choice,
            "model_call": tools.model_calls,
            "enforcement": "model registry and tool execution guard",
        },
    )
    from .analysis_planning_budget import budget_hint
    hint = budget_hint(tools)
    if hint:
        from langchain_core.messages import HumanMessage
        tools.events.append("plan", "warn", "Planning limit: seal or decline", {
            "planning_model_calls": tools.session.record.get("planning_model_calls", 0),
            "planning_model_limit": tools.session.record.get("planning_model_limit"),
            "reserved_execution_calls": 9, "available_tools": sorted(allowed),
        })
        return request.override(tools=selected, tool_choice=choice,
                                messages=[*request.messages, HumanMessage(content=hint)])
    return request.override(tools=selected, tool_choice=choice)


def call_with_phase_choice(tools, request, handler):
    """One explicit unsupported-field fallback; each attempted HTTP is charged."""
    from openai import BadRequestError

    try:
        return handler(request)
    except BadRequestError as exc:
        body = getattr(exc, "body", {})
        error = body.get("error", body) if isinstance(body, dict) else {}
        message = str(error.get("message", "")).lower()
        named = error.get("param") == "tool_choice" or "tool_choice" in message
        unsupported = any(
            word in message
            for word in (
                "unsupported",
                "unknown field",
                "unknown_parameter",
                "not support",
            )
        )
        if not request.tool_choice or not (named and unsupported):
            raise
        tools.session.record["tool_choice_supported"] = False
        tools.control_store.save("session", tools.session.record)
        tools.events.append(
            "code",
            "warn",
            "Using phase tool list only",
            {
                "phase": tools.session.state()["phase"],
                "reason": "Upstream rejected tool_choice",
                "available_tools": sorted(tool_name(tool) for tool in request.tools),
            },
        )
        tools._tick(model=True)
        return handler(request.override(tool_choice=None))
