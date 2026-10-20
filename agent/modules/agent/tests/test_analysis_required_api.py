import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from modules.agent.backend import api


def payload_for(tmp_path):
    workspace=tmp_path/'alice/output';workspace.mkdir(parents=True)
    (workspace.parent/'.auth.json').write_text(json.dumps({'salt':'required-output-unit-salt'}))
    token=api.sign_user_token('alice','required-output-unit-salt')
    return {'mode':'analysis','message':'Generate requested tables and report','provider':'custom','model':'unit-model','apiKey':'fixture-model-key','context':{'userId':'alice','workspaceDirectory':str(workspace),'userToken':token,'requiredArtifacts':['table.tsv','report.md']}}


def test_real_api_dispatch_preserves_caller_contract(tmp_path):
    payload=payload_for(tmp_path)
    with patch.object(api,'ACCESS_TOKEN',''),patch('modules.agent.backend.analysis_agent.run_analysis',new_callable=AsyncMock)as run:
        run.return_value={'message':'fixture only','status':'failed','validation':{'required_artifact_coverage':{'complete':False}}}
        with TestClient(api.build_app())as client:r=client.post('/api/agent/analysis',json=payload)
    assert r.status_code==200
    assert run.call_args.kwargs['required_artifacts']==['table.tsv','report.md']
    assert r.json()['metadata']['validation']['required_artifact_coverage']['complete']is False
    assert 'fixture-model-key' not in r.text and payload['context']['userToken']not in str(run.call_args)


def test_bad_contract_rejected_by_actual_backend_before_model(tmp_path):
    payload=payload_for(tmp_path);payload['context']['requiredArtifacts']='report.md'
    with patch.object(api,'ACCESS_TOKEN',''):
        with TestClient(api.build_app())as client:r=client.post('/api/agent/analysis',json=payload)
    assert r.status_code==400 and 'required_artifacts' in r.text
