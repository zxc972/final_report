import importlib
import pytest
from test_analysis_agent import agent

policy=importlib.import_module(agent.__package__+'.analysis_failure_classification')


@pytest.mark.parametrize('patch,category',[
    ({'routing':{'parseStatus':'route_failed'}},'route_failed'),
    ({'validation':{'public_output_contract':{'status':'fail'}}},'contract_failed'),
    ({'validation':{'independent_numeric':{'status':'fail','numeric_mismatch_count':1}}},'numeric_mismatch'),
    ({'validation':{'internal_review':{'decision':'revise','protocol_valid':True}}},'review_incomplete'),
    ({'status':'incomplete_review','validation':{'internal_review':{'decision':'unreviewed','transport_exhausted':True}}},'review_incomplete'),
    ({'model_calls':30},'agent_budget_exhausted'),
    ({'execution':{'status':'failed','exit_code':1}},'execution_error'),
])
def test_specific_terminal_root_cause(patch,category):
    result=policy.classify({'status':'failed','route':'analysis',**patch})
    assert result['category']==category
    assert result['stop_eligible'] is not bool(patch.get('validation',{}).get('internal_review',{}).get('transport_exhausted'))


def test_different_roots_and_transport_do_not_stop_a_model():
    contract=policy.classify({'route':'analysis','status':'failed','validation':{'public_output_contract':{'status':'fail'}}})
    numeric=policy.classify({'route':'analysis','status':'blocked','validation':{'independent_numeric_status':'fail'}})
    upstream=policy.classify({'route':'analysis','status':'incomplete_review'})
    assert not policy.should_stop([contract,numeric,upstream,upstream])
    assert policy.should_stop([contract,numeric,upstream,contract])
    assert policy.failure_counts([contract,upstream])=={'contract_failed':1}


def test_recovered_transport_does_not_turn_a_success_into_a_failure():
    assert policy.classify({'status':'completed','route':'analysis','transport_retries':2})['category'] is None
