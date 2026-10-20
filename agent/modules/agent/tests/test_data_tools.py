"""External datasets, real filesystem tools and idempotent pipeline submission."""
import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from modules.agent.backend.data_tools import DataTools
from modules.agent.backend.pipeline_bridge import PipelineBridge, function_specs
from modules.agent.backend.analysis_access import approved_input_roots
from modules.agent.backend import analysis_agent as agent, pipeline, tasks, api


class DataToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base/'users'/'alice'/'output'; self.output.mkdir(parents=True)
        self.source = self.base/'elsewhere'/'dataset'; self.source.mkdir(parents=True)
        self.env = patch.dict(os.environ, {'AGENT_DATA_ROOTS':str(self.source),
            'AGENT_ANALYSIS_STATE_DIR':str(self.base/'server-state'), 'PRIMATEX_PIPELINE_IMAGE':''})
        self.env.start(); self.addCleanup(self.env.stop)
        t1 = self.source/'sub-001'/'ses-01'/'anat'; t1.mkdir(parents=True)
        self.t1 = t1/'sub-001_ses-01_T1w.nii.gz'; self.t1.write_bytes(b'fixture-not-real-MRI')
        (t1/'sub-001_ses-01_T2w.nii.gz').write_bytes(b'fixture')
        (self.source/'participants.tsv').write_text('participant_id\tspecies\nsub-001\tMacaque\n')
        (self.source/'example.py').write_text('def inspect_data():\n    return "thickness"\n')
        self.data = DataTools(self.output, approved_input_roots(self.output,None))
        self.bridge = PipelineBridge(self.data, threads=3)

    def test_ls_glob_grep_and_read_on_external_source(self):
        roots=self.data.list_roots()
        self.assertEqual(roots['roots'][0]['path'],str(self.source))
        self.assertEqual(roots['outputDirectory'],str(self.output))
        self.assertIn('participants.tsv',[r['name'] for r in self.data.ls(str(self.source))['entries']])
        self.assertIn(str(self.t1),self.data.glob('*T1w.nii.gz',str(self.source))['matches'])
        result=self.data.grep('thickness',str(self.source),file_pattern='*.py')
        self.assertEqual(result['matches'][0]['line'],2)
        self.assertIn('2: sub-001',self.data.read_file('/inputs/0/participants.tsv')['content'])
        self.assertEqual(len(self.data.ls(str(self.source),limit=1)['entries']),1)
        self.assertIsNotNone(self.data.ls(str(self.source),limit=1)['nextOffset'])

    def test_subject_discovery_does_not_choose_ambiguous_scan_or_guess_species(self):
        result=self.data.discover_subjects(str(self.source))
        self.assertEqual(result['count'],1)
        subject=result['subjects'][0]
        self.assertEqual(subject['subjectId'],'sub-001_ses-01')
        self.assertEqual(subject['t1Candidates'],[str(self.t1)])
        self.assertFalse(subject['ambiguous']); self.assertIsNone(subject['species'])
        (self.t1.parent/'sub-001_ses-01_run-02_T1w.nii.gz').write_bytes(b'fixture')
        self.assertTrue(self.data.discover_subjects(str(self.source))['subjects'][0]['ambiguous'])

    def test_flat_and_subject_t1_layouts(self):
        (self.source/'101410_0000.nii.gz').write_bytes(b'fixture')
        folder=self.source/'monkey-A'/'T1'; folder.mkdir(parents=True)
        (folder/'scan.nii.gz').write_bytes(b'fixture')
        ids={r['subjectId'] for r in self.data.discover_subjects(str(self.source))['subjects']}
        self.assertIn('101410_0000',ids); self.assertIn('monkey-A',ids)

    def test_private_unregistered_and_symlink_paths_rejected(self):
        (self.source/'.env').write_text('private')
        with self.assertRaises(ValueError): self.data.read_file(str(self.source/'.env'))
        with self.assertRaises(ValueError): self.data.ls(str(self.base))
        with self.assertRaises(ValueError): self.data.read_file('/inputs/0/../outside.txt')
        try: (self.source/'alias').symlink_to(self.base,target_is_directory=True)
        except OSError: self.skipTest('Symlinks unavailable')
        with self.assertRaises(ValueError): self.data.ls(str(self.source/'alias'))
        self.assertNotIn('alias',[r['name'] for r in self.data.ls(str(self.source))['entries']])

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO')
    def test_grep_and_read_do_not_block_on_fifo(self):
        os.mkfifo(self.source/'pipe.csv')
        with self.assertRaises(ValueError): self.data.read_file(str(self.source/'pipe.csv'))
        self.data.grep('anything',str(self.source))

    def test_discover_then_submit_keeps_external_input_and_enforces_output(self):
        candidate=self.data.discover_subjects(str(self.source))['subjects'][0]
        with patch('modules.agent.backend.pipeline.ensure_primx_exists'), \
             patch.object(tasks,'submit_pipeline_task',return_value=Future()) as submit:
            first=self.bridge.submit_pipeline(candidate['subjectId'],candidate['t1Candidates'][0],
                                               ['preprocess-1'],'Macaque')
            again=PipelineBridge(self.data,threads=3).submit_pipeline(candidate['subjectId'],str(self.t1),
                                               ['preprocess-1'],'Macaque')
            self.assertEqual(submit.call_count,1)
            self.assertEqual(first['taskId'],again['taskId'])
            self.assertTrue(again['reused'])
        self.assertEqual(first['inputPath'],str(self.t1))

    def test_same_subject_not_double_queued_and_other_users_cannot_query(self):
        def submit_one():
            return self.bridge.submit_pipeline('unique',str(self.t1),['preprocess-1'],'Macaque')
        with patch('modules.agent.backend.pipeline.ensure_primx_exists'), \
             patch.object(tasks,'submit_pipeline_task',return_value=Future()) as submit:
            with ThreadPoolExecutor(2) as pool: receipts=list(pool.map(lambda _:submit_one(),range(2)))
            self.assertEqual(submit.call_count,1)
            self.assertEqual(receipts[0]['taskId'],receipts[1]['taskId'])
            self.assertEqual(sum(r['reused'] for r in receipts),1)
            args=submit.call_args.args[2]
            self.assertEqual(args.t1_path,str(self.t1))
            self.assertEqual(args.out_path,str(self.output/'unique'))
            self.assertEqual(args.threads,3)
            task=tasks.TASKS.get(receipts[0]['taskId'])
            task.status='completed'
            self.assertEqual(self.bridge.pipeline_status(task.task_id)['status'],'completed')
            bob=self.base/'users'/'bob'/'output'; bob.mkdir(parents=True)
            with self.assertRaises(ValueError): PipelineBridge(DataTools(bob,[self.source])).pipeline_status(task.task_id)

    def test_existing_output_traversal_and_bad_source_do_not_submit(self):
        dest=self.output/'already'; dest.mkdir(); (dest/'keep.txt').write_text('keep')
        with patch('modules.agent.backend.pipeline.ensure_primx_exists'), \
             patch.object(tasks,'submit_pipeline_task') as submit:
            for subject,source in [('already',str(self.t1)),('../escape',str(self.t1)),
                                   ('missing',str(self.source/'absent.nii.gz'))]:
                with self.subTest(subject=subject),self.assertRaises(ValueError):
                    self.bridge.submit_pipeline(subject,source,['preprocess-1'],'Macaque')
            submit.assert_not_called()
        self.assertEqual((dest/'keep.txt').read_text(),'keep')

    def test_tool_schemas_share_real_directory_and_submission_tools(self):
        specs=function_specs(self.data,self.bridge)
        self.assertEqual({t['function']['name'] for t in specs},
            {'list_roots','ls','glob','grep','read_file','discover_subjects','submit_pipeline','pipeline_status'})

    def test_new_data_folder_is_discovered_without_moving_or_reconfiguring_it(self):
        home=self.base/'data-home'; home.mkdir()
        (home/'agent').mkdir(); (home/'structural_env').mkdir()
        with patch.dict(os.environ,{'AGENT_DATA_ROOTS':'','AGENT_DATA_DIRECTORY':str(home)}):
            self.assertEqual(approved_input_roots(self.output,None),[])
            novel=home/'new_cohort'; novel.mkdir()
            roots=approved_input_roots(self.output,None)
            self.assertEqual(roots,[novel])
            registered=DataTools(self.output,roots)
            self.assertEqual(registered.ls(str(home))['entries'][0]['path'],str(novel))

    def test_pipeline_api_can_discover_external_subject_and_submit_without_copy(self):
        (self.output.parent/'.auth.json').write_text(json.dumps({'salt':'fixture-salt'}))
        token=api.sign_user_token('alice','fixture-salt')
        responses=[('discover_subjects',{'path':str(self.source)}),
            ('submit_pipeline',{'subject_id':'api-subject','t1_path':str(self.t1),
                                'steps':['preprocess-1'],'species':'Macaque'})]
        observed=[]
        async def model_call(base,key,model,messages,tools):
            observed.append({t['function']['name'] for t in tools})
            if responses:
                name,args=responses.pop(0)
                msg={'role':'assistant','content':None,'tool_calls':[{'id':name,'type':'function',
                    'function':{'name':name,'arguments':json.dumps(args)}}]}
            else: msg={'role':'assistant','content':'Task submitted.'}
            return {'choices':[{'message':msg}]}
        with patch.object(api,'ACCESS_TOKEN',''), \
             patch.object(api,'call_chat_completions',side_effect=model_call), \
             patch('modules.agent.backend.pipeline.ensure_primx_exists'), \
             patch.object(tasks,'submit_pipeline_task',return_value=Future()) as submit:
            with TestClient(api.build_app()) as client:
                result=client.post('/api/agent/chat',json={'mode':'pipeline','provider':'custom',
                    'model':'fixture','apiKey':'fixture-key','message':'Find and preprocess the macaque T1.',
                    'context':{'userId':'alice','userToken':token,'workspaceDirectory':str(self.output)}})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(submit.call_count,1)
        self.assertTrue(all('discover_subjects' in names and 'submit_pipeline' in names for names in observed))
        receipts=result.json()['metadata']['tools']
        self.assertEqual(receipts[-1]['inputPath'],str(self.t1))
        self.assertEqual(receipts[-1]['outPath'],str(self.output/'api-subject'))
        self.assertFalse((self.output.parent/'input').exists())

    def test_sif_command_has_gpu_flag_and_external_readonly_input(self):
        from modules.agent.backend.models import RunPipelineArgs
        image=self.base/'runtime.sif'; image.write_bytes(b'fixture')
        args=RunPipelineArgs(subjectId='subject',workspaceDirectory=str(self.output),
            t1Path=str(self.t1),steps=['preprocess-1'],out_path=str(self.output/'subject'))
        with patch.dict(os.environ,{'PRIMATEX_PIPELINE_IMAGE':str(image)}), \
             patch.object(pipeline.shutil,'which',return_value='/usr/bin/apptainer'):
            normal=pipeline.build_process_command(args,['neuro','preprocess-1'],'preprocess-1')
            gpu=pipeline.build_process_command(args,['seg','wm'],'seg-wm')
        self.assertNotIn('--nv',normal); self.assertIn('--nv',gpu)
        self.assertIn(f'{self.t1.parent}:{self.t1.parent}:ro',gpu)
        self.assertIn(f'{self.output}:{self.output}:rw',gpu)

    @unittest.skipUnless(os.name=='posix','Real subprocess smoke uses a POSIX CLI fixture')
    def test_real_background_queue_passes_external_input_to_cli(self):
        fixture=self.base/'primx-fixture'
        fixture.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        fixture.chmod(0o700)
        try:
            with patch.object(pipeline,'PRIMX_PATH',str(fixture)):
                receipt=self.bridge.submit_pipeline('queue-smoke',str(self.t1),['preprocess-1'],'Macaque')
                task=tasks.TASKS.get(receipt['taskId'])
                task.future.result(timeout=10)
            self.assertEqual(task.status,'completed',task.error)
            log=Path(task.log_path).read_text()
            self.assertIn(str(self.t1),log)
            self.assertIn(str(self.output/'queue-smoke'),log)
            self.assertFalse((self.output.parent/'input').exists())
        finally:
            tasks.shutdown_cleanup()

    def test_real_deepagents_discovery_and_submit_uses_real_filesystem(self):
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage,ToolMessage
        from langchain_core.outputs import ChatGeneration,ChatResult
        from pydantic import PrivateAttr
        source=str(self.source)
        captured=[]

        class ScriptedModel(BaseChatModel):
            _calls: int=PrivateAttr(default=0)
            @property
            def _llm_type(self): return 'deterministic-submission-test'
            def bind_tools(self,tools,**kwargs): return self
            def get_num_tokens(self,text): return max(1,len(text)//4)
            def get_num_tokens_from_messages(self,messages,tools=None):
                return sum(self.get_num_tokens(str(m.content)) for m in messages)
            def _generate(self,messages,**kwargs):
                for m in messages:
                    if isinstance(m,ToolMessage) and m.name=='discover_subjects':
                        captured.append(json.loads(m.content))
                calls=[('ls',{'path':source}),('grep',{'pattern':'Macaque','path':source}),
                       ('discover_subjects',{'path':source})]
                index=self._calls; self._calls+=1
                if index<len(calls): name,args=calls[index]
                elif index==len(calls):
                    record=captured[-1]['subjects'][0]
                    name,args='submit_pipeline',{'subject_id':record['subjectId'],
                        't1_path':record['t1Candidates'][0],'steps':['preprocess-1'],'species':'Macaque'}
                else:
                    return ChatResult(generations=[ChatGeneration(message=AIMessage(content='Task queued.'))])
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[
                    {'name':name,'args':args,'id':f'call-{index}','type':'tool_call'}]))])

        with patch('modules.agent.backend.pipeline.ensure_primx_exists'), \
             patch.object(tasks,'submit_pipeline_task',return_value=Future()) as submit:
            result=asyncio.run(agent.run_analysis(message='Process the discovered macaque T1.',user_id='alice',
                workspace=self.output,conversation_id='discovery-submit',model='offline',base_url='https://example.invalid',
                api_key='do-not-store',input_roots=[self.source],model_factory=lambda **kwargs:ScriptedModel()))
        self.assertEqual(result['status'],'submitted',result)
        self.assertEqual(result['executions'],0)
        self.assertEqual(submit.call_count,1)
        self.assertEqual(result['pipeline_tasks'][0]['inputPath'],str(self.t1))
        self.assertTrue(captured)


if __name__=='__main__': unittest.main()
