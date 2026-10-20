"""Tests for two-phase Skill loading."""

import json
import unittest

from modules.agent.backend.skills import (
    load_skills,
    parse_skill_load_requests,
    skill_catalog,
    skill_loaded_result,
    skill_loader_tool,
)


class SkillDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skills = load_skills()
        cls.skills_by_name = {skill.name: skill for skill in cls.skills}

    def test_initial_loader_exposes_metadata_but_not_action_schemas_or_body(self) -> None:
        loader = skill_loader_tool(self.skills)
        self.assertEqual(loader["function"]["name"], "load-skill")
        self.assertIn("seg-brain", loader["function"]["parameters"]["properties"]["skillName"]["enum"])
        self.assertNotIn("# Segmentation: Brain Extraction", str(loader))

        catalog = skill_catalog(self.skills)
        self.assertIn("`seg-brain`", catalog)
        self.assertNotIn("# Segmentation: Brain Extraction", catalog)
        self.assertIn(
            "Use proactively whenever species or segSpecies is required",
            catalog,
        )
        self.assertIn(
            "run this Skill before asking the user to identify the species",
            catalog,
        )

    def test_load_request_selects_skill_without_executing_action(self) -> None:
        calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "load-skill",
                    "arguments": json.dumps({"skillName": "seg-brain"}),
                },
            }
        ]
        requested, errors = parse_skill_load_requests(calls, self.skills_by_name)
        self.assertEqual(requested, {"seg-brain"})
        self.assertEqual(errors, {})

        result = skill_loaded_result(self.skills_by_name["seg-brain"])
        self.assertEqual(result["status"], "skill_loaded")
        self.assertFalse(result["executed"])
        self.assertNotIn("instructions", result)

    def test_invalid_load_request_is_rejected(self) -> None:
        calls = [
            {
                "id": "call_bad",
                "function": {
                    "name": "load-skill",
                    "arguments": json.dumps({"skillName": "not-a-skill"}),
                },
            }
        ]
        requested, errors = parse_skill_load_requests(calls, self.skills_by_name)
        self.assertEqual(requested, set())
        self.assertIn("call_bad", errors)


if __name__ == "__main__":
    unittest.main()
