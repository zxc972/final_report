"""Overall priority and draft/review scope are deterministic host decisions."""
import copy
import importlib
import pytest
from test_analysis_agent import agent

status=importlib.import_module(agent.__package__+'.analysis_overall_status')


def card():
    return {'verdict':'qualified','conclusion_text':'The Agent claims success.', 'reason':'Stored scale only', 'checks_passed':[], 'checks_not_passed':[]}


def validation(decision='pass'):
    return {'internal_review':{'decision':decision,'protocol_valid':decision in {'pass','revise'}}, 'public_output_contract':{'status':'pass','identity_mismatch_count':0}, 'independent_numeric':{'status':'pass','numeric_mismatch_count':0}}


@pytest.mark.parametrize('native,decision,expected',[
    ('completed','pass','qualified'), ('incomplete_review','unreviewed','incomplete_review'),
    ('completed','unreviewed','deferred'), ('failed','unreviewed','failed'),
    ('blocked','unreviewed','blocked'), ('failed','pass','failed'),
    ('completed','revise','deferred'), ('incomplete_review','revise','incomplete_review'),
])
def test_overall_priority_and_review_cap(native,decision,expected):
    result=status.finalize_card(card(),validation(decision),native,{'exit_code':0,'status':'success'},'finalized')
    assert result['overall_status']==expected
    assert result['component_statuses']['execution']=='passed'
    assert result['conclusion_text']=='The Agent claims success.'
    if decision!='pass':
        assert result['verdict']=='deferred'
        assert result['text_label']=='Agent draft (unreviewed)'
    else:
        assert result['text_label']=='Reviewed'


def test_reviewed_accepted_and_numeric_blocked_are_preserved():
    base=card()
    base['verdict']='accepted'
    assert status.finalize_card(base,validation(),'completed',{'status':'success','exit_code':0})['overall_status']=='accepted'
    base['verdict']='blocked'
    result=status.finalize_card(base,validation('unreviewed'),'failed',{'status':'success','exit_code':0})
    assert result['overall_status']=='blocked' and result['verdict']=='blocked'


def test_data_inspection_does_not_need_scientific_review():
    v={'scope':'data_inspection'}
    base=card()
    base['verdict']='accepted'
    result=status.finalize_card(base,v,'inspected',{})
    assert result['review_status']=='not_required' and result['overall_status']=='accepted'


def test_event_view_persists_the_same_overall_status(tmp_path,monkeypatch):
    chat=importlib.import_module(agent.__package__+'.agent_chat_state')
    monkeypatch.setenv('AGENT_ANALYSIS_STATE_DIR',str(tmp_path/'protected'))
    workspace=tmp_path/'workspace'
    workspace.mkdir()
    s=chat.ChatSession(workspace,'fixture','overall','','30')
    s.start('analysis','Synthetic',True)
    s.complete('fixture','draft','incomplete_review',overall_status='incomplete_review',component_statuses={'internal_review':'unreviewed'})
    view=chat.conversation_events(workspace,'fixture','overall',0)
    assert view['overall_status']=='incomplete_review'
    assert view['component_statuses']['internal_review']=='unreviewed'
