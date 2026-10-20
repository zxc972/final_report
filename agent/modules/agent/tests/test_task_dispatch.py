"""Tests for Agent task dispatch and cancellation."""

import unittest
from unittest.mock import Mock, patch

from modules.agent.backend import tasks
from modules.agent.backend.models import PipelineTask


def make_task(steps: list[str]) -> PipelineTask:
    return PipelineTask(
        task_id="agent_test",
        subject_id="subject",
        workspace_directory="/tmp/workspace",
        out_path="/tmp/workspace/subject",
        steps=steps,
        species=None,
        seg_species=None,
        t1_path=None,
        model_dir=None,
        brain_size=None,
        reference=None,
        low_res_mesh=None,
        threads=2,
    )


class TaskDispatchTests(unittest.TestCase):
    @patch("modules.agent.backend.tasks.ensure_executor")
    def test_all_pipelines_use_general_executor(self, ensure_executor: Mock) -> None:
        general_executor = Mock()
        submitted_future = Mock()
        general_executor.submit.return_value = submitted_future
        ensure_executor.return_value = general_executor
        runner = Mock()
        task = make_task(["preprocess-1", "seg-brain", "preprocess-3"])
        args = object()

        result = tasks.submit_pipeline_task(runner, task, args)

        general_executor.submit.assert_called_once_with(runner, task, args)
        self.assertIs(result, submitted_future)

    def test_cancelled_task_does_not_wait_for_segmentation_resource(self) -> None:
        task = make_task(["seg-brain"])
        task.cancel_requested = True
        self.assertFalse(tasks.acquire_segmentation_resource(task))

    @patch("modules.agent.backend.tasks.terminate_process")
    def test_cancel_task_cancels_future_and_process(self, terminate_process: Mock) -> None:
        task = make_task(["seg-brain"])
        task.future = Mock()
        task.process = Mock()

        tasks.cancel_task(task)

        task.future.cancel.assert_called_once_with()
        terminate_process.assert_called_once_with(task.process)
        self.assertEqual(task.status, "cancelled")
        self.assertTrue(task.cancel_requested)

    def test_completed_task_is_not_relabelled_cancelled(self) -> None:
        task = make_task(["seg-brain"])
        task.status = "completed"

        tasks.cancel_task(task)

        self.assertEqual(task.status, "completed")
        self.assertFalse(task.cancel_requested)


if __name__ == "__main__":
    unittest.main()
