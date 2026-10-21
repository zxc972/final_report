"""Validated, immutable knowledge exposure settings for controlled experiments."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

DEFAULT_PROFILE = "legacy_v13"
PROFILE_PATH = Path(__file__).resolve().parent.parent / "knowledge_analysis" / "profiles.json"
PROFILE_NAMES = {
    "legacy_v13", "no_knowledge", "text_retrieval", "text_plus_rules", "method_graph",
}
CONTROL_PROFILES = {"method_graph", "method_graph_gated", "product_graph_planner"}
EVIDENCE_KINDS = {"source_text", "software_contract", "method"}


@dataclass(frozen=True)
class KnowledgeProfile:
    name: str
    exposed_tools: tuple[str, ...]
    include_domain_rules: bool
    allowed_evidence_kinds: tuple[str, ...]
    all_knowledge_tools: frozenset[str]
    profiles_sha256: str


def load_knowledge_profile(path: Path | None = None) -> KnowledgeProfile:
    """Fail closed for an unknown name or malformed server-owned configuration."""
    selected = os.environ.get("AGENT_KNOWLEDGE_PROFILE", DEFAULT_PROFILE)
    location = Path(path) if path is not None else PROFILE_PATH
    if location.is_symlink() or not location.is_file() or location.stat().st_size > 32768:
        raise ValueError("Invalid knowledge profile configuration file")
    raw = location.read_bytes()
    config = json.loads(raw)
    if not isinstance(config, dict) or set(config) != PROFILE_NAMES | {"product_graph_planner"}:
        raise ValueError("Knowledge profile configuration must define the registered experiment groups")
    all_tools = set()
    for name, entry in config.items():
        if not isinstance(entry, dict):
            raise ValueError("Invalid knowledge profile entry")
        tools = entry.get("exposed_tools")
        kinds = entry.get("allowed_evidence_kinds")
        if (
            not isinstance(tools, list)
            or any(not isinstance(tool, str) or not tool.isidentifier() for tool in tools)
            or len(set(tools)) != len(tools)
            or type(entry.get("include_domain_rules")) is not bool
            or not isinstance(kinds, list)
            or any(not isinstance(kind, str) or kind not in EVIDENCE_KINDS for kind in kinds)
            or len(set(kinds)) != len(kinds)
        ):
            raise ValueError("Invalid tools, domain-rule flag or evidence kinds in " + name)
        all_tools.update(tools)
    if selected == "method_graph_gated":
        config[selected] = dict(config["method_graph"])
    if selected not in config:
        raise ValueError("Unknown AGENT_KNOWLEDGE_PROFILE: " + repr(selected))
    entry = config[selected]
    return KnowledgeProfile(
        name=selected,
        exposed_tools=tuple(entry["exposed_tools"]),
        include_domain_rules=entry["include_domain_rules"],
        allowed_evidence_kinds=tuple(entry["allowed_evidence_kinds"]),
        all_knowledge_tools=frozenset(all_tools),
        profiles_sha256=hashlib.sha256(raw).hexdigest(),
    )


def filter_functions(
    functions: list[Callable[..., Any]], profile: KnowledgeProfile,
) -> list[Callable[..., Any]]:
    """Keep common tools in their original order, using a single filtered registry."""
    names = [function.__name__ for function in functions]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate analysis tool name")
    if not set(profile.exposed_tools).issubset(names):
        raise ValueError("Configured knowledge tools are not installed")
    return [
        function for function in functions
        if function.__name__ not in profile.all_knowledge_tools
        or function.__name__ in profile.exposed_tools
    ]


def require_evidence_kind(profile: KnowledgeProfile, kind: str) -> None:
    """Enforce text-only groups on reads as well as search arguments."""
    if kind not in profile.allowed_evidence_kinds:
        raise ValueError("Evidence kind is disabled in this knowledge profile: " + kind)

