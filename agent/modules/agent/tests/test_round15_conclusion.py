"""Round15 typed conclusion feedback, dynamic enums and bounded idempotence."""
import importlib
import json
from langchain.agents.middleware.types import ModelRequest
from langchain_core.tools import StructuredTool
from test_analysis_agent import agent
from test_round8_closure import sealed, fake_execution

c = importlib.import_module(agent.__package__ + '.analysis_crossspecies')
phase = importlib.import_module(agent.__package__ + '.analysis_phase_tools')


def ready(tmp_path, monkeypatch):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    tools.write_code('/work/analysis.py', "print('fixture')")
    tools.run_python()
    monkeypatch.setenv('AGENT_CROSSSPECIES_RULES', '1')
    tools.control_store.save('crossspecies_observations', {
        'plan_sha256': tools.control_store.latest('plan')['sha256'],
        'execution_receipt_id': tools.last_execution['receipt_id'],
        'independent_numeric': {'host_verified': True, 'status': 'pass'},
    })
    original = c.observed_environment
    monkeypatch.setattr(c, 'observed_environment', lambda tools, plan: {
        **original(tools, plan), 'species': ['human'],
        'species_source': [{'method': 'explicit synthetic fixture'}],
        'atlas': {'name': 'DK', 'applicable': True},
    })
    return tools


def test_same_submission_is_cached_and_limit_defers(tmp_path, monkeypatch):
    tools = ready(tmp_path, monkeypatch)
    first = c.submit_conclusion(tools, 'Synthetic description', 'invalid')
    repeat = c.submit_conclusion(tools, 'Synthetic description', 'invalid')
    assert repeat['duplicate'] and repeat['conclusion_card'] == first['conclusion_card']
    assert len(tools.control_store.versions('conclusion')) == 1
    for i in range(3):
        c.submit_conclusion(tools, f'Synthetic description {i}', 'invalid')
    result = c.submit_conclusion(tools, 'Another description', 'invalid')
    assert result['submission_count'] == 4
    assert result['conclusion_card']['verdict'] == 'deferred'
    assert result['conclusion_card']['review_status'] == 'unreviewed'
    assert not result['conclusion_card']['must_rewrite']


def test_rejection_publishes_scopes_and_second_is_accepted(tmp_path, monkeypatch):
    tools = ready(tmp_path, monkeypatch)
    result = c.public_conclusion_feedback(c.submit_conclusion(tools, 'n=1 description', 'descriptive'))
    assert result['must_rewrite'] and result['reason']
    assert 'supplied_descriptive' in result['allowed_scopes']
    second = c.public_conclusion_feedback(c.submit_conclusion(tools, 'n=1 description', result['allowed_scopes'][0]))
    assert second['status'] == 'reviewed' and not second['must_rewrite']
    assert second['verdict'] == 'qualified'


def test_current_plan_tool_enum_and_meanings(tmp_path, monkeypatch):
    tools = ready(tmp_path, monkeypatch)
    def submit_conclusion(text: str, claim_scope: str):
        """Submit typed synthetic conclusion."""
        return c.submit_conclusion(tools, text, claim_scope)
    request = ModelRequest(model=None, messages=[], tools=[StructuredTool.from_function(submit_conclusion)])
    selected = phase.restrict_request(tools, request).tools[0]
    schema = selected.args_schema.model_json_schema()
    scope = schema['properties']['claim_scope']
    assert scope.get('enum', [scope.get('const')]) == list(c.conclusion_scope_options(tools))
    assert 'supplied_descriptive:' in selected.description
    assert 'population' in selected.description
