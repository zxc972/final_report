"""The new cohort guard charges up to four HTTP attempts per logical call."""
import importlib.util
from pathlib import Path
import pytest

path = Path(__file__).parents[1] / "experiments/round13/budget_policy.py"
spec = importlib.util.spec_from_file_location("round13_guard", path)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def test_eight_trials_and_four_rate_limit_attempts():
    counts = (0, 0, 0, 0)
    for attempt in range(4):
        counts = guard.reserve_counts(*counts, 8, attempt)
    assert counts == (1, 1, 4, 4)
    with pytest.raises(guard.RunLimitReached):
        guard.reserve_counts(*counts, 8, 4)
    with pytest.raises(guard.RunLimitReached):
        guard.reserve_counts(30, 30, 30, 30, 8, 0)


@pytest.mark.parametrize("planned", [0, 9])
def test_invalid_batch_size_is_rejected(planned):
    with pytest.raises(ValueError):
        guard.reserve_counts(0, 0, 0, 0, planned, 0)
