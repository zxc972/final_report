"""429 uses a separate, metered retry policy and batch pause decision."""
import importlib
import httpx
import pytest
from test_round11_transport import session
from test_analysis_provider_compat import success

transport = importlib.import_module("modules.agent.backend.analysis_transport")
provider = importlib.import_module("modules.agent.backend.analysis_provider")
classification = importlib.import_module("modules.agent.backend.analysis_failure_classification")


@pytest.mark.parametrize("retry_after,expected", [(None, [10, 30, 60]), ("2", [2, 2, 2])])
def test_rate_limit_four_http_one_logical(tmp_path, monkeypatch, retry_after, expected):
    delays, calls = [], []
    monkeypatch.setattr(transport, "sleep_sync", delays.append)
    state = session(tmp_path, monkeypatch, limit=1)
    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "synthetic limit"}},
                              headers={"Retry-After": retry_after} if retry_after else {})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = provider.CompatibleChatOpenAI(model="fixture", api_key="fixture", base_url="https://fixture.invalid/v1", http_client=client, max_retries=0)
        with state.activate(), pytest.raises(transport.RateLimited):
            model.invoke("synthetic")
    assert delays == expected and len(calls) == 4
    view = state.budget.view()
    assert view["model_calls"] == 1 and view["http_attempts"] == 4
    assert view["unknown_usage_calls"] == 4


def test_one_rate_limit_then_success(tmp_path, monkeypatch):
    delays, calls = [], []
    monkeypatch.setattr(transport, "sleep_sync", delays.append)
    state = session(tmp_path, monkeypatch)
    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "limit"}}) if len(calls) == 1 else httpx.Response(200, json=success())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = provider.CompatibleChatOpenAI(model="fixture", api_key="fixture", base_url="https://fixture.invalid/v1", http_client=client, max_retries=0)
        with state.activate():
            assert model.invoke("fixture").content == "OK"
    assert delays == [10] and state.budget.view()["model_calls"] == 1


def test_environment_and_expected_safety_do_not_strike_model():
    limited = classification.classify({"status": "environment_rate_limited", "route": "analysis"})
    blocked = classification.classify({"status": "blocked", "route": "analysis", "validation": {"scope": "method_constraint_block"}})
    assert not limited["stop_eligible"] and not blocked["stop_eligible"]
    assert not classification.should_stop([limited, limited, blocked, blocked])
    first = classification.rate_limit_batch_action(0, limited)
    assert first == {"consecutive_rate_limited": 1, "stop_batch": False, "pause_seconds": 300}
    assert classification.rate_limit_batch_action(1, limited)["stop_batch"]
