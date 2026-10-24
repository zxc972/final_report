"""Round 16: condition canonicalisation (algorithm 1) with a scripted LLM."""
import importlib
import importlib.util
from pathlib import Path
import sys
import types

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _load():
    try:
        from test_analysis_agent import agent
        return importlib.import_module(agent.__package__ + ".analysis_condition_canonicalizer")
    except Exception:
        spec = importlib.util.spec_from_file_location("_r16_canon", BACKEND / "analysis_condition_canonicalizer.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


c = _load()
SOURCE = ("Usage of the -localGI feature assumes that a subject has already been processed with recon-all. "
          "MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.")
SLOTS = {"S_pial": ["subject", "hemisphere", "mesh", "space"], "S_thk": ["subject", "hemisphere", "mesh"]}


def scripted(*answers):
    seq = list(answers)
    def llm(_prompt):
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return llm


def test_quote_support_exact_fuzzy_and_absent():
    assert c.quote_support("MATLAB is required to use the -localGI feature.", SOURCE) == 1.0
    assert c.quote_support("MATLAB is required to use the localGI features", SOURCE) >= 0.9
    assert c.quote_support("Thickness must be smoothed with a 10 mm kernel.", SOURCE) < 0.9


def test_retrieval_ranks_software_for_matlab_statement():
    ranked = c.Retriever().rank("MATLAB and its Image Processing Toolbox must be installed")
    assert ranked[0][0] == "software"


def test_accepts_consistent_type_valid_answer_and_merges_sources():
    st = {"statement": "MATLAB and its Image Processing Toolbox must be installed.",
          "quote": "MATLAB is required to use the -localGI feature.", "source_id": "fs_lgi"}
    llm = scripted('{"template": "software", "parameters": {"commands": ["matlab"]}}')
    r = c.canonicalise_statement(st, SOURCE, SLOTS, llm)
    assert r["decision"] == "accepted" and r["support"] == 1.0 and r["parameters"] == {"commands": ["matlab"]}
    merged = c.merge([r, dict(r, source_id="other")], "method:lgi")
    assert len(merged) == 1 and len(merged[0]["sources"]) == 2


def test_rejects_unverified_quote():
    st = {"statement": "Smooth thickness", "quote": "Thickness must be smoothed with a 10 mm kernel.", "source_id": "x"}
    assert c.canonicalise_statement(st, SOURCE, SLOTS, scripted("{}"))["decision"] == "rejected_quote"


def test_type_errors_become_advisory():
    st = {"statement": "Pial surfaces must be in MNI space.", "quote": "MATLAB is required to use the -localGI feature.",
          "source_id": "s"}
    bad = '{"template": "attr_in", "parameters": {"slot": "S_missing", "attr": "space", "values": ["MNI152"]}}'
    r = c.canonicalise_statement(st, SOURCE, SLOTS, scripted(bad))
    assert r["decision"] == "advisory" and r["invalid_attempts"] == {"attr_in": 5}


def test_split_votes_go_to_review():
    st = {"statement": "Pial and thickness files must share the subject and mesh.",
          "quote": "MATLAB is required to use the -localGI feature.", "source_id": "s"}
    a = '{"template": "attr_equal", "parameters": {"slots": ["S_pial", "S_thk"], "attrs": ["subject", "mesh"]}}'
    b = '{"template": "attr_equal", "parameters": {"slots": ["S_pial", "S_thk"], "attrs": ["subject"]}}'
    r = c.canonicalise_statement(st, SOURCE, SLOTS, scripted(a, b, a, b, b))
    assert r["decision"] == "review" and abs(r["support"] - 0.6) < 1e-9


def test_canonical_key_ignores_order_and_evaluate_scores():
    k1 = c.canonical_key("attr_equal", {"slots": ["b", "a"], "attrs": ["mesh", "subject"]})
    k2 = c.canonical_key("attr_equal", {"attrs": ["subject", "mesh"], "slots": ["a", "b"]})
    assert k1 == k2
    pred = [{"method_id": "m", "template": "software", "parameters": {"commands": ["matlab"]}},
            {"method_id": "m", "template": "cardinality", "parameters": {"object": "subjects", "minimum": 2}}]
    gold = [{"method_id": "m", "template": "software", "parameters": {"commands": ["matlab"]}},
            {"method_id": "m", "template": "provenance", "parameters": {"step": "recon-all"}}]
    s = c.evaluate(pred, gold)
    assert s["tp"] == 1 and s["precision"] == 0.5 and s["recall"] == 0.5


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
