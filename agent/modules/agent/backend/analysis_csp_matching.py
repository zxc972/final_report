"""Product matching as a constraint satisfaction problem (algorithm 3).

Given a method's input slots and the products observed for the registered
subjects, find every assignment slot -> product that satisfies the method's
conditions, rank the assignments, and report slots whose domain is empty as
typed missing requirements for backward planning.

Formulation
  Types T with parent links (knowledge_analysis/product_types.json); subsumption
  t <= s holds when s is t or an ancestor of t.
  Product p = (type_p, attrs_p).  Slot s = (type_s, unary constraints phi_s).
  Domain D(s) = { p : type_p <= type_s and phi_s(attrs_p) }.
  Assignment sigma: slots -> products, injective, sigma(s) in D(s).
  Feasible when every hard n-ary constraint holds; soft constraints count as
  warnings.
  Search: backtracking, slots ordered by smallest domain first (MRV), forward
  checking with the n-ary constraints after every binding.
  Ranking (lexicographic): soft violations, distance from the preferred space,
  then a stable product-id order.

Supported constraint kinds (subset of the condition templates):
  unary  attr_in(attr, values), attr_equals(attr, value), attr_present(attr)
  n-ary  attr_equal(slots, attrs): all bound products share each attribute value
"""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

MAX_SOLUTIONS = 256


class TypeHierarchy:
    def __init__(self, types: Iterable[Mapping[str, object]]):
        self.parent = {str(t["id"]): (str(t["parent"]) if t.get("parent") else None) for t in types}

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "TypeHierarchy":
        return cls(document["types"])  # type: ignore[arg-type]

    def ancestors(self, type_id: str) -> list[str]:
        chain, seen, current = [], set(), type_id
        while current is not None:
            if current in seen:
                raise ValueError(f"Cycle in type hierarchy at {current}")
            seen.add(current)
            chain.append(current)
            current = self.parent.get(current)
        return chain

    def subsumes(self, general: str, specific: str) -> bool:
        if specific not in self.parent:
            return False
        return general in self.ancestors(specific)


def _unary_ok(attrs: Mapping[str, object], constraint: Mapping[str, object]) -> bool:
    kind, attr = constraint["kind"], str(constraint["attr"])
    value = attrs.get(attr)
    if kind == "attr_present":
        return value is not None
    if kind == "attr_equals":
        return value == constraint["value"]
    if kind == "attr_in":
        return value in set(constraint["values"])  # type: ignore[arg-type]
    raise ValueError(f"Unknown unary constraint {kind!r}")


def domains(slots: Sequence[Mapping[str, object]], products: Sequence[Mapping[str, object]],
            hierarchy: TypeHierarchy) -> dict[str, list[Mapping[str, object]]]:
    out = {}
    for slot in slots:
        out[str(slot["name"])] = [
            p for p in products
            if hierarchy.subsumes(str(slot["type"]), str(p["type"]))
            and all(_unary_ok(p.get("attrs", {}), c) for c in slot.get("unary", []))
        ]
    return out


def _nary_status(constraint: Mapping[str, object], binding: Mapping[str, Mapping[str, object]]):
    """True / False when decidable on the bound slots, None while undecided."""
    names = [str(s) for s in constraint["slots"]]
    bound = [binding[n] for n in names if n in binding]
    if len(bound) < 2:
        return None if len(bound) < len(names) else True
    for attr in constraint["attrs"]:
        values = {p.get("attrs", {}).get(str(attr)) for p in bound}
        if len(values) > 1 or None in values:
            return False
    return True if len(bound) == len(names) else None


def solve(slots: Sequence[Mapping[str, object]], products: Sequence[Mapping[str, object]],
          constraints: Sequence[Mapping[str, object]], hierarchy: TypeHierarchy,
          preferred_space: str | None = None, max_solutions: int = MAX_SOLUTIONS) -> dict:
    """Enumerate feasible assignments; report empty domains as missing requirements."""
    for c in constraints:
        if c.get("kind") != "attr_equal":
            raise ValueError(f"Unsupported n-ary constraint {c.get('kind')!r}")
    dom = domains(slots, products, hierarchy)
    missing = [{"slot": str(s["name"]), "type": str(s["type"]), "unary": list(s.get("unary", []))}
               for s in slots if not dom[str(s["name"])]]
    stats = {"nodes": 0, "pruned": 0}
    if missing:
        return {"solutions": [], "missing": missing, "domain_sizes": {k: len(v) for k, v in dom.items()},
                "stats": stats, "truncated": False}
    hard = [c for c in constraints if c.get("severity", "hard") == "hard"]
    soft = [c for c in constraints if c.get("severity", "hard") == "soft"]
    solutions: list[dict] = []
    truncated = False

    def search(binding: dict, current: dict):
        nonlocal truncated
        if len(solutions) >= max_solutions:
            truncated = True
            return
        free = [n for n in current if n not in binding]
        if not free:
            solutions.append(dict(binding))
            return
        name = min(free, key=lambda n: (len(current[n]), n))  # MRV
        for product in current[name]:
            if any(product is p for p in binding.values()):
                continue
            stats["nodes"] += 1
            binding[name] = product
            if any(_nary_status(c, binding) is False for c in hard):
                stats["pruned"] += 1
                del binding[name]
                continue
            # forward checking: shrink the other free domains
            reduced, dead = {}, False
            for other in free:
                if other == name:
                    continue
                keep = []
                for candidate in current[other]:
                    binding[other] = candidate
                    if all(_nary_status(c, binding) is not False for c in hard):
                        keep.append(candidate)
                    del binding[other]
                if not keep:
                    dead = True
                    break
                reduced[other] = keep
            if dead:
                stats["pruned"] += 1
            else:
                nxt = dict(current)
                nxt.update(reduced)
                search(binding, nxt)
            del binding[name]

    search({}, dom)

    ranked = []
    for sol in solutions:
        soft_violations = sum(1 for c in soft if _nary_status(c, sol) is False)
        off_space = 0
        if preferred_space:
            off_space = sum(1 for p in sol.values() if p.get("attrs", {}).get("space") not in (None, preferred_space))
        ranked.append({"assignment": {k: str(v["id"]) for k, v in sol.items()},
                       "soft_violations": soft_violations, "off_preferred_space": off_space})
    ranked.sort(key=lambda r: (r["soft_violations"], r["off_preferred_space"],
                               tuple(sorted(r["assignment"].items()))))
    return {"solutions": ranked, "missing": [], "domain_sizes": {k: len(v) for k, v in dom.items()},
            "stats": stats, "truncated": truncated}


def brute_force(slots, products, constraints, hierarchy) -> list[dict]:
    """Exhaustive reference used only by tests and the matching experiment."""
    import itertools
    dom = domains(slots, products, hierarchy)
    names = [str(s["name"]) for s in slots]
    hard = [c for c in constraints if c.get("severity", "hard") == "hard"]
    out = []
    for combo in itertools.product(*(dom[n] for n in names)):
        if len({id(p) for p in combo}) != len(combo):
            continue
        binding = dict(zip(names, combo))
        if all(_nary_status(c, binding) is not False for c in hard):
            out.append({k: str(v["id"]) for k, v in binding.items()})
    return out
