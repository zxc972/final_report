from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import pytest

path = Path(__file__).resolve().parents[1] / 'experiments/round11/budget_policy.py'
spec = spec_from_file_location('r11_trial_budget', path)
policy = module_from_spec(spec)
spec.loader.exec_module(policy)

def test_retry_does_not_consume_another_logical_call():
    assert policy.reserve_counts(30, 30, 30, 30, 6, 1) == (30, 30, 31, 31)
    assert policy.reserve_counts(30, 30, 31, 31, 6, 2) == (30, 30, 32, 32)
    with pytest.raises(policy.RunLimitReached):
        policy.reserve_counts(30, 30, 32, 32, 6, 3)

def test_new_run_has_fresh_allowance():
    assert policy.reserve_counts(0, 30, 0, 32, 6, 0) == (1, 31, 1, 33)
    with pytest.raises(policy.RunLimitReached):
        policy.reserve_counts(30, 30, 30, 30, 6, 0)

def test_cohort_limit_is_separate_and_cannot_reset():
    with pytest.raises(policy.BatchLimitReached):
        policy.reserve_counts(0, 180, 0, 180, 6, 0)
    with pytest.raises(ValueError):
        policy.reserve_counts(0, 0, 0, 0, 7, 0)

def test_retry_http_ceiling_remains_bounded():
    with pytest.raises(policy.RunLimitReached):
        policy.reserve_counts(30, 30, 90, 90, 6, 1)
    with pytest.raises(policy.BatchLimitReached):
        policy.reserve_counts(1, 180, 1, 540, 6, 1)

def test_router_native_budget_before_context_activation():
    from types import SimpleNamespace
    budget = SimpleNamespace(records=[{'logical_id': 'router-reservation'}])
    assert policy.active_budget({'chat_budget': budget}, None) is budget
    assert policy.active_budget({}, SimpleNamespace(budget=budget)) is budget

def test_unbound_request_is_still_rejected():
    assert policy.active_budget({}, None) is None
