import importlib.util
from pathlib import Path
import pytest


def test_eight_case_guard_matches_user_authorized_plan():
    path = Path(__file__).parents[1] / "experiments/round12/budget_policy.py"
    spec = importlib.util.spec_from_file_location("round12_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for runs in range(1, 9):
        assert module.reserve_counts(0, 0, 0, 0, runs, 0) == (1, 1, 1, 1)
    for runs in (0, 9):
        with pytest.raises(ValueError):
            module.reserve_counts(0, 0, 0, 0, runs, 0)
