import os
import pytest
from test_analysis_agent import agent, TestOnlyExecutor, FakeKnowledge
from pathlib import Path
from unittest.mock import patch
from importlib import import_module
profile = import_module(agent.__package__ + '.analysis_profile')


def test_confirmed_deepseek_profile():
    with patch.dict(os.environ, {}, clear=True):
        opts = profile.coding_model_options('deepseek-v4-pro','https://inferaiapi.com/v1')
    assert opts == {'timeout':150,'max_retries':0,'max_tokens':20000,'extra_body':{'thinking':{'type':'disabled'}}}


@pytest.mark.parametrize('url,model',[
 ('https://other.example/v1','deepseek-v4-pro'),
 ('https://inferaiapi.com/v1','some-other-model'),
 ('http://inferaiapi.com/v1','deepseek-v4-pro'),
 ('https://inferaiapi.com','deepseek-v4-pro'),
 ('https://inferaiapi.com.evil.invalid/v1','deepseek-v4-pro'),
 ('https://inferaiapi.com/v1?x=y','deepseek-v4-pro'),
])
def test_unknown_provider_retains_original_options(url,model):
    with patch.dict(os.environ, {}, clear=True):
        assert profile.coding_model_options(model,url) == {'timeout':60,'max_retries':0,'max_tokens':4096}


@pytest.mark.parametrize('name,value',[
 ('ANALYSIS_MODEL_MAX_TOKENS','40000'),('ANALYSIS_MODEL_MAX_TOKENS','bad'),
 ('ANALYSIS_MODEL_TIMEOUT_SECONDS','0'),('ANALYSIS_MODEL_MAX_TOKENS','-1'),
])
def test_server_settings_fail_before_provider_call(name,value):
    with patch.dict(os.environ,{name:value},clear=True), pytest.raises(ValueError,match=name):
        profile.coding_model_options('deepseek-v4-pro','https://inferaiapi.com/v1')


def test_operator_override_is_bounded():
    with patch.dict(os.environ,{'ANALYSIS_MODEL_MAX_TOKENS':'24000','ANALYSIS_MODEL_TIMEOUT_SECONDS':'180'},clear=True):
        opts=profile.coding_model_options('deepseek-v4-pro','https://inferaiapi.com/v1/')
    assert opts['max_tokens']==24000 and opts['timeout']==180


def test_actual_coding_builder_passes_profile_to_model(tmp_path):
    work=tmp_path/'work';data=tmp_path/'data';work.mkdir();data.mkdir()
    tools=agent.AnalysisTools(work,[data],TestOnlyExecutor(work,[data]),FakeKnowledge())
    seen={}
    class StopCapture(Exception): pass
    def capture(**kwargs):
        seen.update(kwargs)
        raise StopCapture()
    with patch.dict(os.environ,{},clear=True),pytest.raises(StopCapture):
        agent._build_coding_agent(tools,model='deepseek-v4-pro',base_url='https://inferaiapi.com/v1',api_key='not-in-state',model_factory=capture)
    assert seen['max_tokens']==20000 and seen['extra_body']=={'thinking':{'type':'disabled'}}
    assert seen['timeout']==150 and agent.MAX_MODEL_CALLS==64 and agent.MAX_EXECUTIONS==24
