"""Unified typed SQLite storage for knowledge, observed instances and workflows."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

from .analysis_control_store import canonical, digest


class UnifiedKnowledge:
    def __init__(self, path):
        self.path = Path(path).absolute()
        if self.path.is_symlink() or any(
            parent.is_symlink() for parent in self.path.parents
        ):
            raise ValueError("Unified knowledge path must not traverse symlinks")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._transaction = None
        self._guard = threading.RLock()
        with self.connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_documents (
                    name TEXT PRIMARY KEY, path TEXT NOT NULL,
                    sha256 TEXT NOT NULL, body TEXT NOT NULL CHECK(json_valid(body))
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY, layer TEXT NOT NULL,
                    kind TEXT NOT NULL, label TEXT NOT NULL,
                    properties TEXT NOT NULL CHECK(json_valid(properties))
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL REFERENCES nodes(id),
                    target TEXT NOT NULL REFERENCES nodes(id),
                    relation TEXT NOT NULL,
                    properties TEXT NOT NULL CHECK(json_valid(properties))
                );
                CREATE INDEX IF NOT EXISTS edge_source_relation ON edges(source, relation);
                CREATE INDEX IF NOT EXISTS edge_target_relation ON edges(target, relation);
                CREATE INDEX IF NOT EXISTS node_layer_kind ON nodes(layer, kind);
                CREATE TABLE IF NOT EXISTS quarantined_edges (
                    id TEXT PRIMARY KEY, source_package TEXT NOT NULL,
                    reason TEXT NOT NULL, record TEXT NOT NULL CHECK(json_valid(record))
                );
            """
            )
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?,?)",
                ("schema", "primatex.unified_graph.v1"),
            )

    @contextmanager
    def connection(self):
        # A single repository can be reached by parallel tool calls. Serialize
        # access so the active transaction never escapes into another thread.
        with self._guard:
            if self._transaction is not None:
                yield self._transaction
                return
            db = sqlite3.connect(str(self.path), timeout=30)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            previous = self._transaction
            self._transaction = db
            try:
                yield self
            finally:
                self._transaction = previous

    def node(self, identifier, layer, kind, label, properties):
        with self.connection() as db:
            prior = db.execute(
                "SELECT properties FROM nodes WHERE id=?", (identifier,)
            ).fetchone()
            merged = json.loads(prior["properties"]) if prior else {}
            merged.update(properties)
            db.execute(
                "INSERT INTO nodes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "layer=excluded.layer,kind=excluded.kind,label=excluded.label,properties=excluded.properties",
                (identifier, layer, kind, label, canonical(merged).decode()),
            )

    def edge(
        self, source, target, relation, properties=None, source_package="generated"
    ):
        properties = properties or {}
        identifier = "edge:" + digest([source, relation, target, properties])
        with self.connection() as db:
            found = db.execute(
                "SELECT count(*) FROM nodes WHERE id IN (?,?)", (source, target)
            ).fetchone()[0]
            expected = 1 if source == target else 2
            if found != expected:
                db.execute(
                    "INSERT OR REPLACE INTO quarantined_edges VALUES (?,?,?,?)",
                    (
                        identifier,
                        source_package,
                        "Endpoint is undeclared; relation not activated",
                        canonical(
                            {
                                "source": source,
                                "target": target,
                                "relation": relation,
                                "properties": properties,
                            }
                        ).decode(),
                    ),
                )
                return False
            db.execute(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?)",
                (identifier, source, target, relation, canonical(properties).decode()),
            )
        return True

    def document(self, name, path=None, expected_sha256=None):
        if path is not None:
            path = Path(path)
            raw = path.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if path.is_symlink() or (expected_sha256 and actual != expected_sha256):
                raise ValueError("Unified import digest mismatch: " + name)
            body = json.loads(raw)
            with self.connection() as db:
                db.execute(
                    "INSERT OR REPLACE INTO source_documents VALUES (?,?,?,?)",
                    (name, str(path), actual, raw.decode("utf-8-sig")),
                )
            return body, actual
        with self.connection() as db:
            row = db.execute(
                "SELECT body,sha256 FROM source_documents WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            raise ValueError("Unified knowledge document not imported: " + name)
        return json.loads(row["body"]), row["sha256"]

    def get_node(self, identifier):
        with self.connection() as db:
            row = db.execute("SELECT * FROM nodes WHERE id=?", (identifier,)).fetchone()
        return (
            {**dict(row), "properties": json.loads(row["properties"])} if row else None
        )

    def find_nodes(self, *, layer=None, kind=None):
        terms, parameters = [], []
        for column, value in (("layer", layer), ("kind", kind)):
            if value is not None:
                terms.append(column + "=?")
                parameters.append(value)
        query = (
            "SELECT * FROM nodes"
            + (" WHERE " + " AND ".join(terms) if terms else "")
            + " ORDER BY id"
        )
        with self.connection() as db:
            rows = db.execute(query, parameters).fetchall()
        return [
            {**dict(row), "properties": json.loads(row["properties"])} for row in rows
        ]

    def is_subtype(self, child, parent):
        seen = set()
        while child and child not in seen:
            if child == parent:
                return True
            seen.add(child)
            node = self.get_node(child)
            child = node["properties"].get("parent") if node else None
        return False

    def import_graph(self, name, graph):
        for node in graph.get("nodes", []):
            self.node(
                node["id"],
                "knowledge",
                node.get("type", "Entity"),
                node.get("name", node["id"]),
                {name + "_node": node},
            )
        for method in graph.get("methods", []):
            self.node(
                method["id"],
                "knowledge",
                "Method",
                method["name"],
                {"method_card": method},
            )
        for source in graph.get("sources", []):
            self.node(
                source["id"],
                "knowledge",
                "Source",
                source.get("url", source["id"]),
                {"source_record": source},
            )
        for edge in graph.get("edges", []):
            self.edge(
                edge["source"],
                edge["target"],
                edge.get("type", edge.get("relation", "relatedTo")),
                edge,
                name,
            )

    def import_knowledge(self, knowledge_root, release_root):
        with self.transaction():
            return self._import_knowledge(knowledge_root, release_root)

    def _import_knowledge(self, knowledge_root, release_root):
        knowledge_root = Path(knowledge_root)
        release_root = Path(release_root) if release_root is not None else None
        # A shared persistent database must not accumulate stale edges after a
        # source-version change. Select a new database for a new release.
        with self.connection() as db:
            previous_documents = {
                row["name"]: row["sha256"]
                for row in db.execute("SELECT name,sha256 FROM source_documents")
            }
        for name, previous_digest in previous_documents.items():
            root = (
                release_root
                if name in {"method_graph", "domain_graph"}
                else knowledge_root
            )
            if root is None:
                continue
            source_path = root / (name + ".json")
            if (
                source_path.is_file()
                and hashlib.sha256(source_path.read_bytes()).hexdigest()
                != previous_digest
            ):
                raise ValueError(
                    "Unified source version changed: "
                    + name
                    + "; select a new database instead of retaining stale edges"
                )
        names = (
            "method_requirements",
            "pipeline_dependencies",
            "lobar_mapping",
            "constraint_probes",
            "product_types",
            "condition_templates",
            "workflow_steps",
        )
        optional = tuple(name for name in ("cross_species_rules", "species_reference_values", "conclusion_rules", "method_graph_overlay_v15")
                         if (knowledge_root / (name + ".json")).is_file())
        names += optional
        docs = {}
        for name in names:
            path = knowledge_root / (name + ".json")
            expected = path.with_suffix(".sha256").read_text().split()[0]
            docs[name], _ = self.document(name, path, expected)
        if release_root is not None:
            config = json.loads((release_root / "config.json").read_bytes())
            for name in ("method_graph", "domain_graph"):
                filename = name + ".json"
                expected = config.get(name + "_sha256") or config.get(
                    "snapshot_files", {}
                ).get(filename)
                if not expected:
                    raise ValueError("Missing frozen release digest for " + filename)
                graph, _ = self.document(name, release_root / filename, expected)
                self.import_graph(name, graph)
        if "method_graph_overlay_v15" in docs:
            self.import_graph("method_graph_overlay_v15", docs["method_graph_overlay_v15"])
        for row in docs["product_types"]["types"]:
            self.node(row["id"], "knowledge", "ProductType", row["id"], row)
        for row in docs["product_types"]["types"]:
            if row["parent"]:
                self.edge(
                    row["id"],
                    row["parent"],
                    "subClassOf",
                    {"source": docs["product_types"]["source"]},
                )
        type_map = {
            "surface_metric": "type:SurfaceMetric",
            "annotation": "type:Annotation",
            "cortex_label": "type:Label.Cortex",
            "surface": "type:Surface",
            "pial_surface": "type:Surface.Pial",
            "white_surface": "type:Surface.White",
            "registration_surface": "type:Surface.SphereReg",
            "volume": "type:Volume",
            "t1_volume": "type:Volume.T1",
            "t2_volume": "type:Volume.T2",
            "brainmask": "type:Volume.BrainMask",
            "subject_table": "type:SubjectTable",
            "aseg_stats": "type:StatsTable.AsegStats",
            "cortical_parc_stats": "type:StatsTable.CorticalParcStats",
            "aseg_presurf": "type:Volume.Aseg",
            "design_matrix": "type:StatsTable.DesignMatrix",
            "contrast": "type:StatsTable.ContrastMatrix",
        }
        for ordinal, method in enumerate(docs["method_requirements"]["methods"]):
            identifier = method["method_id"]
            self.node(
                identifier,
                "knowledge",
                "Method",
                identifier,
                {"requirements_spec": method, "requirements_ordinal": ordinal},
            )
            for index, product in enumerate(method.get("required_products", [])):
                slot = identifier + ":slot:" + str(index)
                self.node(
                    slot,
                    "knowledge",
                    "Slot",
                    product,
                    {"product_key": product, "source": method.get("source", [])},
                )
                self.edge(identifier, slot, "hasSlot")
                self.edge(
                    slot,
                    type_map.get(product, "type:Product"),
                    "ofType",
                    {
                        "unresolved_product_key": (
                            product if product not in type_map else None
                        )
                    },
                )
        self._import_lobes(docs["lobar_mapping"])
        self._import_conditions(docs["condition_templates"])
        self._import_workflows(docs["workflow_steps"])
        for name, key, kind in (("cross_species_rules", "templates", "ConditionTemplate"),
                                ("species_reference_values", "references", "ReferenceValue"),
                                ("conclusion_rules", "rules", "ConclusionRule")):
            for row in docs.get(name, {}).get(key, []):
                self.node(row["id"], "knowledge", kind, row["id"], row)
                sources = row.get("source", [])
                sources = sources if isinstance(sources, list) else [sources]
                for source in sources:
                    source_id = "policy_source:" + digest(source)[:24]
                    self.node(source_id, "knowledge", "Source", source.get("url", source.get("document", source_id)), source)
                    self.edge(row["id"], source_id, "supportedBy")

        for method in docs["method_requirements"]["methods"]:
            for measure in method.get("measures", []):
                key = "measure:" + measure
                self.node(
                    key,
                    "knowledge",
                    "Measure",
                    measure,
                    {"source": method.get("source", [])},
                )
                self.edge(method["method_id"], key, "computes")
        for spec in docs["constraint_probes"]["constraints"]:
            group = docs["condition_templates"]["legacy_probe_groups"][
                spec["probe"]["checker"]
            ]
            for condition in group.get("root", []) + group.get("each_annotation", []):
                for method in docs["method_requirements"]["methods"]:
                    # Scope/category applicability remains explicit; linking is
                    # not a claim every condition runs for every task.
                    self.edge(
                        method["method_id"],
                        condition["id"],
                        "hasCondition",
                        {"applies_to": spec["applies_to"]},
                    )
        with self.connection() as db:
            manifest = dict(
                db.execute(
                    "SELECT name,sha256 FROM source_documents ORDER BY name"
                ).fetchall()
            )
            db.execute(
                "INSERT OR REPLACE INTO metadata VALUES (?,?)",
                ("knowledge_sha256", digest(manifest)),
            )
        return self.stats()

    def _import_lobes(self, mapping):
        for row in mapping["records"]:
            atlas = row["atlas"]
            region = row["region"]
            region_id = "region:human:" + region
            self.node(region_id, "knowledge", "Region", region, {"species": "human"})
            for label in row["labels"]:
                label_id = "atlaslabel:" + atlas + ":" + label
                self.node(
                    label_id,
                    "knowledge",
                    "AtlasLabel",
                    label,
                    {"atlas": atlas, "species": "human", "mapping_record": row},
                )
                self.edge(label_id, region_id, "partOf", {"source": row})

    def _import_conditions(self, mapping):
        for name, group in mapping["legacy_probe_groups"].items():
            for row in group.get("root", []) + group.get("each_annotation", []):
                self._condition_sources(row)
                self.node(
                    row["id"],
                    "knowledge",
                    "Condition",
                    row["id"],
                    {
                        "template_instance": row,
                        "legacy_probe_group": name,
                        "evaluation_scope": group["scope"],
                    },
                )
        for row in mapping["extra_method_conditions"]:
            self.node(
                row["id"],
                "knowledge",
                "Condition",
                row["id"],
                {"template_instance": row},
            )
            self.edge(row["method_id"], row["id"], "hasCondition")
            self._condition_sources(row)
        for group in mapping["legacy_probe_groups"].values():
            for row in group.get("root", []) + group.get("each_annotation", []):
                self._condition_sources(row)

    def _condition_sources(self, row):
        for source in row.get("source", []):
            key = "source:condition:" + digest(source)
            self.node(
                key,
                "knowledge",
                "Source",
                source.get("url", source.get("method_fact_id", "source pointer")),
                {
                    "source_record": source,
                    "trust": "Source-bound candidate, not expert approval",
                },
            )
            if self.get_node(row["id"]) is not None:
                self.edge(row["id"], key, "evidencedBy")
            fact = source.get("method_fact_id")
            if fact and self.get_node(fact):
                self.edge(key, fact, "refersToFact")

    def _import_workflows(self, mapping):
        for step in mapping["steps"]:
            identifier = "step:" + step["id"]
            self.node(identifier, "workflow", "StepType", step["id"], step)
            for index, slot in enumerate(step.get("inputs", [])):
                self.edge(
                    identifier,
                    slot["type"],
                    "needs",
                    {
                        "slot": index,
                        "attributes": slot.get("attributes", {}),
                        "optional": slot.get("optional", False),
                    },
                )
            for index, output in enumerate(step.get("outputs", [])):
                self.edge(
                    identifier,
                    output["type"],
                    "produces",
                    {
                        "output": index,
                        "attribute_rules": output.get("attribute_rules", {}),
                    },
                )
            for command in step.get("software", []):
                software_id = "software:" + command
                self.node(
                    software_id, "workflow", "Software", command, {"command": command}
                )
                self.edge(identifier, software_id, "requiresSoftware")

    def stats(self):
        with self.connection() as db:
            return {
                "nodes": db.execute("SELECT count(*) FROM nodes").fetchone()[0],
                "edges": db.execute("SELECT count(*) FROM edges").fetchone()[0],
                "quarantined_edges": db.execute(
                    "SELECT count(*) FROM quarantined_edges"
                ).fetchone()[0],
                "nodes_by_layer": {
                    row["layer"]: row["n"]
                    for row in db.execute(
                        "SELECT layer,count(*) AS n FROM nodes GROUP BY layer"
                    )
                },
                "source_documents": db.execute(
                    "SELECT count(*) FROM source_documents"
                ).fetchone()[0],
            }

    def integrity(self):
        with self.connection() as db:
            return {
                "sqlite": db.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_errors": [
                    tuple(row) for row in db.execute("PRAGMA foreign_key_check")
                ],
            }

    def knowledge_digest(self):
        with self.connection() as db:
            row = db.execute(
                "SELECT value FROM metadata WHERE key=?", ("knowledge_sha256",)
            ).fetchone()
        return row["value"] if row else None
