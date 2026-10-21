"""Offline routing, source-only isolation, bounds and immutable-parent tests."""

import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_analysis_agent import agent, TestOnlyExecutor
from test_analysis_knowledge_profiles import profiles

evidence = importlib.import_module(agent.__package__ + ".analysis_evidence")
research = importlib.import_module(agent.__package__ + ".analysis_research")
knowledge_module = importlib.import_module(agent.__package__ + ".analysis_knowledge")


class Stores:
    def __init__(self):
        self.calls = []
        self._source_graph = SimpleNamespace(sha256="b" * 64)

    def search_research_text(self, query, limit):
        self.calls.append(("text_search", query, limit))
        return {
            "status": "ok", "route": "registered_parent_text_lexical_only",
            "release_sha256": "a" * 64,
            "sources": [{
                "source_id": "PARENT", "heading": "Official original",
                "source_url": "https://example.invalid/source",
                "excerpt": {"text": "Original applicability and exception."},
            }],
        }

    def read_research_text(self, identifier, start, cap):
        self.calls.append(("text_read", identifier, start, cap))
        return {
            "id": identifier, "source_url": "https://example.invalid/source",
            "text": "Original bounded passage.", "truncated": True, "next_char": 100,
            "release_sha256": "a" * 64,
        }

    def search_source_graph(self, query, limit):
        self.calls.append(("software_search", query, limit))
        return {
            "status": "ok", "graph_sha256": "b" * 64,
            "results": [{
                "id": "SW", "name": "Software input", "summary": "Input contract",
                "source": {"url": "https://example.invalid/code"},
            }],
        }

    def read_source_graph(self, identifier):
        self.calls.append(("software_read", identifier))
        return {
            "node": {"name": "Software input"},
            "evidence": {"url": "https://example.invalid/code", "text": "Original code"},
        }


class Graph:
    sources = {"SRC": {"url": "https://example.invalid/method"}}

    def search(self, query, limit):
        return {
            "status": "ok", "release_sha256": "c" * 64,
            "results": [{
                "method_id": "M", "name": "Method", "purpose": "Descriptive purpose",
                "source_ids": ["SRC"],
            }],
        }

    def read(self, identifier):
        return {
            "method": {"name": "Method", "purpose": "Descriptive purpose"},
            "source_evidence": [{"source_id": "SRC", "url": self.sources["SRC"]["url"]}],
            "release_sha256": "c" * 64, "executable": False,
        }


def gateway(monkeypatch, name="method_graph"):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", name)
    stores = Stores()
    return evidence.EvidenceGateway(stores, Graph, profiles.load_knowledge_profile()), stores


def test_default_search_is_only_original_text(monkeypatch):
    adapter, stores = gateway(monkeypatch)
    result = adapter.search("area")
    assert result["status"] == "ok"
    assert stores.calls == [("text_search", "area", 5)]
    hit = result["results"][0]
    assert set(hit) == {"id", "kind", "title", "snippet", "source_url", "release_sha256"}
    assert hit["id"] == "source_text:PARENT"
    assert hit["release_sha256"] == "a" * 64


def test_explicit_kinds_are_routed_and_globally_bounded(monkeypatch):
    adapter, stores = gateway(monkeypatch)
    result = adapter.search("area", ["source_text", "software_contract", "method"], 3)
    assert [hit["kind"] for hit in result["results"]] == [
        "source_text", "software_contract", "method",
    ]
    assert len(adapter.search("area", ["source_text", "software_contract", "method"], 1)["results"]) == 1


@pytest.mark.parametrize(
    "identifier,kind,digest",
    [("source_text:PARENT", "source_text", "a" * 64),
     ("software_contract:SW", "software_contract", "b" * 64),
     ("method:M", "method", "c" * 64)],
)
def test_prefixed_reads_preserve_source_and_release(identifier, kind, digest, monkeypatch):
    adapter, stores = gateway(monkeypatch)
    result = adapter.read(identifier)
    assert result["id"] == identifier and result["kind"] == kind
    assert result["release_sha256"] == digest
    assert result["executable"] is False
    if kind == "source_text":
        assert result["next_read"] == {
            "id": identifier, "start_char": 100, "max_chars": 8000,
        }
    if kind == "method":
        assert result["source_reads"] == [{"id": "source_text:METHOD_SOURCE_SRC"}]


@pytest.mark.parametrize("name", ["text_retrieval", "text_plus_rules"])
@pytest.mark.parametrize("kind", ["method", "software_contract"])
def test_text_groups_reject_nontext_search_and_read(name, kind, monkeypatch):
    adapter, stores = gateway(monkeypatch, name)
    with pytest.raises(ValueError, match="disabled"):
        adapter.search("area", [kind])
    with pytest.raises(ValueError, match="disabled"):
        adapter.read(kind + ":M")
    assert not stores.calls


def test_no_knowledge_rejects_even_direct_unified_tool_use(monkeypatch):
    adapter, stores = gateway(monkeypatch, "no_knowledge")
    with pytest.raises(ValueError, match="disabled"):
        adapter.search("area")
    assert not stores.calls


@pytest.mark.parametrize("identifier", [
    "PARENT", "bad:PARENT", "source_text:../secret", "source_text:/etc/passwd",
    "source_text:", "source_text:a\\b", "source_text:a\x00b",
])
def test_forged_ids_are_not_paths(identifier, monkeypatch):
    adapter, stores = gateway(monkeypatch)
    with pytest.raises(ValueError):
        adapter.read(identifier)
    assert not stores.calls


@pytest.mark.parametrize("query,kinds,limit", [
    ("", None, 5), ("x" * 1001, None, 5), ("area", [], 5),
    ("area", ["unknown"], 5), ("area", ["method", "method"], 5),
    ("area", "source_text", 5), ("area", None, True), ("area", None, 0),
    ("area", None, 9),
])
def test_invalid_queries_fail_before_store_access(query, kinds, limit, monkeypatch):
    adapter, stores = gateway(monkeypatch)
    with pytest.raises(ValueError):
        adapter.search(query, kinds, limit)
    assert not stores.calls


def test_unavailable_source_release_is_not_success(monkeypatch):
    adapter, stores = gateway(monkeypatch)
    stores.search_research_text = lambda *args: {
        "status": "unavailable", "sources": [], "reason": "not configured",
    }
    result = adapter.search("area")
    assert result["status"] == "unavailable" and not result["results"]


def test_unified_tool_reserves_exactly_one_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_KNOWLEDGE_PROFILE", "text_retrieval")
    work = tmp_path / "work"
    work.mkdir()
    stores = Stores()
    tools = agent.AnalysisTools(work, [], TestOnlyExecutor(work, []), stores)
    assert tools.search_evidence("area")["status"] == "ok"
    assert tools.tool_calls == 1
    assert tools.read_evidence("source_text:PARENT")["status"] == "ok"
    assert tools.tool_calls == 2


@pytest.fixture
def text_release(tmp_path):
    root = tmp_path / "release"
    root.mkdir()
    documents = []
    for identifier, heading, text in [
        ("P1", "Surface area", "Original surface area requires an appropriate mesh."),
        ("P2", "Volume", "Original volume documentation."),
    ]:
        documents.append({
            "id": identifier, "heading": heading, "url": "https://example.invalid/" + identifier,
            "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        })
    files = {
        "documents.json": json.dumps(documents),
        "worker.py": "raise AssertionError('search must not execute this worker')",
        "domain_graph.json": '{"nodes": [], "edges": []}',
    }
    config = {"schema": "primatex.research_retrieval.v1", "python": sys.executable}
    for name, content in files.items():
        raw = content.encode()
        (root / name).write_bytes(raw)
    # Explicit protocol keys, independent of filename-to-key conventions.
    config["worker_sha256"] = hashlib.sha256((root / "worker.py").read_bytes()).hexdigest()
    config["documents_sha256"] = hashlib.sha256((root / "documents.json").read_bytes()).hexdigest()
    config["domain_graph_sha256"] = hashlib.sha256((root / "domain_graph.json").read_bytes()).hexdigest()
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return root


def test_source_search_never_invokes_old_mixed_worker(text_release, monkeypatch):
    retriever = research.ResearchEvidenceRetriever(text_release)
    before = {path.name: path.read_bytes() for path in text_release.iterdir()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Combined graph retrieval must not run")

    monkeypatch.setattr(retriever, "_invoke", forbidden)
    result = retriever.search_text("surface area")
    assert [item["source_id"] for item in result["sources"]] == ["P1"]
    assert result["route"] == "registered_parent_text_lexical_only"
    assert result["native_graph_calls"] == 0
    assert result["retrieval_provider_http_calls"] == 0
    assert {path.name: path.read_bytes() for path in text_release.iterdir()} == before
    assert "derived_graph_hints" not in result


def test_source_only_read_rejects_graph_id_before_existing_reader(text_release, monkeypatch):
    retriever = research.ResearchEvidenceRetriever(text_release)
    seen = []
    monkeypatch.setattr(retriever, "read", lambda *args: seen.append(args))
    with pytest.raises(ValueError, match="original parent"):
        retriever.read_text("GRAPH_NODE")
    assert not seen


def test_registered_source_read_dispatches_to_existing_bounded_reader(text_release, monkeypatch):
    retriever = research.ResearchEvidenceRetriever(text_release)
    seen = []

    def read(*args):
        seen.append(args)
        return {"id": "P1", "text": "Original", "truncated": False}

    monkeypatch.setattr(retriever, "read", read)
    result = retriever.read_text("P1", 12, 100)
    assert seen == [("P1", 12, 100)]
    assert result["heading"] == "Surface area"


def test_changed_parent_catalogue_fails_before_retrieval(text_release):
    retriever = research.ResearchEvidenceRetriever(text_release)
    (text_release / "documents.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        retriever.search_text("surface")


def test_knowledge_store_delegates_only_to_text_methods(monkeypatch):
    store = object.__new__(knowledge_module.KnowledgeStore)
    retriever = SimpleNamespace(
        search_text=lambda query, limit: ("search_text", query, limit),
        read_text=lambda identifier, start, cap: ("read_text", identifier, start, cap),
    )
    monkeypatch.setattr(store, "_research_retriever", lambda: retriever)
    assert store.search_research_text("area", 2) == ("search_text", "area", 2)
    assert store.read_research_text("P1", 10, 100) == ("read_text", "P1", 10, 100)

