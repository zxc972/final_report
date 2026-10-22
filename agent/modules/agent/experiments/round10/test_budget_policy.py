import pytest
from budget_policy import reserve_counts, RunLimitReached, BatchLimitReached


def test_independent_thirty_request_budgets():
    assert reserve_counts(29,29,6)==(30,30)
    with pytest.raises(RunLimitReached):
        reserve_counts(30,30,6)
    assert reserve_counts(0,30,6)==(1,31)


def test_batch_ceiling_is_six_times_thirty():
    assert reserve_counts(29,179,6)==(30,180)
    with pytest.raises(BatchLimitReached):
        reserve_counts(0,180,6)
    with pytest.raises(ValueError):
        reserve_counts(0,0,7)
