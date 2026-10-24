"""Observed constraint identities and unique aliases; no new observations."""
from __future__ import annotations


def qualified(method_id, constraint_id):
    if not isinstance(constraint_id, str) or not constraint_id:
        raise ValueError('Observed constraint must have an ID')
    prefix = str(method_id) + ':' if method_id else ''
    return constraint_id if not prefix or constraint_id.startswith(prefix) else prefix + constraint_id


def canonical_row(row):
    result = dict(row)
    method = row.get('method_id')
    identity = qualified(method, row['constraint_id'])
    prefix = str(method) + ':' if method else ''
    local = identity[len(prefix):] if prefix and identity.startswith(prefix) else identity
    result.update(constraint_id=identity, local_constraint_id=local)
    return result


def observed_aliases(card):
    aliases = {}
    for observed in card.get('hard_blocks', []):
        row = canonical_row(observed)
        for name in {row['constraint_id'], row['local_constraint_id']}:
            aliases.setdefault(name, set()).add(row['constraint_id'])
    return aliases


def resolve_observed(identity, card):
    choices = observed_aliases(card).get(identity, set())
    if len(choices) != 1:
        kind = 'ambiguous' if choices else 'unobserved'
        raise ValueError('Disclosure must cite observed hard-block ids (' + kind + '): ' + str(identity))
    return next(iter(choices))


def normalize_disclosure(ids, card):
    if not isinstance(ids, list) or any(not isinstance(x, str) for x in ids):
        raise ValueError('Disclosure must list observed constraint IDs')
    return list(dict.fromkeys(resolve_observed(x, card) for x in ids))


def register_observed_constraints(card, registered):
    # Unambiguous legacy local IDs remain accepted aliases, never extra facts.
    for alias, choices in observed_aliases(card).items():
        if len(choices) == 1:
            registered.update([alias, next(iter(choices))])
    return registered
