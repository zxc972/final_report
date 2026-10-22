"""Host-owned repository selection; runtime planning reads the unified SQLite copy."""

from __future__ import annotations

import os
from pathlib import Path

from .analysis_control_store import digest
from .analysis_unified_store import UnifiedKnowledge


def repository_for(tools):
    existing = getattr(tools, "unified_knowledge", None)
    if existing is not None:
        return existing
    if tools.control_store is None:
        raise ValueError("Unified planning requires protected analysis state")
    from .analysis_release import configured_research_root

    graph = getattr(tools, "_method_graph_store", None)
    release = getattr(graph, "root", None)
    if release is None:
        release = configured_research_root()
    configured = os.environ.get("AGENT_UNIFIED_GRAPH_DB")
    path = (
        Path(configured) if configured else tools.control_store.root / "unified.sqlite3"
    )
    for forbidden in [tools.workdir, *tools.input_roots]:
        if path.absolute().is_relative_to(forbidden.resolve()):
            raise ValueError(
                "Unified graph must remain outside all model-writable or input mounts"
            )
    store = UnifiedKnowledge(path)
    knowledge_root = Path(__file__).resolve().parent.parent / "knowledge_analysis"
    release_root = (
        Path(release) if release and (Path(release) / "config.json").is_file() else None
    )
    store.import_knowledge(knowledge_root, release_root)
    if (
        release
        and release_root is None
        and (Path(release) / "domain_graph.json").is_file()
    ):
        # Explicit custom/test graph, preserving its original unregistered-source
        # status rather than pretending it belongs to the frozen v13 release.
        graph_body, _ = store.document(
            "domain_graph", Path(release) / "domain_graph.json"
        )
        store.import_graph("domain_graph", graph_body)
    tools.unified_knowledge = store
    tools.knowledge_metadata["unified_knowledge"] = {
        "schema": "primatex.unified_graph.v1",
        "database_ref": str(path),
        "knowledge_sha256": store.knowledge_digest(),
        "unregistered_custom_release": release_root is None,
        "scope": "Source-bound development migration; not expert-reviewed scientific approval",
    }
    return store
