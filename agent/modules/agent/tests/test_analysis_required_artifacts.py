import json,asyncio
from pathlib import Path
from importlib import import_module
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_analysis_agent import agent, TestOnlyExecutor, FakeKnowledge, fixture_code
Validator=import_module(agent.__package__+'.analysis_validation').ArtifactValidator


@pytest.mark.parametrize('bad',[True,'report.md', ['../x'], ['/x'],['a//b'],['a\\b'],['a:foo'],['.hidden'],['x','x'],['a*'],[None]])
def test_bad_required_names_rejected(bad):
    with pytest.raises(ValueError):agent._required_artifact_contract(bad)


def test_name_contract_supports_nested_unique_outputs_without_globbing():
    c=agent._required_artifact_coverage(['report.md','tables/a.tsv'],[{'path':'results/report.md'},{'path':'tables/a.tsv'}])
    assert c['complete'] and not c['missing']
    assert not agent._required_artifact_coverage(['report.md'],[{'path':'a/report.md'},{'path':'b/report.md'}])['complete']


def test_missing_file_cannot_be_removed_from_caller_contract_to_get_completed(tmp_path):
    work=tmp_path/'work';data=tmp_path/'data';work.mkdir();data.mkdir()
    tools=agent.AnalysisTools(work,[data],TestOnlyExecutor(work,[data]),FakeKnowledge())
    class Coder:
        def invoke(self,state,config):
            tools.write_code('/work/analysis.py',fixture_code());tools.run_python('/work/analysis.py')
            return {'messages':[{'role':'assistant','content':'Only summary exists; all requested outputs completed.'}]}
    graph=agent._build_graph(Coder(),tools,Validator(),InMemorySaver())
    res=graph.invoke({'request':'Produce summary and report','iterations':0,'execution_required':True,'required_artifacts':['summary.json','report.md']},{'configurable':{'thread_id':'missing'}})
    assert res['status']=='failed' and res['iterations']==agent.MAX_ROUNDS
    assert res['validation']['required_artifact_coverage']['missing']==['report.md']
    assert res['required_artifacts']==['summary.json','report.md']


def test_real_code_repair_adds_required_report_and_preserves_contract(tmp_path):
    work=tmp_path/'work';data=tmp_path/'data';work.mkdir();data.mkdir()
    tools=agent.AnalysisTools(work,[data],TestOnlyExecutor(work,[data]),FakeKnowledge())
    class Coder:
        n=0
        def invoke(self,state,config):
            self.n+=1
            code=fixture_code()
            if self.n>1:
                assert 'report.md' in state['messages'][0]['content']
                code+='\nPath("report.md").write_text("Actual test fixture report; no scientific claim.")\n'
                code+='m=json.loads(Path("analysis_manifest.json").read_text());m["artifacts"].append({"path":"report.md","kind":"markdown"});Path("analysis_manifest.json").write_text(json.dumps(m))\n'
            tools.write_code('/work/analysis.py',code);tools.run_python('/work/analysis.py')
            return {'messages':[{'role':'assistant','content':'Observed test-only outputs.'}]}
    saver=InMemorySaver();graph=agent._build_graph(Coder(),tools,Validator(),saver);config={'configurable':{'thread_id':'repair'}}
    res=graph.invoke({'request':'Produce report','iterations':0,'execution_required':True,'required_artifacts':['summary.json','report.md']},config)
    assert res['status']=='completed' and res['iterations']==2 and tools.executions==2
    coverage=res['validation']['required_artifact_coverage'];assert coverage['complete'] and len(coverage['required'])==2
    saved=graph.get_state(config).values
    with pytest.raises(ValueError,match='original required artifact'):agent._check_required_artifact_resume(saved,[],True)
    agent._check_required_artifact_resume(saved,['report.md','summary.json'],True)


def test_public_bad_contract_fails_before_any_api_call(tmp_path):
    with pytest.raises(ValueError,match='bounded list'):
        asyncio.run(agent.run_analysis(message='analyze',user_id='test',workspace=tmp_path,conversation_id='x',model='test',base_url='https://invalid.example/v1',api_key='fixture',input_roots=[],required_artifacts='report.md'))
