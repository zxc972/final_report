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

"""Task registry and executor utilities for background pipeline runs."""

import os
import signal
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from .config import DEFAULT_MAX_WORKERS
from .models import PipelineTask

# Tracks live subprocesses by task ID for cancellation/shutdown.
PROCESS_REGISTRY: Dict[str, subprocess.Popen] = {}
PROCESS_LOCK = threading.Lock()
EXECUTOR_LOCK = threading.Lock()
EXECUTOR: Optional[ThreadPoolExecutor] = None
SEGMENTATION_RESOURCE_LOCK = threading.Lock()
CURRENT_MAX_WORKERS = DEFAULT_MAX_WORKERS


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_task_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class TaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, PipelineTask] = {}
        self._lock = threading.Lock()

    def create(self, task: PipelineTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task

    def get(self, task_id: str) -> Optional[PipelineTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs: Any) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for key, value in kwargs.items():
                setattr(task, key, value)


TASKS = TaskStore()


def ensure_executor(max_workers: int) -> ThreadPoolExecutor:
    global EXECUTOR, CURRENT_MAX_WORKERS
    with EXECUTOR_LOCK:
        if EXECUTOR is None or max_workers != CURRENT_MAX_WORKERS:
            if EXECUTOR is not None:
                EXECUTOR.shutdown(wait=False, cancel_futures=False)
            EXECUTOR = ThreadPoolExecutor(max_workers=max_workers)
            CURRENT_MAX_WORKERS = max_workers
    return EXECUTOR


def submit_pipeline_task(
    runner: Callable[..., Any],
    task: PipelineTask,
    *runner_args: Any,
) -> Future[Any]:
    """Dispatch every pipeline normally; resource-heavy steps lock in the runner."""
    executor = ensure_executor(CURRENT_MAX_WORKERS)
    return executor.submit(runner, task, *runner_args)


def acquire_segmentation_resource(task: PipelineTask) -> bool:
    """Wait interruptibly for the single in-process DL segmentation slot."""
    while not task.cancel_requested:
        if SEGMENTATION_RESOURCE_LOCK.acquire(timeout=0.2):
            return True
    return False


def release_segmentation_resource() -> None:
    SEGMENTATION_RESOURCE_LOCK.release()


def normalize_max_workers(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return CURRENT_MAX_WORKERS
    return max(1, min(parsed, 64))


def register_process(task_id: str, process: subprocess.Popen[str]) -> None:
    with PROCESS_LOCK:
        PROCESS_REGISTRY[task_id] = process


def unregister_process(task_id: str) -> None:
    with PROCESS_LOCK:
        PROCESS_REGISTRY.pop(task_id, None)


def terminate_process(process: subprocess.Popen[str]) -> None:
    """Terminate the full subprocess group when supported."""
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except Exception:
            pass


def cancel_task(task: PipelineTask) -> None:
    """Cancel a queued future or terminate the currently running process tree."""
    if task.status in {"completed", "failed", "cancelled"}:
        return
    task.cancel_requested = True
    if task.future is not None:
        task.future.cancel()
    if task.process is not None:
        terminate_process(task.process)
    task.status = "cancelled"
    task.message = "Cancelled by user"
    task.end_time = task.end_time or utc_now_iso()
    if task.start_time:
        start = parse_task_datetime(task.start_time)
        end = parse_task_datetime(task.end_time)
        task.duration_seconds = round((end - start).total_seconds()) if start and end else None


def shutdown_cleanup() -> None:
    global EXECUTOR
    with PROCESS_LOCK:
        processes = list(PROCESS_REGISTRY.values())
        PROCESS_REGISTRY.clear()
    for process in processes:
        terminate_process(process)
    with EXECUTOR_LOCK:
        if EXECUTOR is not None:
            EXECUTOR.shutdown(wait=False, cancel_futures=False)
            EXECUTOR = None
