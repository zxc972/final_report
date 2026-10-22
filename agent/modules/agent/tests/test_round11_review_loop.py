"""Replay actual R10 revision evidence through the product outer repair graph."""
import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_analysis_agent import agent
from test_round8_closure import sealed, fake_execution


def execute_loop(tmp_path, monkeypatch, *, always_revise=False, numeric_fails_first=False):
    tools, _, _ = sealed(tmp_path, monkeypatch)
    fake_execution(tools)
    fixture=json.loads((Path(__file__).parent/'fixtures/round10_review_revise.json').read_text())
    observed=[]
    internal=importlib.import_module(agent.__package__+'.analysis_internal_review')
    numeric=importlib.import_module(agent.__package__+'.analysis_independent_numeric')
    def review(*args, **kwargs):
        observed.append(tools.session.state()['phase'])
        if always_revise or len(observed)==1:
            return copy.deepcopy(fixture['response'])
        return {'decision':'pass','protocol_valid':True,'findings':[],'limitations':['Synthetic replay only']}
    monkeypatch.setattr(internal,'run_review',review)
    if numeric_fails_first:
        monkeypatch.setattr(numeric,'current_summary',lambda value:{'status':'fail' if len(observed)==1 else 'pass','mismatch_count':1 if len(observed)==1 else 0,'host_verified':True})
    tools._internal_review_model=object()
    phases=[]
    class Coder:
        calls=0
        def invoke(self, payload, config=None):
            self.calls+=1
            phases.append(tools.session.state()['phase'])
            if self.calls>1:
                feedback=json.loads((tools.workdir/'tool_results/validation_feedback.json').read_text())
                assert feedback['internal_review']['decision']=='revise'
                assert 'independent_numeric' not in feedback
            tools.write_code('/work/analysis.py',f'# synthetic replay revision {self.calls}')
            assert tools.run_python()['state']['phase']=='finalized'
            return {'messages':[SimpleNamespace(content='Synthetic report replay; no scientific inference.')]}
    coder=Coder()
    validator=importlib.import_module(agent.__package__+'.analysis_validation').ArtifactValidator()
    result=agent._build_graph(coder,tools,validator,InMemorySaver()).invoke({'request':'Replay a historical AI review','history':[],'iterations':0},{'configurable':{'thread_id':'r11-replay'}})
    return tools,result,phases,observed,fixture


@pytest.mark.parametrize('numeric_fails_first',[False,True])
def test_real_review_revise_enters_repair_before_numeric_stop(tmp_path,monkeypatch,numeric_fails_first):
    tools,result,phases,observed,fixture=execute_loop(tmp_path,monkeypatch,numeric_fails_first=numeric_fails_first)
    assert fixture['response']['decision']=='revise' and len(fixture['response']['findings'])==4
    assert result['status']=='completed' and result['iterations']==2
    assert phases==['sealed','executed_failed']
    assert tools.executions==2 and len(observed)==2
    assert any(tools.control_store.read(p.name)['record'].get('review_pending') for p in tools.control_store.versions('session'))
    assert tools.session.record['review_pending'] is False


def test_revision_limit_is_three_outer_rounds(tmp_path,monkeypatch):
    tools,result,phases,observed,_=execute_loop(tmp_path,monkeypatch,always_revise=True)
    assert result['iterations']==3 and len(observed)==3
    assert tools.executions==3 and tools.session.state()['phase']=='executed_failed'
    assert result['status']!='completed'


def test_review_revision_can_read_its_own_report_and_source(tmp_path,monkeypatch):
    tools,_,_=sealed(tmp_path,monkeypatch)
    phase=importlib.import_module(agent.__package__+'.analysis_phase_tools')
    assert phase.read_error_allowed(tools,{'path':'/work/report.md'}) is False
    tools.session.record['review_pending']=True
    assert phase.read_error_allowed(tools,{'path':'/work/report.md'}) is True
    assert phase.read_error_allowed(tools,{'path':'/work/analysis.py'}) is True
    assert phase.read_error_allowed(tools,{'path':'/inputs/0/surf/lh.thickness'}) is False
