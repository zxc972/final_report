"""Trusted orchestration of deterministic sandbox metadata profiling."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import uuid

from .analysis_control_store import canonical


def explicit_species(request):
    match = re.search(
        r"(?:species|物种)\s*[:=：]\s*([a-zA-Z_ -]{2,50}|人类|人|猕猴|猴)",
        request,
        re.I,
    )
    return match.group(1).strip() if match else None


def mapped_path(tools, raw):
    path = tools.resolve(raw)
    if raw.startswith("/inputs/"):
        return raw
    if path.is_relative_to(tools.workdir):
        return "/work/" + path.relative_to(tools.workdir).as_posix()
    for index, root in enumerate(tools.input_roots):
        if path.is_relative_to(root):
            return f"/inputs/{index}/" + path.relative_to(root).as_posix()
    raise ValueError("Profile path outside approved mounts")


def profile_data(tools, paths):
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= 4096
        or any(not isinstance(p, str) for p in paths)
    ):
        raise ValueError("Supply 1..4096 explicit file paths")
    mapped = [mapped_path(tools, path) for path in paths]
    if len(set(mapped)) != len(mapped):
        raise ValueError("Duplicate profile paths")
    from .analysis_agent import _write_regular, _read_regular

    request = {
        "paths": mapped,
        "tables": getattr(tools, "participants_tables", []),
        "registered_ids": [r["subject_id"] for r in json.loads(Path(os.environ["AGENT_DATA_CATALOG"]).read_text()).get("roots", [])] if os.environ.get("AGENT_DATA_CATALOG") else [],
        "declared_species": explicit_species(getattr(tools, "task_request", "")),
        "request_id": uuid.uuid4().hex,
    }
    script = tools.workdir / ".profile_probe.py"
    worker = Path(__file__).with_name("analysis_profile_worker.py")
    import tempfile

    # Freeze both algorithm and arguments outside the model-writable mount.
    source = worker.read_text(encoding="utf-8")
    source += (
        "\nif __name__ == '__main__':\n"
        "    main(json.loads(" + repr(canonical(request).decode()) + "))\n"
    )
    with tempfile.NamedTemporaryFile(
        dir=tools.control_store.root, suffix=".py", delete=False
    ) as frozen:
        frozen.write(source.encode("utf-8"))
        frozen_path = Path(frozen.name)
    _write_regular(script, tools.workdir, source)
    with tools._execution_lock:
        result = tools.executor.run(
            script, timeout_seconds=120, frozen_source=frozen_path
        )
    if result.get("status") != "success" or result.get("exit_code") != 0:
        return {
            "status": "blocked",
            "reason": "Deterministic sandbox profile did not complete",
            "execution": result,
        }
    profile = json.loads(
        _read_regular(
            tools.workdir / "data_profile.json", tools.workdir, 64 * 1024 * 1024
        )
    )
    if (
        profile.get("schema_version") != "primatex.data_profile.v1"
        or profile.get("request_id") != request["request_id"]
        or [item["path"]["value"] for item in profile["files"]] != mapped
    ):
        raise ValueError("Unexpected profile response")
    saved = tools.control_store.save("data_profile", profile)
    return {
        "status": "ok",
        "path": "/work/data_profile.json",
        "file_count": len(mapped),
        "profile_sha256": saved["sha256"],
        "version": saved["version"],
        "profile": profile,
        "protected_ref": f"data_profile.v{saved['version']:06d}.json",
        "execution": result,
    }
