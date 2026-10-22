import pytest
from budget_policy import reserve_counts, RunLimitReached, BatchLimitReached


def test_thirty_then_next_run_is_independent():
    count, total = 0, 0
    for i in range(30):
        count, total = reserve_counts(count, total, 7)
    with pytest.raises(RunLimitReached):
        reserve_counts(count, total, 7)
    assert reserve_counts(0, total, 7) == (1, 31)


def test_batch_cap_is_separate():
    assert reserve_counts(29, 209, 7) == (30, 210)
    with pytest.raises(BatchLimitReached):
        reserve_counts(0, 210, 7)
    with pytest.raises(ValueError):
        reserve_counts(0, 0, 8)
