"""Bounded model views with recoverable full tool returns and untouched checkpoints."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid

MAX_TOOL_CHARACTERS = 4000


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def short(value, limit=160):
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def tool_summary(name, payload, path):
    summary = {
        "status": payload.get("status", "ok"),
        "response_ref": path,
        "full_response_offloaded": True,
    }
    for key in (
        "error",
        "reason",
        "version",
        "plan_sha256",
        "protected_ref",
        "path",
        "exit_code",
        "receipt_id",
        "automatic_finalization",
        "feedback_observation_id",
        "reflection_required",
        "state",
    ):
        if key in payload:
            summary[key] = payload[key]
    if name == "plan_analysis":
        summary["candidates"] = [
            {
                key: row[key]
                for key in (
                    "candidate_id",
                    "method",
                    "atlas",
                    "label_counts",
                    "conditions",
                    "subjects",
                )
                if key in row
            }
            for row in payload.get("candidates", [])
        ]
        for row in summary["candidates"]:
            row["method"] = {
                key: row["method"].get(key)
                for key in ("method_id", "name", "evidence_id")
            }
        summary["infeasible"] = [
            {
                "method": row.get("method", {}).get("method_id"),
                "reason": short(row.get("reason", ""), 230),
            }
            for row in payload.get("infeasible", [])
        ]
        summary["needs_preprocessing"] = [
            {
                "reason": short(row.get("reason", "")),
                "preprocessing_plan": row.get("preprocessing_plan"),
            }
            for row in payload.get("needs_preprocessing", [])
        ]
    elif name == "commit_plan" and payload.get("status") == "committed":
        bundle = payload.get("execution_bundle", {})
        summary["plan"] = {"code_path": payload["plan"]["code_path"]}
        summary["execution_bundle"] = {
            key: bundle[key]
            for key in (
                "label_sets_ref",
                "output_contract",
                "unit_disclosure",
                "bundle_ref",
                "next_step",
            )
            if key in bundle
        }
        summary["execution_bundle"]["operations"] = {
            "calls": [
                {"function": row["function"], "inputs": row["inputs"]}
                for row in bundle.get("operations", {}).get("calls", [])
            ]
        }
    elif name == "submit_conclusion":
        card = payload.get("conclusion_card", payload)
        summary["conclusion_card"] = {key: card.get(key) for key in (
            "verdict", "reason", "must_rewrite", "supported_rewrite_scope", "allowed_scopes", "not_passed_count")}
    elif name == "read_file":
        content = payload.get("content", "")
        lines, used = [], 0
        for line in content.splitlines():
            if used + len(line) + 1 > 2300:
                break
            lines.append(line)
            used += len(line) + 1
        summary.update(
            content="\n".join(lines),
            startLine=payload.get("startLine"),
            next_start_line=(payload.get("startLine", 1) + len(lines)),
            truncated=True,
        )
    elif name == "read_operations":
        summary["functions"] = [
            {key: row[key] for key in ("name", "signature") if key in row}
            for row in payload.get("functions", [])
        ]
        summary["next"] = (
            "Call read_operations(function=<name>) for the actual return example"
        )
    else:
        summary["title"] = short(payload.get("title", payload.get("scope", name)))
        summary["snippet"] = short(
            payload.get("snippet", payload.get("interpretation", "")), 1200
        )
        for key in ("source_url", "id", "kind"):
            if key in payload:
                summary[key] = payload[key]
    summary["next_read"] = (
        "Read response_ref with read_file in small pages if more detail is needed"
    )
    if len(serialized(summary)) > MAX_TOOL_CHARACTERS:
        summary.pop("needs_preprocessing", None)
        if "execution_bundle" in summary:
            summary["execution_bundle"].pop("operations", None)
        summary["candidates"] = [
            {
                "candidate_id": row["candidate_id"],
                "method": row.get("method"),
                "atlas": row.get("atlas"),
                "label_counts": row.get("label_counts"),
            }
            for row in summary.get("candidates", [])
        ]
    if len(serialized(summary)) > MAX_TOOL_CHARACTERS:
        summary = {
            key: summary[key]
            for key in (
                "status",
                "response_ref",
                "full_response_offloaded",
                "version",
                "plan_sha256",
                "plan",
                "execution_bundle",
                "error",
                "state",
                "next_read",
            )
            if key in summary
        }
    if len(serialized(summary)) > MAX_TOOL_CHARACTERS:
        summary.pop("execution_bundle", None)
    assert len(serialized(summary)) <= MAX_TOOL_CHARACTERS
    return summary


class ModelContext:
    def __init__(self, tools):
        self.tools = tools

    def offload(self, name, payload):
        if name == "commit_plan" and payload.get("status") == "committed":
            from .analysis_execution_card import execution_card
            return execution_card(payload)
        if len(serialized(payload)) <= MAX_TOOL_CHARACTERS:
            return payload
        from .analysis_agent import _write_regular

        path = "/work/tool_results/" + name + "_" + uuid.uuid4().hex + ".json"
        target = self.tools.resolve(path, writable=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        _write_regular(target, self.tools.workdir, content)
        self.tools.control_store.save(
            "tool_return",
            {
                "tool": name,
                "path": path,
                "characters": len(content),
                "sha256": hashlib.sha256(content.encode()).hexdigest(),
            },
        )
        return tool_summary(name, payload, path)

    def messages(self, messages):
        views = compact_messages(messages)
        before = sum(len(str(getattr(m, "content", ""))) for m in messages)
        after = sum(len(str(getattr(m, "content", ""))) for m in views)
        self.tools.control_store.save(
            "context_view",
            {
                "model_call": self.tools.model_calls,
                "content_characters_before": before,
                "content_characters_after": after,
                "checkpoint_messages_modified": False,
            },
        )
        return views


def _content(message):
    return message.get("content", "") if isinstance(message, dict) else message.content


def _calls(message):
    return (
        message.get("tool_calls", [])
        if isinstance(message, dict)
        else getattr(message, "tool_calls", [])
    )


def _call_parts(call):
    if "function" in call:
        function = call["function"]
        try:
            args = json.loads(function.get("arguments", "{}"))
        except ValueError:
            args = {}
        return function["name"], args
    return call.get("name", ""), call.get("args", {})


def _role(message):
    if isinstance(message, dict):
        return message.get("role", "")
    return {"ai": "assistant", "human": "user"}.get(message.type, message.type)


def compact_messages(messages):
    """Pure replay-safe source compaction; never remove tool call/response pairs."""
    result = copy.deepcopy(messages)
    successful = set()
    for message in result:
        if _role(message) != "tool":
            continue
        try:
            payload = json.loads(_content(message))
        except (TypeError, ValueError):
            continue
        if payload.get("status") == "written":
            successful.add(
                message.get("tool_call_id")
                if isinstance(message, dict)
                else message.tool_call_id
            )
    latest = {}
    for index, message in enumerate(result):
        for call in _calls(message):
            name, args = _call_parts(call)
            if name == "write_code" and call.get("id") in successful:
                latest[args.get("path")] = index
    for index, message in enumerate(result):
        for call in _calls(message):
            name, args = _call_parts(call)
            if (
                name == "write_code"
                and latest.get(args.get("path"), index) > index
                and "code" in args
            ):
                raw = args["code"].encode()
                args["code"] = (
                    "# Superseded source omitted from model view. Current file: "
                    + str(args.get("path"))
                    + "; previous SHA-256: "
                    + hashlib.sha256(raw).hexdigest()
                    + "\n"
                )
                if "function" in call:
                    call["function"]["arguments"] = serialized(args)
        if _role(message) == "tool":
            try:
                payload = json.loads(_content(message))
            except (TypeError, ValueError):
                continue
            path = payload.get("path")
            if (
                isinstance(path, str)
                and path in latest
                and latest[path] > index
                and "content" in payload
            ):
                payload["content"] = (
                    "Superseded code read; read the current sealed file if needed."
                )
                text = serialized(payload)
                if isinstance(message, dict):
                    message["content"] = text
                else:
                    message.content = text
    return result
