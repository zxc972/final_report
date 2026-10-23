"""Condition canonicalisation for knowledge-graph construction (algorithm 1).

Input: method cards already extracted from official documentation and method
papers (knowledge/method_extractions/*.json: statements with quotes and
source ids) and the source texts. Output: executable condition instances
(template + typed parameters + severity + sources), advisory statements, and a
human review queue.

Stages
  1. Quote verification   rho(q, D) = max over windows w of |LCS(q, w)| / |q|
                          on normalised text; keep when rho >= RHO_MIN.
  2. Template retrieval   cosine similarity between the statement and each
                          template description (bag of words, idf weighted);
                          top-k candidates.
  3. Definition           an LLM fills parameters for each candidate; K samples.
  4. Type checking        slot names exist, attributes belong to the slot type,
                          values lie in the attribute domain, numbers in range.
  5. Voting               canonical key = template + sorted parameters; support
                          v = fraction of the K samples that produced the key.
                          score = LAMBDA * cosine + (1 - LAMBDA) * v.
                          Accept when score >= TAU and score - runner-up >= DELTA.
  6. Canonical merge      identical keys within a method merge and union sources.
  Statements without a type-valid template become advisory; low-margin or
  low-support items go to the review queue.

The LLM is injected as a callable so the algorithm can be tested offline and
run on the server with the configured provider.
"""
from __future__ import annotations

from collections import Counter
import difflib
import json
import math
import re
from typing import Callable, Iterable, Mapping, Sequence

RHO_MIN = 0.9
TOP_K = 3
SAMPLES = 5
LAMBDA = 0.3
TAU = 0.6
DELTA = 0.2

TEMPLATES: dict[str, dict] = {
    "product_present": {"desc": "required input file product must exist be present available produced processed output surface volume annotation label stats",
                        "params": {"slot": "slot", "type": "type"}},
    "attr_equal": {"desc": "same subject hemisphere mesh space resolution match consistent identical correspond vertices number equal between files",
                   "params": {"slots": "slots", "attrs": "attrs"}},
    "attr_in": {"desc": "must be in space species template resolution format allowed values one of native fsaverage MNI isotropic voxel size",
                "params": {"slot": "slot", "attr": "attr", "values": "values"}},
    "label_policy": {"desc": "exclude unknown unassigned medial wall labels annotation colour table label names parcellation regions",
                     "params": {"slot": "slot", "exclude": "values"}},
    "cardinality": {"desc": "at least minimum number subjects group size sample per group participants scans",
                    "params": {"object": "text", "minimum": "int"}},
    "design_variable": {"desc": "design matrix covariate age sex group variable column participants table contrast",
                        "params": {"columns": "values"}},
    "software": {"desc": "software installed required toolbox matlab freesurfer fsl ants command available path version licence environment",
                 "params": {"commands": "values"}},
    "provenance": {"desc": "processed with stream recon-all completed run before pipeline step previously done log finished",
                   "params": {"step": "text"}},
    "scale_check": {"desc": "scale rescale units millimetre physical size conversion factor voxel dimensions brain size",
                    "params": {"metric": "text"}},
    "plausibility": {"desc": "typical range expected values normal thickness area volume outlier quality check implausible",
                     "params": {"metric": "text"}},
    "asymmetry_flip": {"desc": "left right hemisphere asymmetry flip symmetric template lateralization bias",
                       "params": {}},
    "advisory": {"desc": "recommendation note caution interpret consider may should visually inspect manually",
                 "params": {"text": "text"}},
}

ATTRIBUTE_DOMAINS = {
    "hemisphere": {"lh", "rh"},
    "species": {"human", "macaque", "marmoset", "chimpanzee"},
    "space": {"native", "native_1mm", "fsaverage", "fsLR_32k", "fsLR_164k", "MNI152", "NMT_v2", "Yerkes19"},
}

_TOKEN = re.compile(r"[a-z0-9]+")


def normalise(text: str) -> str:
    text = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    return " ".join(_TOKEN.findall(text))


def quote_support(quote: str, source: str) -> float:
    """rho(q, D): best matched-character fraction of the quote over windows of the source."""
    q, d = normalise(quote), normalise(source)
    if not q:
        return 0.0
    if q in d:
        return 1.0
    words, n = d.split(" "), len(q.split(" "))
    best = 0.0
    step = max(1, n // 2)
    for start in range(0, max(1, len(words) - n + 1), step):
        window = " ".join(words[start:start + n + max(2, n // 5)])
        matcher = difflib.SequenceMatcher(None, q, window, autojunk=False)
        size = sum(block.size for block in matcher.get_matching_blocks())
        best = max(best, size / len(q))
        if best >= 0.999:
            break
    return best


class Retriever:
    def __init__(self, templates: Mapping[str, Mapping[str, object]] = TEMPLATES):
        self.names = list(templates)
        docs = [normalise(f"{n.replace('_', ' ')} {templates[n]['desc']}").split() for n in self.names]
        df = Counter(t for doc in docs for t in set(doc))
        self.idf = {t: math.log((1 + len(docs)) / (1 + c)) + 1.0 for t, c in df.items()}
        self.vectors = [self._vec(doc) for doc in docs]

    def _vec(self, tokens: Sequence[str]) -> dict:
        counts = Counter(tokens)
        vec = {t: c * self.idf.get(t, 0.0) for t, c in counts.items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def rank(self, statement: str, k: int = TOP_K) -> list[tuple[str, float]]:
        v = self._vec(normalise(statement).split())
        scores = [(name, sum(v.get(t, 0.0) * w for t, w in vec.items()))
                  for name, vec in zip(self.names, self.vectors)]
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores[:k]


def type_check(template: str, params: Mapping[str, object], slots: Mapping[str, Sequence[str]]) -> list[str]:
    """Return a list of problems (empty = valid). slots: slot name -> allowed attribute names."""
    spec = TEMPLATES.get(template)
    if spec is None:
        return [f"unknown template {template}"]
    problems = []
    for name, kind in spec["params"].items():
        if name not in params:
            problems.append(f"missing parameter {name}")
            continue
        value = params[name]
        if kind == "slot" and value not in slots:
            problems.append(f"unknown slot {value}")
        elif kind == "slots" and (not isinstance(value, list) or len(value) < 2 or any(s not in slots for s in value)):
            problems.append("slots must list at least two known slots")
        elif kind == "attrs" and (not isinstance(value, list) or not value):
            problems.append("attrs must be a non-empty list")
        elif kind == "values" and (not isinstance(value, list) or not value):
            problems.append(f"{name} must be a non-empty list")
        elif kind == "int" and (not isinstance(value, int) or value < 1):
            problems.append(f"{name} must be a positive integer")
    if "attr" in params:
        slot = params.get("slot")
        if slot in slots and params["attr"] not in slots[slot]:
            problems.append(f"attribute {params['attr']} not defined for slot {slot}")
        domain = ATTRIBUTE_DOMAINS.get(str(params["attr"]))
        if domain and isinstance(params.get("values"), list) and not set(params["values"]) <= domain:
            problems.append(f"values outside the {params['attr']} domain")
    if template == "attr_equal" and isinstance(params.get("slots"), list):
        for attr in params.get("attrs") or []:
            for slot in params["slots"]:
                if slot in slots and attr not in slots[slot]:
                    problems.append(f"attribute {attr} not defined for slot {slot}")
    return problems


def canonical_key(template: str, params: Mapping[str, object]) -> str:
    def norm(v):
        if isinstance(v, list):
            return sorted(norm(x) for x in v)
        if isinstance(v, str):
            return v.strip()
        return v
    return template + ":" + json.dumps({k: norm(v) for k, v in sorted(params.items())}, sort_keys=True)


def build_prompt(statement: str, quote: str, candidates: Sequence[str],
                 slots: Mapping[str, Sequence[str]]) -> str:
    specs = {n: TEMPLATES[n]["params"] for n in candidates}
    return (
        "Map one method condition to an executable template.\n"
        f"Statement: {statement}\nQuote: {quote}\n"
        f"Method input slots and their attributes: {json.dumps({k: list(v) for k, v in slots.items()})}\n"
        f"Candidate templates and parameter kinds: {json.dumps(specs)}\n"
        'Answer with JSON only: {"template": <name or "none">, "parameters": {...}}. '
        "Use only the listed slots and attributes. Answer none if no template fits."
    )


def parse_answer(text: str) -> tuple[str, dict] | None:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    template = str(data.get("template", "none"))
    if template == "none":
        return None
    params = data.get("parameters") or {}
    return (template, params) if isinstance(params, dict) else None


def canonicalise_statement(statement: Mapping[str, object], source_text: str,
                           slots: Mapping[str, Sequence[str]], llm: Callable[[str], str],
                           retriever: Retriever | None = None, samples: int = SAMPLES) -> dict:
    retriever = retriever or Retriever()
    rho = quote_support(str(statement.get("quote", "")), source_text)
    record = {"statement": statement.get("statement"), "quote_support": rho,
              "source_id": statement.get("source_id")}
    if rho < RHO_MIN:
        return {**record, "decision": "rejected_quote"}
    ranked = retriever.rank(str(statement.get("statement", "")) + " " + str(statement.get("quote", "")))
    cosine = dict(ranked)
    candidates = [n for n, _ in ranked if n != "advisory"]
    prompt = build_prompt(str(statement["statement"]), str(statement.get("quote", "")), candidates, slots)
    votes: Counter = Counter()
    keyed: dict[str, tuple[str, dict]] = {}
    invalid = Counter()
    for _ in range(samples):
        answer = parse_answer(llm(prompt))
        if answer is None:
            continue
        template, params = answer
        problems = type_check(template, params, slots)
        if problems:
            invalid[template] += 1
            continue
        key = canonical_key(template, params)
        votes[key] += 1
        keyed[key] = (template, params)
    scored = sorted(((LAMBDA * cosine.get(keyed[k][0], 0.0) + (1 - LAMBDA) * c / samples, k)
                     for k, c in votes.items()), reverse=True)
    if not scored:
        return {**record, "decision": "advisory", "reason": "no type-valid template",
                "invalid_attempts": dict(invalid), "candidates": ranked}
    best_score, best_key = scored[0]
    margin = best_score - (scored[1][0] if len(scored) > 1 else 0.0)
    template, params = keyed[best_key]
    result = {**record, "template": template, "parameters": params, "key": best_key,
              "score": best_score, "margin": margin, "support": votes[best_key] / samples,
              "candidates": ranked}
    if best_score >= TAU and margin >= DELTA:
        return {**result, "decision": "accepted"}
    return {**result, "decision": "review"}


def merge(results: Iterable[Mapping[str, object]], method_id: str) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in results:
        if r.get("decision") != "accepted":
            continue
        entry = merged.setdefault(str(r["key"]), {"method_id": method_id, "template": r["template"],
                                                  "parameters": r["parameters"], "sources": [], "statements": []})
        entry["sources"].append({"source_id": r.get("source_id"), "quote_support": r.get("quote_support")})
        entry["statements"].append(r.get("statement"))
    return list(merged.values())


def evaluate(predicted: Iterable[Mapping[str, object]], gold: Iterable[Mapping[str, object]]) -> dict:
    """Precision / recall / F1 on canonical keys and on template labels per (method, statement)."""
    pk = {(p["method_id"], canonical_key(p["template"], p["parameters"])) for p in predicted}
    gk = {(g["method_id"], canonical_key(g["template"], g["parameters"])) for g in gold}
    tp = len(pk & gk)
    precision = tp / len(pk) if pk else 0.0
    recall = tp / len(gk) if gk else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "predicted": len(pk), "gold": len(gk), "precision": precision, "recall": recall, "f1": f1}
