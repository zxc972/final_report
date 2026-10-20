# Copyright (C) 2026 Wang Zheng Lab, Peking University
#
# This file is part of PrimateX.
#
# PrimateX is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# If you use PrimateX in academic work, please cite:
# Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
# Multi-agentic routing with PrimateX: standardized structural MRI analysis
# for non-human primates and humans.
#
# * Equal contribution.
# Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
# (zheng.wang@pku.edu.cn).
#
# See CITATION.cff for full citation details.

"""Tool execution and validation for agent tool calls."""

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException
from .config import ALLOWED_STEPS, DEFAULT_WORKSPACE, PRIMX_PATH
from .models import (
    CancelPipelineArgs,
    FindT1Args,
    PipelineStatusArgs,
    PipelineTask,
    RouterArgs,
    RunPipelineArgs,
    StepRequest,
    SubjectLsArgs,
    SubjectTreeArgs,
    TailLogArgs,
    UseSampleArgs,
    WorkspaceLsArgs,
)
from .pipeline import ensure_primx_exists, run_pipeline_task, task_response
from . import tasks
from .tasks import TASKS, cancel_task

# Output files produced by the pipeline itself — never treated as a raw T1 candidate.
_KNOWN_OUTPUTS = {
    "T1.nii.gz", "T1_1mm.nii.gz", "T1_truncate.nii.gz", "T1_process_1.nii.gz",
    "brain.nii.gz", "brain_mask.nii.gz", "wm.nii.gz",
}


def _find_t1_candidates(subject_root: Path) -> list[str]:
    candidates: list[str] = []
    for pattern in ("*.nii.gz", "*/*.nii.gz", "*.nii", "*/*.nii"):
        for f in sorted(subject_root.glob(pattern)):
            if f.name not in _KNOWN_OUTPUTS:
                candidates.append(str(f))
    return candidates


def _safe_resolve(workspace: str, *parts: str) -> tuple[Path, Path]:
    """Resolve workspace and a sub-path, rejecting traversal and shallow system paths.

    Returns (workspace_root, resolved_target).
    Raises HTTPException 400 on any path violation.
    """
    workspace_root = Path(workspace).resolve()
    if len(workspace_root.parts) < 3:
        raise HTTPException(
            status_code=400,
            detail=(
                "The Workspace Directory is too broad to use safely. "
                "Please use the default Workspace Directory from Configuration, or choose a dedicated data folder."
            ),
        )
    target = workspace_root
    for part in parts:
        target = (target / part).resolve()
    if not target.is_relative_to(workspace_root):
        raise HTTPException(
            status_code=400,
            detail="The requested path is outside your Workspace Directory. Please choose a file or subject inside your own workspace.",
        )
    return workspace_root, target


def _derive_input_root(workspace_directory: str) -> Optional[Path]:
    """The workspaceDirectory passed to agent tools is always enforced to be
    "<root>/<userId>/output" (see api.py). Raw uploaded T1 files live in the sibling
    "<root>/<userId>/input" tree, which read-only discovery tools also need to see.
    Returns None if workspace_directory doesn't end in /output (e.g. DEFAULT_WORKSPACE,
    which has no input/output split)."""
    p = Path(workspace_directory).resolve()
    if p.name == "output":
        return p.parent / "input"
    return None


def _resolve_with_input_fallback(workspace_directory: str, *parts: str) -> Path:
    """Resolve a sub-path under the enforced output/ workspace; if it doesn't exist
    there, also try the sibling input/ tree before giving up. Falls back to the
    output/ path (even if missing) so callers can still report a sensible 404."""
    _, target = _safe_resolve(workspace_directory, *parts)
    if target.exists():
        return target
    input_root = _derive_input_root(workspace_directory)
    if input_root:
        try:
            _, alt = _safe_resolve(str(input_root), *parts)
            if alt.exists():
                return alt
        except HTTPException:
            pass
    return target


def map_tool_name(name: str) -> str:
    """Normalize tool names to internal handlers."""
    name_map = {
        "run-pipeline": "run_pipeline",
        "pipeline-status": "pipeline_status",
        "cancel-pipeline": "cancel_pipeline",
    }
    return name_map.get(name, name)


def validate_run_pipeline_args(args: RunPipelineArgs) -> None:
    if not args.steps:
        raise HTTPException(status_code=400, detail="steps must be a non-empty array")
    for step in args.steps:
        if step not in ALLOWED_STEPS:
            raise HTTPException(status_code=400, detail=f"Unsupported step: {step}")

    has_fastsurfer = "fastsurfer" in args.steps
    if has_fastsurfer and len(args.steps) > 1:
        raise HTTPException(status_code=400, detail="fastsurfer must be run as a standalone step")
    if has_fastsurfer and args.species and args.species.lower() != "human":
        raise HTTPException(status_code=400, detail="species must be Human when running fastsurfer")

    needs_t1 = any(step in {"preprocess-1", "fastsurfer"} for step in args.steps)
    if needs_t1 and not args.t1_path:
        raise HTTPException(status_code=400, detail="t1Path is required for preprocess or fastsurfer steps")
    needs_species = any(
        step in {"preprocess-1", "acpc-align", "preprocess-3", "rescale", "freesurfer2caret"}
        for step in args.steps
    )
    if needs_species and not args.species:
        raise HTTPException(status_code=400, detail="species is required for neuro pipeline steps")
    needs_seg_species = any(step in {"seg-brain", "seg-wm"} for step in args.steps)
    if needs_seg_species and not args.seg_species:
        raise HTTPException(status_code=400, detail="segSpecies is required for segmentation steps")


def init_task(args: RunPipelineArgs) -> PipelineTask:
    out_path = str(Path(args.workspace_directory) / args.subject_id)
    task_id = f"agent_{uuid.uuid4().hex[:8]}"
    return PipelineTask(
        task_id=task_id,
        subject_id=args.subject_id,
        workspace_directory=args.workspace_directory,
        out_path=out_path,
        steps=args.steps,
        species=args.species,
        seg_species=args.seg_species,
        t1_path=args.t1_path,
        model_dir=args.model_dir,
        brain_size=args.brain_size,
        reference=args.reference,
        low_res_mesh=args.low_res_mesh,
        threads=args.threads,
    )


def build_single_step_args(name: str, step_args: StepRequest) -> RunPipelineArgs:
    out_path = str(Path(step_args.workspace_directory) / step_args.subject_id)
    return RunPipelineArgs(
        subjectId=step_args.subject_id,
        workspaceDirectory=step_args.workspace_directory,
        species=step_args.species,
        segSpecies=step_args.seg_species,
        steps=[name],
        t1Path=step_args.t1_path,
        modelDir=step_args.model_dir,
        brainSize=step_args.brain_size,
        reference=step_args.reference,
        lowResMesh=step_args.low_res_mesh,
        sphinx=step_args.sphinx,
        noStdOrient=step_args.no_std_orient,
        averageHcp=step_args.average_hcp,
        denoise=step_args.denoise,
        keepTmp=step_args.keep_tmp,
        withWm=step_args.with_wm,
        inflateExtraScale=step_args.inflate_extra_scale,
        msmsulc=step_args.msmsulc,
        threads=step_args.threads,
        out_path=out_path,
    )


def execute_tool(
    name: str,
    arguments: Dict[str, Any],
    enforced_workspace: Optional[str] = None,
    enforced_threads: Optional[int] = None,
) -> Dict[str, Any]:
    name = map_tool_name(name)

    # Server-side enforcement: the LLM's tool-call arguments are never trusted for
    # workspaceDirectory. Always pin it to the caller's own namespace (derived from
    # their userId on the server side), so one user can never read or write into
    # another user's workspace regardless of what the model decides to pass.
    if enforced_workspace:
        arguments = {**arguments, "workspaceDirectory": enforced_workspace}
    if enforced_threads is not None and (name == "run_pipeline" or name in ALLOWED_STEPS):
        arguments = {**arguments, "threads": enforced_threads}

    if name == "run_pipeline":
        args = RunPipelineArgs.model_validate(arguments)
        validate_run_pipeline_args(args)
        out_path = str(Path(args.workspace_directory) / args.subject_id)
        args = args.model_copy(update={"out_path": out_path})

        task = init_task(args)
        TASKS.create(task)

        task.future = tasks.submit_pipeline_task(run_pipeline_task, task, args)

        return {
            "taskId": task.task_id,
            "status": task.status,
            "outPath": out_path,
        }

    if name in ALLOWED_STEPS:
        step_args = StepRequest.model_validate(arguments)
        args = build_single_step_args(name, step_args)
        return execute_tool(
            "run_pipeline",
            args.model_dump(by_alias=True, exclude_none=True),
            enforced_workspace=enforced_workspace,
            enforced_threads=enforced_threads,
        )

    if name == "pipeline_status":
        args = PipelineStatusArgs.model_validate(arguments)
        task = TASKS.get(args.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task_response(task)

    if name == "cancel_pipeline":
        args = CancelPipelineArgs.model_validate(arguments)
        task = TASKS.get(args.task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        cancel_task(task)
        return {"taskId": task.task_id, "status": task.status}

    if name == "species-router":
        args = RouterArgs.model_validate(arguments)
        ensure_primx_exists()
        command = [PRIMX_PATH, "seg", "router", "-input_image", args.input_image]
        print(f"[agent][command] {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "Router failed")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid router output: {exc}") from exc

    if name == "subject-ls":
        args = SubjectLsArgs.model_validate(arguments)
        sub_parts = [args.subject_id, args.sub_path] if args.sub_path else [args.subject_id]
        target_path = _resolve_with_input_fallback(args.workspace_directory, *sub_parts)
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Subject directory not found")
        command = ["ls", "-la", str(target_path)]
        print(f"[agent][command] {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "ls failed")
        return {"path": str(target_path), "output": result.stdout}

    if name == "subject-tree":
        args = SubjectTreeArgs.model_validate(arguments)
        sub_parts = [args.subject_id, args.sub_path] if args.sub_path else [args.subject_id]
        target_path = _resolve_with_input_fallback(args.workspace_directory, *sub_parts)
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Subject directory not found")
        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Target path is not a directory")
        max_depth = args.max_depth if args.max_depth is not None else 3
        print(f"[agent][command] subject-tree {target_path} depth={max_depth}")

        lines: list[str] = [str(target_path)]

        def _render(path: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except OSError:
                return
            for i, entry in enumerate(entries):
                connector = "└── " if i == len(entries) - 1 else "├── "
                try:
                    if entry.is_file():
                        try:
                            size = entry.stat().st_size
                            lines.append(f"{prefix}{connector}{entry.name} ({size:,} B)")
                        except OSError:
                            lines.append(f"{prefix}{connector}{entry.name} (size unavailable)")
                    else:
                        lines.append(f"{prefix}{connector}{entry.name}/")
                        extension = "    " if i == len(entries) - 1 else "│   "
                        _render(entry, prefix + extension, depth + 1)
                except OSError:
                    continue

        _render(target_path, "", 1)
        return {"path": str(target_path), "tree": "\n".join(lines)}

    if name == "tail-log":
        args = TailLogArgs.model_validate(arguments)
        _, log_path = _safe_resolve(args.workspace_directory, args.subject_id, args.log_path)
        if not log_path.exists():
            raise HTTPException(status_code=404, detail="Log file not found")
        command = ["tail", "-n", str(args.lines), str(log_path)]
        print(f"[agent][command] {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr.strip() or "tail failed")
        return {"path": str(log_path), "output": result.stdout}

    if name == "workspace-ls":
        args = WorkspaceLsArgs.model_validate(arguments)
        workspace_str = args.workspace_directory or DEFAULT_WORKSPACE
        workspace_root, _ = _safe_resolve(workspace_str)
        # workspace_str is normally pinned to ".../output"; also look at the sibling
        # input/ tree so subjects with only uploaded (not yet processed) data show up.
        input_root = _derive_input_root(workspace_str)
        subjects = set()
        if workspace_root.exists():
            subjects.update(p.name for p in workspace_root.iterdir() if p.is_dir())
        if input_root and input_root.exists():
            subjects.update(p.name for p in input_root.iterdir() if p.is_dir())
        if not subjects and not workspace_root.exists():
            raise HTTPException(status_code=404, detail=f"Workspace not found: {workspace_root}")
        print(f"[agent][command] workspace-ls {workspace_root} (+ input siblings)")
        return {"workspaceDirectory": str(workspace_root), "subjects": sorted(subjects)}

    if name == "find-t1":
        args = FindT1Args.model_validate(arguments)
        workspace_str = args.workspace_directory or DEFAULT_WORKSPACE
        subject_root = _resolve_with_input_fallback(workspace_str, args.subject_id)
        if not subject_root.exists():
            raise HTTPException(status_code=404, detail="Subject directory not found")
        candidates = _find_t1_candidates(subject_root)
        print(f"[agent][command] find-t1 {subject_root} → {len(candidates)} candidate(s)")
        return {"subjectRoot": str(subject_root), "candidates": candidates}

    if name == "list-samples":
        # Scans the server's fixed default workspace for official sample subjects.
        # Directories that already look like a user namespace (have both input/
        # and output/ subdirs) are excluded so we never surface another user's data.
        workspace_root, _ = _safe_resolve(DEFAULT_WORKSPACE)
        samples: list[Dict[str, Any]] = []
        if workspace_root.exists():
            for entry in sorted(workspace_root.iterdir()):
                if not entry.is_dir():
                    continue
                if (entry / "input").is_dir() and (entry / "output").is_dir():
                    continue
                candidates = _find_t1_candidates(entry)
                if not candidates:
                    continue
                samples.append({"sampleId": entry.name, "t1Path": candidates[0]})
        print(f"[agent][command] list-samples {workspace_root} → {len(samples)} sample(s)")
        return {"samples": samples}

    if name == "use-sample-data":
        args = UseSampleArgs.model_validate(arguments)
        _, sample_dir = _safe_resolve(DEFAULT_WORKSPACE, args.sample_id)
        if not sample_dir.exists():
            raise HTTPException(status_code=404, detail="Sample not found")
        candidates = _find_t1_candidates(sample_dir)
        if not candidates:
            raise HTTPException(status_code=404, detail="No T1 image found in this sample")
        src = Path(candidates[0])

        if not enforced_workspace:
            raise HTTPException(status_code=400, detail="No workspace configured for this user; cannot copy sample data")
        # enforced_workspace is always "<root>/<userId>/output" — the user's own root is its parent.
        user_root = str(Path(enforced_workspace).resolve().parent)
        subject_id = args.subject_id or args.sample_id
        _, dest_dir = _safe_resolve(user_root, "input", subject_id, "T1")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / src.name
        shutil.copy2(src, dest_path)
        print(f"[agent][command] use-sample-data {src} -> {dest_path}")
        return {"t1Path": str(dest_path), "inputDir": str(dest_dir), "subjectId": subject_id}

    raise HTTPException(status_code=400, detail=f"Unknown tool: {name}")


def handle_tool_call(name: str, raw_args: str) -> Dict[str, Any]:
    try:
        arguments = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid tool arguments: {exc}") from exc

    return execute_tool(name, arguments)
