import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from modules.agent.backend import api
from modules.agent.backend.analysis_access import public_context, approved_input_roots


class AnalysisAccessTests(unittest.TestCase):
    def test_context_allowlist_excludes_nested_secrets(self):
        data = public_context({'userId':'alice', 'userToken':'secret', 'apiKey':'secret',
            'extra':{'password':'secret'},'recentUpload':{'t1Path':'/a.nii','userToken':'secret'}})
        self.assertNotIn('secret', json.dumps(data))
        self.assertEqual(data['recentUpload']['t1Path'], '/a.nii')

    def test_input_roots_cannot_escape_grants(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'AGENT_ANALYSIS_DATA_ROOTS':''}):
            workspace=Path(d)/'alice'/'output'; workspace.mkdir(parents=True)
            with self.assertRaises(ValueError): approved_input_roots(workspace,[d])
            self.assertEqual(approved_input_roots(workspace,None),[])
            subject = workspace/'subject001'; subject.mkdir()
            (workspace/'.analysis_runs').mkdir()
            self.assertEqual(approved_input_roots(workspace,None),[subject])

    def test_analysis_auth_dispatch_and_no_credential_context(self):
        with tempfile.TemporaryDirectory() as d, patch.object(api,'ACCESS_TOKEN',''):
            workspace=Path(d)/'alice'/'output'; workspace.mkdir(parents=True)
            (workspace.parent/'.auth.json').write_text(json.dumps({'salt':'unit-test-salt'}))
            token=api.sign_user_token('alice','unit-test-salt')
            payload={'mode':'analysis','message':'inspect tables','provider':'custom',
                'model':'test-model','apiKey':'model-key','context':{'userId':'alice',
                'workspaceDirectory':str(workspace),'userToken':token}}
            with patch('modules.agent.backend.analysis_agent.run_analysis',new_callable=AsyncMock) as run:
                run.return_value={'message':'finished','status':'validated'}
                with TestClient(api.build_app()) as client:
                    response=client.post('/api/agent/chat',json=payload)
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['metadata']['mode'],'analysis')
                    self.assertNotIn(token,str(run.call_args))
                    self.assertNotIn('model-key',response.text)
                    payload['context']['userToken']='wrong'
                    self.assertEqual(client.post('/api/agent/analysis',json=payload).status_code,401)
                    self.assertEqual(run.call_count,1)

    def test_symlinked_input_cannot_expand_grants(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'AGENT_ANALYSIS_DATA_ROOTS':''}):
            workspace = Path(d)/'alice'/'output'; workspace.mkdir(parents=True)
            outside = Path(d)/'bob'; outside.mkdir()
            try: (workspace.parent/'input').symlink_to(outside,target_is_directory=True)
            except OSError: self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError): approved_input_roots(workspace,None)

    def test_symlink_component_in_requested_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'AGENT_ANALYSIS_DATA_ROOTS':''}):
            workspace = Path(d)/'alice'/'output'; workspace.mkdir(parents=True)
            source = workspace.parent/'input'; source.mkdir()
            nested = source/'real'; nested.mkdir()
            try: (source/'alias').symlink_to(nested,target_is_directory=True)
            except OSError: self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError): approved_input_roots(workspace,[str(source/'alias')])

    def test_symlinked_workspace_is_rejected(self):
        from modules.agent.backend.analysis_access import analysis_workspace
        with tempfile.TemporaryDirectory() as d:
            real=Path(d)/'real'/'output'; real.mkdir(parents=True)
            try: (Path(d)/'alice').symlink_to(real.parent,target_is_directory=True)
            except OSError: self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError): analysis_workspace(str(Path(d)/'alice'/'output'),'alice')
