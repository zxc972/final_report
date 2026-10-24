"""Source independence and metered extraction packaging, with zero network calls."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def load():
    path = ROOT / "tools/knowledge/prepare_condition_test_cards_v2.py"
    spec = importlib.util.spec_from_file_location("round20_cards_v2_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_primary_and_backup_sources_are_disjoint_from_both_previous_sets():
    module = load()
    seen = module.seen_source_urls()
    methods = [*module.METHODS, *module.BACKUP_METHODS]
    assert len({m["method_id"] for m in methods}) == 9
    assert len({m["objective"] for m in methods}) == 1
    assert all(module.normal_url(module.SOURCES[sid]) not in seen for m in methods for sid in m["sources"])
    assert module.normal_url("https://surfer.nmr.mgh.harvard.edu/fswiki/LGI") in seen
    assert all("LGI" not in module.SOURCES[sid] for m in methods for sid in m["sources"])


def test_offline_extraction_uses_shared150_budget_and_unlabelled2001_ids(tmp_path, monkeypatch):
    module = load()
    module.METHODS = module.METHODS[:2]
    out = tmp_path / "cards"
    (out / "sources").mkdir(parents=True)
    module.SHARED_LEDGER = tmp_path / "shared_extraction_ledger"
    manifest = []
    for method in module.METHODS:
        sid = method["sources"][0]
        text = "Exact synthetic source quotation for " + sid
        path = out / "sources" / (sid + ".txt")
        path.write_text(text)
        manifest.append({"source_id": sid, "url": module.SOURCES[sid], "text_sha256": module.base.sha256(path)})
    module.base.save_json(out / "source_manifest.json", manifest)
    seen = []
    def config(path, **kwargs):
        assert kwargs == {"max_tokens": 8192, "thinking": "disabled", "json_output": True, "timeout": 180}
        return module.transport.Config(base_url="https://fixture.invalid/v1", api_key="fake-local-only", **kwargs)
    class Provider:
        def __init__(self, cfg, folder, max_requests):
            assert cfg.temperature == .7 and max_requests == 150 and folder == module.SHARED_LEDGER
        def complete(self, prompt):
            scope = module.transport._SCOPE.get()
            assert scope["arm"] == "independent_card_extraction" and scope["sample"] == 1
            assert "gold_template" not in prompt
            payload = json.loads(prompt.split("\nINPUT JSON:\n", 1)[1])
            source = payload["sources"][0]
            seen.append(payload["method_id"])
            card = {**module.SCHEMA, "method_id": payload["method_id"], "name": payload["name"], "software": []}
            card.update({field: [] for field in module.FIELDS})
            card["inputs"] = [{"statement": "Synthetic command scope " + payload["method_id"], "source_id": source["source_id"], "quote": source["text"], "claim_type": "direct"}]
            return json.dumps(card)
        def stats(self):
            return {"http_attempts": len(seen), "successful_requests": len(seen)}
        def close(self):
            pass
    monkeypatch.setattr(module.transport, "load_config", config)
    monkeypatch.setattr(module.transport, "Provider", Provider)
    module.extract(out, "unused-fixture-config")
    frozen = json.loads((out / "extraction_frozen.json").read_text())
    assert frozen["max_http_attempts"] == 150 and frozen["algorithm_calls"] == 0 and frozen["gold_created"] is False
    packet = json.loads((out / "claude_annotation_packet/statements_unlabelled.json").read_text())
    assert [row["id"] for row in packet["items"]] == [2001, 2002]
    assert len(seen) == 2 and all("gold_template" not in row for row in packet["items"])
