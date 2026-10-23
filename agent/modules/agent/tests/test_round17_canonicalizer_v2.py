"""Round 17: canonicaliser v2 (all templates offered, advisory voting, vocabularies)."""
import importlib
import importlib.util
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _load():
    try:
        from test_analysis_agent import agent
        return importlib.import_module(agent.__package__ + ".analysis_condition_canonicalizer")
    except Exception:
        spec = importlib.util.spec_from_file_location("_r17_canon", BACKEND / "analysis_condition_canonicalizer.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


c = _load()
SOURCE = "MATLAB is required to use the -localGI feature. usage assumes that a subject has already been processed with recon-all."
SLOTS = {"T1": ["subject", "species", "space"], "pial": ["subject", "hemisphere", "mesh"]}
VOCAB = {"types": ["type:Volume.T1", "type:Surface.Pial"], "steps": ["recon-all", "fastsurfer"]}
ST = {"statement": "s", "quote": "MATLAB is required to use the -localGI feature.", "source_id": "x"}


def seq(*answers):
    items = list(answers)
    return lambda _p: items.pop(0) if len(items) > 1 else items[0]


def test_software_names_normalise_to_one_key():
    llm = seq('{"template":"software","parameters":{"commands":["SPM12 or newer","MATLAB R2020a or newer"]}}',
              '{"template":"software","parameters":{"commands":["matlab","spm12"]}}',
              '{"template":"software","parameters":{"commands":["MATLAB","SPM12"]}}')
    r = c.canonicalise_statement_v2(ST, SOURCE, SLOTS, llm, VOCAB, samples=3)
    assert r["decision"] == "accepted" and r["parameters"] == {"commands": ["matlab", "spm12"]} and r["support"] == 1.0


def test_advisory_wins_vote():
    llm = seq('{"template":"advisory"}', '{"template":"plausibility","parameters":{"metric":"x"}}',
              '{"template":"advisory","parameters":{}}', '{"template":"none"}', '{"template":"advisory"}')
    r = c.canonicalise_statement_v2(ST, SOURCE, SLOTS, llm, VOCAB)
    assert r["decision"] == "advisory" and r["support"] == 0.8


def test_type_vocabulary_and_step_mapping():
    bad = '{"template":"product_present","parameters":{"slot":"pial","type":"mesh"}}'
    r = c.canonicalise_statement_v2(ST, SOURCE, SLOTS, seq(bad), VOCAB, samples=2)
    assert r["decision"] == "review" and r["invalid_attempts"] == {"product_present": 2}
    prov = '{"template":"provenance","parameters":{"step":"full recon-all stream"}}'
    r = c.canonicalise_statement_v2(ST, SOURCE, SLOTS, seq(prov), VOCAB, samples=2)
    assert r["decision"] == "accepted" and r["parameters"] == {"step": "recon-all"}


def test_split_vote_goes_to_review():
    a = '{"template":"advisory"}'
    b = '{"template":"provenance","parameters":{"step":"recon-all"}}'
    r = c.canonicalise_statement_v2(ST, SOURCE, SLOTS, seq(a, b, a, b, "garbage"), VOCAB)
    assert r["decision"] == "review" and r["answered"] == 4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
