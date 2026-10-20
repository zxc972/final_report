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

"""Pipeline command building and execution helpers."""

import os
import shutil
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .config import DEEP_LEARNING_SEGMENTATION_STEPS, PRIMX_PATH
from .models import PipelineTask, RunPipelineArgs
from .tasks import (
    acquire_segmentation_resource,
    register_process,
    release_segmentation_resource,
    terminate_process,
    unregister_process,
)


def build_process_command(args: RunPipelineArgs, cmd_args: list[str], step: str) -> list[str]:
    """Optional operator-configured SIF runtime; preserve --nv for GPU segmentation."""
    image_value = os.getenv("PRIMATEX_PIPELINE_IMAGE", "")
    if not image_value:
        return [PRIMX_PATH, *cmd_args]
    image = Path(image_value).resolve()
    runtime = shutil.which("apptainer") or shutil.which("singularity")
    if not runtime or not image.is_file():
        raise RuntimeError("Configured PrimateX pipeline SIF/runtime is unavailable")
    repo = Path(PRIMX_PATH).resolve().parents[2]
    binds = [(repo, "ro"), (Path(args.workspace_directory).resolve(), "rw")]
    for value in (args.t1_path, args.model_dir, args.reference):
        if value:
            path = Path(value).resolve()
            binds.append((path if path.is_dir() else path.parent, "ro"))
    command = [runtime, "exec", "--cleanenv"]
    if step in DEEP_LEARNING_SEGMENTATION_STEPS or step == "fastsurfer":
        command.append("--nv")
    for path, access in dict.fromkeys(binds):
        if any(c in str(path) for c in (":", ",", "\n")):
            raise ValueError("Unsupported container bind path")
        command.extend(["--bind", f"{path}:{path}:{access}"])
    license_value = os.getenv("PRIMATEX_FREESURFER_LICENSE", "")
    if license_value:
        license_path = Path(license_value).resolve()
        if not license_path.is_file() or any(c in str(license_path) for c in (":", ",", "\n")):
            raise RuntimeError("Configured FreeSurfer license file is unavailable")
        command.extend(["--bind", f"{license_path}:/opt/freesurfer-7.2.0/.license:ro"])
    return [*command, str(image), PRIMX_PATH, *cmd_args]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_task_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def task_duration_seconds(task: PipelineTask) -> int | None:
    start = parse_task_datetime(task.start_time)
    if not start:
        return None
    end = parse_task_datetime(task.end_time) or datetime.now(timezone.utc)
    seconds = round((end - start).total_seconds())
    return seconds if seconds >= 0 else None


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def finalize_task_time(task: PipelineTask) -> int | None:
    task.duration_seconds = task_duration_seconds(task)
    return task.duration_seconds


def write_elapsed_log(log_path: Path | None, task: PipelineTask, label: str = "Elapsed time") -> None:
    if log_path is None:
        return
    seconds = finalize_task_time(task)
    if seconds is None:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            print(f"[agent] {label}: {format_duration(seconds)} ({seconds}s)", file=log_file, flush=True)
    except OSError:
        pass


def task_response(task: PipelineTask) -> Dict[str, Any]:
    return {
        "taskId": task.task_id,
        "status": task.status,
        "currentStep": task.current_step,
        "message": task.message,
        "progress": task.progress,
        "subjectId": task.subject_id,
        "workspaceDirectory": task.workspace_directory,
        "outPath": task.out_path,
        "species": task.species,
        "segSpecies": task.seg_species,
        "steps": task.steps,
        "threads": task.threads,
        "startTime": task.start_time,
        "endTime": task.end_time,
        "durationSeconds": task_duration_seconds(task),
        "error": task.error,
        "logPath": task.log_path,
    }


def ensure_primx_exists() -> None:
    if not Path(PRIMX_PATH).exists():
        raise RuntimeError(f"primx not found at {PRIMX_PATH}")


def is_nifti_path(value: Any) -> bool:
    return bool(value and (value.lower().endswith(".nii") or value.lower().endswith(".nii.gz")))


def existing_file(path_value: Path) -> bool:
    return path_value.is_file()


def has_required_files(base_dir: Path, relative_files: List[str]) -> bool:
    return all(existing_file(base_dir / rel_path) for rel_path in relative_files)


def require_step_prerequisites(args: RunPipelineArgs, step: str) -> None:
    out_path = Path(args.out_path or "")
    subject_dir = out_path / args.subject_id
    backup_dir = out_path / f"{args.subject_id}_1mm"

    if step == "rescale":
        source_dir = backup_dir if backup_dir.exists() else subject_dir
        required_volumes = [
            f"mri/{name}.mgz"
            for name in ("rawavg", "orig", "brain.finalsurfs", "brainmask", "wm", "aseg.presurf")
        ]
        required_surfaces = [
            f"surf/{hemi}.{name}"
            for name in ("white", "smoothwm", "pial")
            for hemi in ("lh", "rh")
        ]
        if not has_required_files(source_dir, [*required_volumes, *required_surfaces]):
            raise RuntimeError(
                f"rescale requires completed preprocess-3 FreeSurfer outputs in {source_dir}. "
                "Missing required files such as mri/brain.finalsurfs.mgz; "
                "run preprocess-3 successfully before rescale."
            )

    if step == "freesurfer2caret":
        required = [f"surf/{hemi}.{name}" for hemi in ("lh", "rh") for name in ("white", "pial")]
        if not has_required_files(subject_dir, required):
            raise RuntimeError(
                f"freesurfer2caret requires completed surface outputs in {subject_dir}/surf. "
                "Run preprocess-3 and rescale successfully before freesurfer2caret."
            )


def build_seg_input(args: RunPipelineArgs, steps: List[str], step: str) -> str:
    step_index = steps.index(step)
    preprocess_index = steps.index("preprocess-1") if "preprocess-1" in steps else -1
    seg_brain_index = steps.index("seg-brain") if "seg-brain" in steps else -1
    acpc_index = steps.index("acpc-align") if "acpc-align" in steps else -1
    preprocessed_t1 = Path(args.out_path or "") / "T1.nii.gz"
    brain_image = Path(args.out_path or "") / "brain.nii.gz"

    if step == "seg-wm":
        has_brain_before = (
            (seg_brain_index != -1 and seg_brain_index < step_index)
            or (acpc_index != -1 and acpc_index < step_index)
        )
        if has_brain_before or existing_file(brain_image):
            return str(brain_image)
        return args.t1_path if is_nifti_path(args.t1_path) else str(brain_image)

    if preprocess_index != -1 and preprocess_index < step_index:
        return str(preprocessed_t1)
    if existing_file(preprocessed_t1):
        return str(preprocessed_t1)
    return args.t1_path if is_nifti_path(args.t1_path) else str(preprocessed_t1)


def build_command_args(args: RunPipelineArgs, steps: List[str], step: str) -> List[str]:
    cmd_args: List[str] = []
    require_step_prerequisites(args, step)
    if step == "fastsurfer":
        cmd_args.extend(
            [
                "human",
                "fastsurfer",
                "-t1_path",
                args.t1_path or "",
                "-id",
                args.subject_id,
                "-out_path",
                args.workspace_directory,
            ]
        )
        return cmd_args
    if step == "preprocess-1":
        cmd_args.extend(
            [
                "neuro",
                "preprocess-1",
                "-t1_path",
                args.t1_path or "",
                "-out_path",
                args.out_path,
            ]
        )
        if args.species:
            cmd_args.extend(["-species", args.species])
        if args.sphinx:
            cmd_args.append("-sphinx")
        if args.no_std_orient:
            cmd_args.append("-no_std_orient")
        if args.average_hcp:
            cmd_args.append("-average_HCP")
        if args.denoise:
            cmd_args.append("-denoise")
        if args.keep_tmp:
            cmd_args.append("-tmp")
        return cmd_args
    if step in {"seg-brain", "seg-wm"}:
        input_image = build_seg_input(args, steps, step)
        input_path = Path(input_image)
        if not input_path.is_file():
            expected = "T1.nii.gz" if step == "seg-brain" else "brain.nii.gz"
            raise RuntimeError(
                f"{step} requires an input image. Expected {input_path} ({expected}) "
                "or provide Image to be segmented manually."
            )
        cmd_args.extend(
            [
                "seg",
                "brain" if step == "seg-brain" else "wm",
                "-input_image",
                input_image,
                "-output_dir",
                args.out_path,
            ]
        )
        if args.seg_species:
            cmd_args.extend(["-species", args.seg_species])
        if args.model_dir:
            cmd_args.extend(["-model_dir", args.model_dir])
        return cmd_args
    if step == "acpc-align":
        cmd_args.extend(
            [
                "neuro",
                "acpc-align",
                "-out_path",
                args.out_path,
            ]
        )
        if args.species:
            cmd_args.extend(["-species", args.species])
        if args.brain_size is not None:
            cmd_args.extend(["-brainSize", str(args.brain_size)])
        if args.reference:
            cmd_args.extend(["-reference", args.reference])
        if args.with_wm:
            cmd_args.append("-with_wm")
        return cmd_args
    if step == "preprocess-3":
        cmd_args.extend(
            [
                "neuro",
                "preprocess-3",
                "-id",
                args.subject_id,
                "-out_path",
                args.out_path,
            ]
        )
        if args.species:
            cmd_args.extend(["-species", args.species])
        cmd_args.extend(["-threads", str(args.threads)])
        return cmd_args
    if step == "rescale":
        cmd_args.extend(
            [
                "neuro",
                "rescale",
                "-id",
                args.subject_id,
                "-out_path",
                args.out_path,
            ]
        )
        if args.species:
            cmd_args.extend(["-species", args.species])
        return cmd_args
    if step == "freesurfer2caret":
        cmd_args.extend(
            [
                "neuro",
                "freesurfer2caret",
                "-id",
                args.subject_id,
                "-out_path",
                args.out_path,
            ]
        )
        if args.species:
            cmd_args.extend(["-species", args.species])
        if args.low_res_mesh is not None:
            cmd_args.extend(["-LowResMesh", str(args.low_res_mesh)])
        if args.inflate_extra_scale is not None:
            cmd_args.extend(["-InflateExtraScale", str(args.inflate_extra_scale)])
        if args.msmsulc:
            cmd_args.append("-msmsulc")
        return cmd_args
    raise RuntimeError(f"Unsupported step: {step}")


def prepare_subject_for_rerun(args: RunPipelineArgs) -> List[str]:
    """Clear only the FreeSurfer directories that block rerunning selected steps."""
    out_path = Path(args.out_path or "")
    subject_dir = out_path / args.subject_id
    backup_dir = out_path / f"{args.subject_id}_1mm"
    log_dir = out_path / "logs"
    preprocess3_intermediates = [
        out_path / "T1_truncate.nii.gz",
        out_path / "T1_1mm.nii.gz",
    ]
    actions: List[str] = []

    def remove_path(target: Path) -> None:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    if "preprocess-3" in args.steps:
        for directory in (subject_dir, backup_dir):
            if directory.exists():
                remove_path(directory)
                actions.append(f"removed FreeSurfer directory {directory}")
        for intermediate in preprocess3_intermediates:
            if intermediate.exists():
                remove_path(intermediate)
                actions.append(f"removed preprocess-3 intermediate {intermediate}")
        if log_dir.exists():
            remove_path(log_dir)
            actions.append(f"removed old logs {log_dir}")
        return actions

    if "rescale" in args.steps and backup_dir.exists():
        if subject_dir.exists():
            remove_path(subject_dir)
            actions.append(f"removed previous rescaled output {subject_dir}")
        backup_dir.rename(subject_dir)
        actions.append(f"restored 1mm backup {backup_dir} -> {subject_dir}")
        if log_dir.exists():
            remove_path(log_dir)
            actions.append(f"removed old logs {log_dir}")

    return actions


def run_pipeline_task(task: PipelineTask, args: RunPipelineArgs) -> None:
    log_path: Path | None = None

    def mark_cancelled() -> None:
        task.status = "cancelled"
        task.message = "Cancelled by user"
        task.end_time = task.end_time or utc_now_iso()
        if log_path is not None:
            try:
                with open(log_path, "a", encoding="utf-8") as log_file:
                    print("[agent] Cancelled by user", file=log_file, flush=True)
                    print(f"[agent] End time: {task.end_time}", file=log_file, flush=True)
            except OSError:
                pass
        write_elapsed_log(log_path, task)

    try:
        # A queued task may have been cancelled before its worker starts. Check
        # before creating output directories or performing destructive rerun prep.
        if task.cancel_requested:
            mark_cancelled()
            return

        ensure_primx_exists()
        task.start_time = utc_now_iso()
        Path(args.out_path or "").mkdir(parents=True, exist_ok=True)
        cleanup_actions = prepare_subject_for_rerun(args)
        log_dir = Path(args.out_path or "") / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"agent_pipeline_{task.task_id}.log"
        task.log_path = str(log_path)

        with open(log_path, "a", encoding="utf-8") as log_file:
            print(f"[agent] Task {task.task_id} started", file=log_file, flush=True)
            print(f"[agent] Start time: {task.start_time}", file=log_file, flush=True)
            print(f"[agent] Subject: {args.subject_id}", file=log_file, flush=True)
            print(f"[agent] Output: {args.out_path}", file=log_file, flush=True)
            print(f"[agent] CPU threads per Preprocess-3 task: {args.threads}", file=log_file, flush=True)
            if cleanup_actions:
                print("[agent][prepare] Existing outputs required step-specific preparation.", file=log_file, flush=True)
                for action in cleanup_actions:
                    print(f"[agent][prepare] {action}", file=log_file, flush=True)

        if task.cancel_requested:
            mark_cancelled()
            return

        total = len(args.steps)
        for index, step in enumerate(args.steps):
            if task.cancel_requested:
                mark_cancelled()
                return

            task.status = "running"
            task.current_step = step
            task.message = f"Running {step}"
            task.progress = int((index / total) * 100)

            cmd_args = build_command_args(args, args.steps, step)
            process_command = build_process_command(args, cmd_args, step)
            segmentation_slot_acquired = False
            if step in DEEP_LEARNING_SEGMENTATION_STEPS:
                task.message = f"Waiting for segmentation resource: {step}"
                with open(log_path, "a", encoding="utf-8") as log_file:
                    print(
                        f"[agent] Waiting for the shared segmentation resource: {step}",
                        file=log_file,
                        flush=True,
                    )
                segmentation_slot_acquired = acquire_segmentation_resource(task)
                if not segmentation_slot_acquired:
                    mark_cancelled()
                    return
                if task.cancel_requested:
                    release_segmentation_resource()
                    mark_cancelled()
                    return
                task.message = f"Running {step}"

            try:
                with open(log_path, "a", encoding="utf-8") as log_file:
                    print(f"[agent] Running step {index + 1}/{total}: {step}", file=log_file, flush=True)
                    if segmentation_slot_acquired:
                        print(
                            f"[agent] Acquired shared segmentation resource: {step}",
                            file=log_file,
                            flush=True,
                        )
                    print(f"[agent][command] {' '.join(process_command)}", file=log_file, flush=True)
                    env = os.environ.copy()
                    env["PYTHONUNBUFFERED"] = "1"
                    process = subprocess.Popen(
                        process_command,
                        stdout=log_file,
                        stderr=log_file,
                        env=env,
                        start_new_session=(os.name == "posix"),
                    )
                    task.process = process
                    register_process(task.task_id, process)
                    # Close the small race where cancellation arrives after
                    # Popen succeeds but before cancel_task can see task.process.
                    if task.cancel_requested:
                        terminate_process(process)
                    return_code = process.wait()
            finally:
                task.process = None
                unregister_process(task.task_id)
                if segmentation_slot_acquired:
                    release_segmentation_resource()

            with open(log_path, "a", encoding="utf-8") as log_file:
                print(f"[agent] Step {step} exited with code {return_code}", file=log_file, flush=True)
                if task.cancel_requested:
                    mark_cancelled()
                    return
                if return_code != 0:
                    task.status = "failed"
                    task.error = f"Step {step} failed with code {return_code}"
                    task.message = task.error
                    task.end_time = utc_now_iso()
                    print(f"[agent] End time: {task.end_time}", file=log_file, flush=True)
                    write_elapsed_log(log_path, task)
                    return

        task.status = "completed"
        task.progress = 100
        task.message = "Pipeline completed"
        task.end_time = utc_now_iso()
        with open(log_path, "a", encoding="utf-8") as log_file:
            print("[agent] Pipeline completed", file=log_file, flush=True)
            print(f"[agent] End time: {task.end_time}", file=log_file, flush=True)
        write_elapsed_log(log_path, task, "Total runtime")
    except Exception as exc:
        if task.cancel_requested:
            mark_cancelled()
            return
        task.status = "failed"
        task.error = str(exc)
        task.message = str(exc)
        task.end_time = utc_now_iso()
        finalize_task_time(task)
        task.process = None
        unregister_process(task.task_id)
        if log_path is not None:
            try:
                with open(log_path, "a", encoding="utf-8") as log_file:
                    print(f"[agent][error] {exc}", file=log_file, flush=True)
                    print(traceback.format_exc(), file=log_file, flush=True)
                    print(f"[agent] End time: {task.end_time}", file=log_file, flush=True)
            except OSError:
                pass
        write_elapsed_log(log_path, task)
        return
