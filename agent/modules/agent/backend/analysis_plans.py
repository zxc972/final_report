"""Host-sealed plans and a conservative read-only Python inspection gate."""

from __future__ import annotations

import ast
import json
from pathlib import Path, PurePosixPath
import time

from .analysis_constraints import plan_core
from .analysis_control_store import canonical, digest

NEXT_STEPS = [
    "换用满足现有条件的方法",
    "补充缺失数据或软件后重新检查",
    "终止分析并报告缺失前提",
]


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError(label + " must be a nonempty bounded string")


def _work_path(path):
    if not isinstance(path, str) or not path.startswith("/work/"):
        raise ValueError("Use an explicit /work path")
    parts = path[len("/work/") :].split("/")
    if (
        any(part in ("", ".", "..") or part.startswith(".") for part in parts)
        or "\\" in path
    ):
        raise ValueError(
            "Use a plain /work path without hidden components or traversal"
        )
    return path


def commit_plan(tools, plan):
    if not isinstance(plan, dict) or len(canonical(plan)) > (2_000_000 if plan.get("method", {}).get("method_id") == "method:v14:group_regional_glm" else 100_000):
        raise ValueError("Bounded structured plan required")
    for key in (
        "question",
        "data",
        "atlas",
        "method",
        "constraints",
        "outputs",
        "code_path",
    ):
        if key not in plan:
            raise ValueError("Missing required plan field: " + key)
    from .analysis_crossspecies import enabled as cross_enabled, validate_commitment
    if cross_enabled(tools):
        validate_commitment(plan.get("analysis_scope", {}).get("commitment"), plan)
    _required_text(plan["question"], "question")
    if "\n" in plan["question"]:
        raise ValueError("question must be one line")
    if (
        not isinstance(plan["data"], dict)
        or not isinstance(plan["atlas"], dict)
        or not isinstance(plan["method"], dict)
    ):
        raise ValueError("data, atlas and method must be structured objects")
    atlas_keys = ("name", "space", "hemisphere_rule") if (
        tools.knowledge_profile.name == "product_graph_planner"
        and plan["atlas"].get("applicable") is False
        and plan["atlas"].get("reason")
    ) else ("name", "version", "space", "hemisphere_rule")
    for key in atlas_keys:
        _required_text(plan["atlas"].get(key), "atlas." + key)
    method_id = plan["method"].get("method_id")
    _required_text(method_id, "method.method_id")
    if method_id.startswith("self:"):
        _required_text(plan["method"].get("reason"), "self-written method reason")
    code_path = _work_path(plan["code_path"])
    if not code_path.endswith(".py"):
        raise ValueError("code_path must name a Python script")
    tools.resolve(code_path, writable=True)
    if (
        not isinstance(plan["outputs"], list)
        or not plan["outputs"]
        or len(plan["outputs"]) > 32
    ):
        raise ValueError("Declare 1..32 output artifacts")
    for output in plan["outputs"]:
        path = output.get("path") if isinstance(output, dict) else output
        _work_path(
            path
            if isinstance(path, str) and path.startswith("/work/")
            else "/work/" + str(path)
        )
    saved = tools.control_store.latest("constraints")
    profile = tools.control_store.latest("data_profile")
    if saved is None or profile is None:
        return {
            "status": "blocked",
            "reason": "Generate data profile and compile constraints before committing",
            "next_steps": NEXT_STEPS,
        }
    ref = plan["constraints"]
    if (
        not isinstance(ref, dict)
        or ref.get("sha256") != saved["sha256"]
        or ref.get("version") != saved["version"]
    ):
        return {
            "status": "blocked",
            "reason": "Plan must reference the latest protected constraints version and SHA-256",
            "next_steps": NEXT_STEPS,
        }
    record = saved["record"]
    if (
        record["profile_sha256"] != profile["sha256"]
        or plan["data"].get("profile_sha256") != profile["sha256"]
    ):
        return {
            "status": "blocked",
            "reason": "Data profile changed or its reference is missing; recompile constraints",
            "next_steps": NEXT_STEPS,
        }
    if record["method_id"] != method_id or record["plan_context_sha256"] != digest(
        plan_core(plan)
    ):
        return {
            "status": "blocked",
            "reason": "Plan differs from the checked method/data/atlas/scope; recompile constraints",
            "next_steps": NEXT_STEPS,
        }
    blocked = [
        row
        for row in record["rows"]
        if row["severity"] == "hard" and row["verdict"] != "pass"
    ]
    if blocked:
        return {
            "status": "blocked",
            "reason": "Hard constraints are not all pass",
            "blocked_constraints": blocked,
            "next_steps": NEXT_STEPS,
        }
    previous = tools.control_store.latest("plan")
    reason = plan.get("revision_reason", "initial plan" if previous is None else "")
    _required_text(reason, "revision_reason (required for every later version)")
    warnings = [row for row in record["rows"] if row["verdict"] == "warn"]
    method_evidence = {}
    if not method_id.startswith("self:"):
        original = tools._method_graph().read(method_id)
        method_evidence = {
            "name": original["method"]["name"],
            "release_sha256": original.get("release_sha256"),
            "sources": original.get("source_evidence", []),
        }
    sealed = {
        "schema_version": "primatex.committed_plan.v1",
        "plan": plan,
        "plan_content_sha256": digest(plan),
        "method_evidence": method_evidence,
        "revision_reason": reason,
        "committed_time": time.time(),
        "constraints_sha256": saved["sha256"],
        "profile_sha256": profile["sha256"],
        "must_disclose": warnings + record.get("unmapped_conditions", []),
        "scope": "Plan commitment and mapped prerequisite observations; not scientific or expert-QC approval",
    }
    saved_plan = tools.control_store.save("plan", sealed)
    return {
        "status": "committed",
        "version": saved_plan["version"],
        "plan_sha256": saved_plan["sha256"],
        "plan": plan,
        "must_disclose": sealed["must_disclose"],
        "protected_ref": f"plan.v{saved_plan['version']:06d}.json",
    }


def plan_history(store):
    history = []
    for path in store.versions("plan"):
        item = store.read(path.name)
        if item["sha256"] != digest(item["record"]):
            raise ValueError("Plan history digest mismatch")
        history.append(
            {
                "version": item["version"],
                "sha256": item["sha256"],
                "revision_reason": item["record"]["revision_reason"],
                "code_path": item["record"]["plan"]["code_path"],
            }
        )
    return history


def read_only_inspection(source, resolver):
    """Accept only a small metadata-reading language, plus an actual RO mount.

    This intentionally rejects general Python, dynamic calls, loops, subprocesses,
    imports of generated modules and output writers. Unrecognized code needs a
    committed plan. It is not a general-purpose Python effect proof.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    safe_modules = {"json", "nibabel", "pathlib"}
    safe_functions = {
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "tuple",
        "list",
        "sorted",
        "Path",
    }
    safe_methods = {
        "read_text",
        "read_bytes",
        "exists",
        "is_file",
        "is_dir",
        "stat",
        "get_zooms",
        "get_xyzt_units",
        "get_data_dtype",
        "as_posix",
    }
    properties = {"shape", "header", "affine", "ndim", "name", "suffix", "st_size"}
    aliases = {"Path": "Path"}
    allowed_nodes = (
        ast.Module,
        ast.Import,
        ast.ImportFrom,
        ast.alias,
        ast.Assign,
        ast.Expr,
        ast.Call,
        ast.Name,
        ast.Attribute,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Load,
        ast.Store,
        ast.keyword,
        ast.Subscript,
        ast.Slice,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            return False
        if isinstance(node, ast.Import):
            for entry in node.names:
                if entry.name not in safe_modules:
                    return False
                aliases[entry.asname or entry.name] = entry.name
        if isinstance(node, ast.ImportFrom):
            if node.module != "pathlib" or any(
                entry.name != "Path" for entry in node.names
            ):
                return False
            for entry in node.names:
                aliases[entry.asname or entry.name] = "Path"
        if isinstance(node, ast.Assign):
            if any(
                not isinstance(target, ast.Name)
                or target.id in safe_functions
                or target.id in aliases
                for target in node.targets
            ):
                return False
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            return False
        if isinstance(
            node, ast.Attribute
        ) and node.attr not in safe_methods | properties | {"load", "loads", "dumps"}:
            return False
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                fn = aliases.get(node.func.id, node.func.id)
                if fn not in safe_functions:
                    return False
                if fn == "Path":
                    if (
                        len(node.args) != 1
                        or not isinstance(node.args[0], ast.Constant)
                        or not isinstance(node.args[0].value, str)
                    ):
                        return False
                    try:
                        resolver(node.args[0].value)
                    except ValueError:
                        return False
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
                if name in {"load", "loads", "dumps"}:
                    if not isinstance(node.func.value, ast.Name):
                        return False
                    module = aliases.get(node.func.value.id)
                    if (name == "load" and module != "nibabel") or (
                        name in {"loads", "dumps"} and module != "json"
                    ):
                        return False
                    if name == "load":
                        if (
                            not node.args
                            or not isinstance(node.args[0], ast.Constant)
                            or not isinstance(node.args[0].value, str)
                        ):
                            return False
                        try:
                            resolver(node.args[0].value)
                        except ValueError:
                            return False
                elif name not in safe_methods:
                    return False
            else:
                return False
    return True


def execution_gate(tools, script, background=False):
    if tools.knowledge_profile.name not in {"method_graph_gated", "product_graph_planner"}:
        return {"allowed": True, "read_only": False}
    plan = tools.control_store.latest("plan")
    target = "/work/" + script.relative_to(tools.workdir).as_posix()
    if plan is not None:
        record = plan["record"]
        current = tools.control_store.latest("constraints")
        profile = tools.control_store.latest("data_profile")
        if (
            record["plan"]["code_path"] == target
            and current
            and profile
            and record["constraints_sha256"] == current["sha256"]
            and record["profile_sha256"] == profile["sha256"]
        ):
            from .analysis_constraints import selected_files
            from .analysis_profile_worker import file_hash, value

            for item in selected_files(profile["record"], record["plan"]):
                try:
                    actual, _ = file_hash(tools.resolve(value(item["path"])))
                except OSError:
                    actual = None
                if actual != value(item["sha256"]):
                    return {
                        "allowed": False,
                        "status": "blocked",
                        "reason": "Input fingerprint changed or became unreadable; regenerate the data profile, constraints and plan",
                        "next_steps": NEXT_STEPS,
                    }
            if record["plan"]["method"]["method_id"] == "method:v14:group_regional_glm":
                import hashlib
                bundle = tools.control_store.latest("execution_bundle")
                manifest = bundle["record"].get("inputs_manifest", {}) if bundle else {}
                try:
                    actual = hashlib.sha256(tools.resolve("/work/inputs_manifest.json").read_bytes()).hexdigest()
                except OSError:
                    actual = None
                if not manifest.get("sha256") or actual != manifest["sha256"]:
                    return {"allowed": False, "status": "blocked", "reason": "Sealed input manifest changed; replan before execution"}
            from .analysis_execution_guidance import verify_documents
            public_bundle = tools.control_store.latest("execution_bundle")
            if public_bundle and not verify_documents(tools, public_bundle["record"]):
                return {"allowed": False, "status": "blocked", "reason": "Sealed execution documentation changed; replan before execution"}
            return {
                "allowed": True,
                "read_only": False,
                "plan_version": plan["version"],
                "plan_sha256": plan["sha256"],
            }
    from .analysis_agent import _read_regular, MAX_CODE_BYTES

    source = _read_regular(script, tools.workdir, MAX_CODE_BYTES).decode("utf-8")
    if not background and read_only_inspection(source, tools.resolve):
        return {
            "allowed": True,
            "read_only": True,
            "scope": "tool-classified read-only metadata inspection",
        }
    return {
        "allowed": False,
        "status": "blocked",
        "reason": "Production execution requires commit_plan with current checks and matching code_path",
        "next_steps": [
            "调用 profile_data 和 compile_constraints",
            "调用 commit_plan 封存计划后执行对应代码",
            *NEXT_STEPS,
        ],
    }
