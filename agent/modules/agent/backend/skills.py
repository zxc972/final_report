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

"""Skill and knowledge loading helpers for tool exposure."""

import json
from typing import Any, Dict, List, Optional

import yaml

from .config import KNOWLEDGE_PATH, SKILLS_DIR
from .models import Skill

_KNOWLEDGE_CACHE: Optional[str] = None


def _load_frontmatter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        return {}
    try:
        parts = text.split("---")
        if len(parts) >= 3:
            return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return {}


def load_skills() -> List[Skill]:
    skills: List[Skill] = []
    if not SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted([p for p in SKILLS_DIR.iterdir() if p.is_dir()]):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        content = skill_md.read_text(encoding="utf-8")
        meta = _load_frontmatter(content)
        name = meta.get("name")
        description = meta.get("description")
        if not name or not description:
            continue
        if name != skill_dir.name:
            continue
        parameters_path = skill_dir / "assets" / "parameters.json"
        if not parameters_path.exists():
            continue
        parameters = json.loads(parameters_path.read_text(encoding="utf-8"))
        skills.append(
            Skill(
                name=name,
                description=description,
                parameters=parameters,
                filename=str(skill_md.relative_to(SKILLS_DIR)),
                content=content,
            )
        )
    return skills


def skill_tools(skills: List[Skill]) -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    for skill in skills:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": skill.parameters,
                },
            }
        )
    return tools


def skill_loader_tool(skills: List[Skill]) -> Dict[str, Any]:
    """Expose a read-only selector before any action tools are available."""
    return {
        "type": "function",
        "function": {
            "name": "load-skill",
            "description": (
                "Load the complete trusted instructions for a Skill before using its "
                "action tool. Loading a Skill does not execute the action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skillName": {
                        "type": "string",
                        "enum": [skill.name for skill in skills],
                        "description": "The Skill whose complete instructions are needed.",
                    }
                },
                "required": ["skillName"],
                "additionalProperties": False,
            },
        },
    }


def skill_catalog(skills: List[Skill]) -> str:
    """Render compact metadata used by the model to choose a Skill."""
    return "\n".join(f"- `{skill.name}`: {skill.description}" for skill in skills)


def parse_skill_load_requests(
    tool_calls: List[Dict[str, Any]],
    skills_by_name: Dict[str, Skill],
) -> tuple[set[str], Dict[str, str]]:
    """Return valid requested Skill names and per-call validation errors."""
    requested: set[str] = set()
    errors: Dict[str, str] = {}
    for call in tool_calls:
        function = call.get("function", {})
        if function.get("name") != "load-skill":
            continue
        call_id = call.get("id", "")
        try:
            arguments = json.loads(function.get("arguments", "{}"))
        except json.JSONDecodeError as exc:
            errors[call_id] = f"Invalid load-skill arguments: {exc}"
            continue
        skill_name = arguments.get("skillName")
        if skill_name not in skills_by_name:
            errors[call_id] = f"Unknown Skill: {skill_name}"
            continue
        requested.add(skill_name)
    return requested, errors


def skill_loaded_result(skill: Skill, already_loaded: bool = False) -> Dict[str, Any]:
    """Acknowledge loading; the instructions themselves live in system context."""
    return {
        "status": "skill_already_loaded" if already_loaded else "skill_loaded",
        "skill": skill.name,
        "executed": False,
        "nextAction": (
            "The complete Skill instructions are now in trusted system context. "
            "Plan with those instructions and call the newly available action tool "
            "only if it remains appropriate."
        ),
    }


def deferred_action_result(tool_name: str) -> Dict[str, Any]:
    """Return a phase-barrier result for an action mixed with a new Skill load."""
    return {
        "status": "action_deferred",
        "tool": tool_name,
        "executed": False,
        "nextAction": (
            "A new Skill was loaded in this round, so no action tools were executed. "
            "Re-plan using the trusted Skill instructions and call the action again "
            "in the next round if it is still appropriate."
        ),
    }


def load_knowledge() -> str:
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is not None:
        return _KNOWLEDGE_CACHE
    if not KNOWLEDGE_PATH.exists():
        _KNOWLEDGE_CACHE = ""
        return _KNOWLEDGE_CACHE
    _KNOWLEDGE_CACHE = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    return _KNOWLEDGE_CACHE
