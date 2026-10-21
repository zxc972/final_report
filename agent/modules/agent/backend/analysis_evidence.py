"""Typed, profile-bound access to original text, software contracts and methods."""

from __future__ import annotations

from typing import Any, Callable
import base64
import binascii

from .analysis_knowledge_profiles import KnowledgeProfile, require_evidence_kind

PREFIXES = {
    "source_text": "source_text:",
    "software_contract": "software_contract:",
    "method": "method:",
}


def evidence_id(kind: str, identifier: str) -> str:
    if (
        kind not in PREFIXES
        or not isinstance(identifier, str)
        or not 1 <= len(identifier) <= 200
        or any(character in identifier for character in ("\\", "\x00"))
        or any(ord(character) < 32 for character in identifier)
        or identifier.startswith("/")
        or ("/" in identifier and kind != "software_contract")
        or ".." in identifier
    ):
        raise ValueError("Use a bounded registered evidence ID, never a path")
    # Software graph node keys may contain an interface source path. They are
    # dictionary keys, never filesystem paths. Encode these keys in the public
    # namespace; reads still require membership in SourceContractGraph.nodes.
    if kind == "software_contract" and ("/" in identifier or identifier.startswith("~")):
        identifier = "~" + base64.urlsafe_b64encode(identifier.encode()).decode().rstrip("=")
    return PREFIXES[kind] + identifier


def split_evidence_id(identifier: str) -> tuple[str, str]:
    if not isinstance(identifier, str) or len(identifier) > (360 if identifier.startswith("software_contract:~") else 240):
        raise ValueError("Invalid evidence ID")
    for kind, prefix in PREFIXES.items():
        if identifier.startswith(prefix):
            native = identifier[len(prefix):]
            if kind == "software_contract" and native.startswith("~"):
                try:
                    native = base64.b64decode(native[1:] + "=" * (-len(native[1:]) % 4), altchars=b"-_", validate=True).decode("utf-8")
                except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
                    raise ValueError("Invalid encoded software node ID") from exc
            if evidence_id(kind, native) != identifier:
                raise ValueError("Use a canonical registered evidence ID")
            return kind, native
    raise ValueError("Unknown evidence ID prefix")


def _hit(
    kind: str, identifier: str, title: str, snippet: str,
    source_url: str | None, release_sha256: str | None,
) -> dict[str, Any]:
    return {
        "id": evidence_id(kind, identifier),
        "kind": kind,
        "title": title,
        "snippet": snippet,
        "source_url": source_url,
        "release_sha256": release_sha256,
    }


class EvidenceGateway:
    """Adapters call existing stores directly; the outer tool reserves one attempt."""

    def __init__(
        self, knowledge: Any, method_graph: Callable[[], Any], profile: KnowledgeProfile,
    ) -> None:
        self.knowledge = knowledge
        self.method_graph = method_graph
        self.profile = profile

    def search(
        self, query: str, kinds: list[str] | None = None, limit: int = 5,
    ) -> dict[str, Any]:
        if not isinstance(query, str) or not 1 <= len(query) <= 1000:
            raise ValueError("A bounded nonempty query is required")
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("Evidence limit must be an integer from 1 to 8")
        chosen = ["source_text"] if kinds is None else kinds
        if (
            not isinstance(chosen, list)
            or not chosen
            or any(not isinstance(kind, str) or kind not in PREFIXES for kind in chosen)
            or len(set(chosen)) != len(chosen)
        ):
            raise ValueError("Use distinct source_text, software_contract or method kinds")
        for kind in chosen:
            require_evidence_kind(self.profile, kind)
        hits = []
        routes = {}
        for kind in chosen:
            if kind == "source_text":
                payload = self.knowledge.search_research_text(query, limit)
                rows = [
                    _hit(
                        kind, row["source_id"], row.get("heading") or row["source_id"],
                        row["excerpt"]["text"], row["source_url"],
                        payload.get("release_sha256"),
                    )
                    for row in payload.get("sources", [])
                ]
            elif kind == "software_contract":
                payload = self.knowledge.search_source_graph(query, limit)
                rows = [
                    _hit(
                        kind, row["id"], row["name"], row.get("summary", ""),
                        (row.get("source") or {}).get("url"), payload.get("graph_sha256"),
                    )
                    for row in payload.get("results", [])
                ]
            else:
                graph = self.method_graph()
                payload = graph.search(query, limit)
                rows = []
                for row in payload.get("results", []):
                    source_ids = row.get("source_ids", [])
                    source = graph.sources.get(source_ids[0], {}) if source_ids else {}
                    rows.append(_hit(
                        kind, row["method_id"], row["name"], row.get("purpose") or "",
                        source.get("url"), payload.get("release_sha256"),
                    ))
            routes[kind] = {
                "status": payload.get("status", "ok"),
                "route": payload.get("route"),
                "reason": payload.get("reason"),
            }
            hits.append(rows)
        # Kind-local scores are incomparable. Interleave in caller order, then cap globally.
        results = []
        for rank in range(limit):
            for rows in hits:
                if rank < len(rows):
                    results.append(rows[rank])
                if len(results) == limit:
                    break
            if len(results) == limit:
                break
        statuses = [route["status"] for route in routes.values()]
        status = "ok" if all(value == "ok" for value in statuses) else (
            "unavailable" if all(value != "ok" for value in statuses) else "partial"
        )
        return {
            "status": status, "results": results, "routes": routes,
            "default_kind": "source_text", "executable": False,
            "notice": "Search hits are candidate evidence, not source reading or permission.",
        }

    def read(
        self, identifier: str, start_char: int = 0, max_chars: int = 8000,
    ) -> dict[str, Any]:
        kind, native = split_evidence_id(identifier)
        require_evidence_kind(self.profile, kind)
        if type(start_char) is not int or start_char < 0:
            raise ValueError("Invalid source offset")
        if type(max_chars) is not int or not 100 <= max_chars <= 12000:
            raise ValueError("Source read size must be from 100 to 12000 characters")
        if kind != "source_text" and start_char:
            raise ValueError("Offsets apply only to original source_text")
        if kind == "source_text":
            payload = self.knowledge.read_research_text(native, start_char, max_chars)
            title = payload.get("heading") or native
            snippet = payload["text"]
            url = payload["source_url"]
            release = payload.get("release_sha256")
        elif kind == "software_contract":
            payload = self.knowledge.read_source_graph(native)
            title = payload["node"]["name"]
            snippet = payload["evidence"]["text"]
            url = payload["evidence"]["url"]
            graph = getattr(self.knowledge, "_source_graph", None)
            release = getattr(graph, "sha256", None)
        else:
            payload = self.method_graph().read(native)
            title = payload["method"]["name"]
            snippet = payload["method"].get("purpose") or ""
            sources = payload.get("source_evidence", [])
            url = sources[0].get("url") if sources else None
            release = payload.get("release_sha256")
        result = _hit(kind, native, title, snippet, url, release)
        result.update(
            status="ok", evidence=payload, executable=False,
            scientific_status="not_evaluated",
        )
        if kind == "source_text" and payload.get("truncated"):
            result["next_read"] = {
                "id": identifier, "start_char": payload["next_char"], "max_chars": max_chars,
            }
        if kind == "method":
            result["source_reads"] = [
                {"id": evidence_id("source_text", "METHOD_SOURCE_" + source["source_id"])}
                for source in payload.get("source_evidence", [])
            ]
        return result

