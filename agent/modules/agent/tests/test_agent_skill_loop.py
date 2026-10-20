"""Integration test for disclosure-before-execution in the Agent loop."""

import copy
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from modules.agent.backend import api


class AgentSkillLoopTests(unittest.TestCase):
    def test_first_skill_selection_discloses_and_second_executes(self) -> None:
        responses = [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_load",
                                    "type": "function",
                                    "function": {
                                        "name": "load-skill",
                                        "arguments": json.dumps({"skillName": "seg-brain"}),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_execute",
                                    "type": "function",
                                    "function": {
                                        "name": "seg-brain",
                                        "arguments": json.dumps(
                                            {
                                                "subjectId": "subject",
                                                "workspaceDirectory": "/tmp/workspace",
                                                "segSpecies": "rhesus",
                                            }
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "The segmentation task was submitted.",
                        }
                    }
                ]
            },
        ]
        message_snapshots = []

        async def fake_chat_completion(
            base_url,
            api_key,
            model,
            messages,
            tools,
        ):
            message_snapshots.append(copy.deepcopy(messages))
            return responses.pop(0)

        with (
            patch.object(api, "ACCESS_TOKEN", ""),
            patch.object(api, "PLATFORM_API_KEY", "test-key"),
            # Two budgeted iterations are enough for execution + final text.
            # The preceding disclosure round must not consume that budget.
            patch.object(api, "MAX_AGENT_ITERS", 2),
            patch.object(
                api,
                "load_platform_models",
                return_value=[{"id": "test-model", "label": "Test"}],
            ),
            patch.object(
                api,
                "call_chat_completions",
                side_effect=fake_chat_completion,
            ),
            patch.object(
                api,
                "execute_tool",
                return_value={"taskId": "agent_test", "status": "pending"},
            ) as execute_tool,
        ):
            with TestClient(api.build_app()) as client:
                response = client.post(
                    "/api/agent/chat",
                    json={
                        "message": "Segment this subject",
                        "provider": "platform",
                        "model": "test-model",
                    },
                )

        self.assertEqual(response.status_code, 200)
        execute_tool.assert_called_once()
        self.assertEqual(response.json()["metadata"]["loadedSkills"], ["seg-brain"])
        self.assertEqual(response.json()["metadata"]["llmIterations"], 3)
        self.assertEqual(response.json()["metadata"]["budgetedIterations"], 2)
        self.assertFalse(response.json()["metadata"]["hitIterationLimit"])

        load_messages = [
            message
            for message in message_snapshots[1]
            if message.get("role") == "tool"
        ]
        self.assertEqual(len(load_messages), 1)
        load_result = json.loads(load_messages[0]["content"])
        self.assertEqual(load_result["status"], "skill_loaded")
        self.assertFalse(load_result["executed"])
        self.assertNotIn("instructions", load_result)

        trusted_system = message_snapshots[1][0]["content"]
        self.assertIn("TRUSTED LOADED SKILL INSTRUCTIONS", trusted_system)
        self.assertIn("# Segmentation: Brain Extraction", trusted_system)

    def test_new_skill_load_defers_every_mixed_action_call(self) -> None:
        responses = [
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "load_brain",
                            "type": "function",
                            "function": {
                                "name": "load-skill",
                                "arguments": json.dumps({"skillName": "seg-brain"}),
                            },
                        }],
                    }
                }]
            },
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "load_wm",
                                "type": "function",
                                "function": {
                                    "name": "load-skill",
                                    "arguments": json.dumps({"skillName": "seg-wm"}),
                                },
                            },
                            {
                                "id": "deferred_brain_action",
                                "type": "function",
                                "function": {
                                    "name": "seg-brain",
                                    "arguments": json.dumps({
                                        "subjectId": "subject",
                                        "workspaceDirectory": "/tmp/workspace",
                                        "segSpecies": "rhesus",
                                    }),
                                },
                            },
                        ],
                    }
                }]
            },
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "execute_brain",
                            "type": "function",
                            "function": {
                                "name": "seg-brain",
                                "arguments": json.dumps({
                                    "subjectId": "subject",
                                    "workspaceDirectory": "/tmp/workspace",
                                    "segSpecies": "rhesus",
                                }),
                            },
                        }],
                    }
                }]
            },
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Done.",
                    }
                }]
            },
        ]
        snapshots = []

        async def fake_chat_completion(base_url, api_key, model, messages, tools):
            snapshots.append(copy.deepcopy(messages))
            return responses.pop(0)

        with (
            patch.object(api, "ACCESS_TOKEN", ""),
            patch.object(api, "PLATFORM_API_KEY", "test-key"),
            patch.object(api, "MAX_AGENT_ITERS", 2),
            patch.object(
                api,
                "load_platform_models",
                return_value=[{"id": "test-model", "label": "Test"}],
            ),
            patch.object(api, "call_chat_completions", side_effect=fake_chat_completion),
            patch.object(
                api,
                "execute_tool",
                return_value={"taskId": "agent_test", "status": "pending"},
            ) as execute_tool,
        ):
            with TestClient(api.build_app()) as client:
                response = client.post(
                    "/api/agent/chat",
                    json={
                        "message": "Load both segmentation skills and run brain segmentation",
                        "provider": "platform",
                        "model": "test-model",
                    },
                )

        self.assertEqual(response.status_code, 200)
        execute_tool.assert_called_once()
        self.assertEqual(
            response.json()["metadata"]["loadedSkills"],
            ["seg-brain", "seg-wm"],
        )

        mixed_round_results = {
            message["tool_call_id"]: json.loads(message["content"])
            for message in snapshots[2]
            if message.get("role") == "tool"
        }
        self.assertEqual(
            mixed_round_results["deferred_brain_action"]["status"],
            "action_deferred",
        )
        self.assertFalse(
            mixed_round_results["deferred_brain_action"]["executed"],
        )


if __name__ == "__main__":
    unittest.main()
