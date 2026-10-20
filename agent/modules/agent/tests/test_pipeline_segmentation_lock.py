"""Tests for step-scoped deep-learning segmentation serialization."""

import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

from modules.agent.backend.models import PipelineTask, RunPipelineArgs
from modules.agent.backend.pipeline import run_pipeline_task


def make_task(task_id: str, out_path: str, steps: list[str]) -> PipelineTask:
    return PipelineTask(
        task_id=task_id,
        subject_id=task_id,
        workspace_directory=str(Path(out_path).parent),
        out_path=out_path,
        steps=steps,
        species=None,
        seg_species="rhesus",
        t1_path=None,
        model_dir=None,
        brain_size=None,
        reference=None,
        low_res_mesh=None,
        threads=2,
    )


def make_args(task: PipelineTask) -> RunPipelineArgs:
    return RunPipelineArgs(
        subjectId=task.subject_id,
        workspaceDirectory=task.workspace_directory,
        steps=task.steps,
        segSpecies=task.seg_species,
        out_path=task.out_path,
    )


class PipelineSegmentationLockTests(unittest.TestCase):
    def test_resource_lock_wraps_only_segmentation_steps(self) -> None:
        class ImmediateProcess:
            _next_pid = 2000

            def __init__(self, *args, **kwargs):
                type(self)._next_pid += 1
                self.pid = type(self)._next_pid

            def wait(self):
                return 0

            def poll(self):
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            task = make_task(
                "subject",
                str(Path(tmp) / "subject"),
                ["preprocess-1", "seg-brain", "preprocess-3"],
            )
            acquire = Mock(return_value=True)
            release = Mock()

            with (
                patch(
                    "modules.agent.backend.pipeline.ensure_primx_exists",
                    return_value=None,
                ),
                patch(
                    "modules.agent.backend.pipeline.build_command_args",
                    return_value=["command"],
                ),
                patch(
                    "modules.agent.backend.pipeline.subprocess.Popen",
                    side_effect=ImmediateProcess,
                ),
                patch(
                    "modules.agent.backend.pipeline.acquire_segmentation_resource",
                    acquire,
                ),
                patch(
                    "modules.agent.backend.pipeline.release_segmentation_resource",
                    release,
                ),
            ):
                run_pipeline_task(task, make_args(task))

        acquire.assert_called_once_with(task)
        release.assert_called_once_with()
        self.assertEqual(task.status, "completed")

    def test_two_segmentation_steps_never_overlap(self) -> None:
        active = 0
        max_active = 0
        counter_lock = threading.Lock()

        class FakeProcess:
            _next_pid = 1000

            def __init__(self, *args, **kwargs):
                nonlocal active, max_active
                type(self)._next_pid += 1
                self.pid = type(self)._next_pid
                with counter_lock:
                    active += 1
                    max_active = max(max_active, active)

            def wait(self):
                nonlocal active
                time.sleep(0.05)
                with counter_lock:
                    active -= 1
                return 0

            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            task_a = make_task("subject_a", str(Path(tmp) / "subject_a"), ["seg-brain"])
            task_b = make_task("subject_b", str(Path(tmp) / "subject_b"), ["seg-wm"])

            with (
                patch(
                    "modules.agent.backend.pipeline.ensure_primx_exists",
                    return_value=None,
                ),
                patch(
                    "modules.agent.backend.pipeline.build_command_args",
                    return_value=["seg", "brain"],
                ),
                patch(
                    "modules.agent.backend.pipeline.subprocess.Popen",
                    side_effect=FakeProcess,
                ),
            ):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [
                        executor.submit(run_pipeline_task, task_a, make_args(task_a)),
                        executor.submit(run_pipeline_task, task_b, make_args(task_b)),
                    ]
                    for future in futures:
                        future.result(timeout=2)

        self.assertEqual(max_active, 1)
        self.assertEqual(task_a.status, "completed")
        self.assertEqual(task_b.status, "completed")

    def test_cancelled_queued_task_does_not_run_destructive_prepare(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "subject"
            protected_dir = out_path / "subject"
            protected_dir.mkdir(parents=True)
            marker = protected_dir / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            task = make_task("subject", str(out_path), ["preprocess-3"])
            task.cancel_requested = True

            with patch(
                "modules.agent.backend.pipeline.ensure_primx_exists",
                return_value=None,
            ):
                run_pipeline_task(task, make_args(task))

            self.assertEqual(task.status, "cancelled")
            self.assertTrue(marker.exists())
            self.assertIsNone(task.start_time)


if __name__ == "__main__":
    unittest.main()
