"""Protected observations and model-authored reflections for an execution-feedback loop.
No expected study answers, fixes, or scientific certification are generated here.
"""
from __future__ import annotations
import hashlib,json,os,re,stat,threading,time,uuid
from pathlib import Path
from typing import Any
class FeedbackJournal:
    def __init__(self,workdir:Path):
        self.workdir=Path(workdir).resolve(strict=True)
        self.root=self.workdir.parent/'.analysis_feedback'/self.workdir.name
        cur=self.workdir.parent
        for part in ['.analysis_feedback',self.workdir.name]:
            cur=cur/part
            if cur.is_symlink():raise ValueError('Feedback journal cannot use symlinks')
            cur.mkdir(exist_ok=True)
        self.lock=threading.RLock()
    def _write(self,kind,obj):
        oid=uuid.uuid4().hex
        rec={'schema':'primatex.analysis_feedback.v1','id':oid,'kind':kind,'time':time.time(),**obj}
        raw=json.dumps(rec,ensure_ascii=False).encode()
        if len(raw)>120000:raise ValueError('Feedback observation exceeds bound')
        path=self.root/(oid+'.json')
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
        with self.lock:
            fd=os.open(path,flags,0o600)
            with os.fdopen(fd,'wb')as f:f.write(raw)
        return rec
    def _read(self,oid):
        if not isinstance(oid,str)or not re.fullmatch('[a-f0-9]{32}',oid):raise ValueError('Registered feedback ID required')
        path=self.root/(oid+'.json')
        if path.is_symlink()or not stat.S_ISREG(path.lstat().st_mode)or path.stat().st_size>120000:raise ValueError('Invalid feedback observation')
        return json.loads(path.read_bytes())
    @staticmethod
    def failure_details(result):
        """Retain actual contract failures even when the subprocess exited zero."""
        failures = []
        def visit(value, path, depth=0):
            if not isinstance(value, dict) or depth > 5:
                return
            status = value.get('status')
            bad = ((isinstance(status, str) and status in {'error', 'fail', 'failed', 'timeout', 'blocked'})
                   or (isinstance(status, str) and ('contract' in status and status.endswith('failed')))
                   or value.get('returncode') not in (None, 0)
                   or value.get('exit_code') not in (None, 0)
                   or value.get('valid') is False or value.get('passed') is False
                   or value.get('argument_validation_failed') is True)
            if bad:
                detail = {'path': path, 'status': status}
                for key in ('error', 'reason', 'errors', 'files', 'missing', 'returncode', 'exit_code'):
                    if key in value:
                        detail[key] = value[key]
                encoded = json.dumps(detail, ensure_ascii=False, default=str)
                if len(encoded) > 4000:
                    detail = {'path': path, 'status': status, 'observation_prefix': encoded[:3500], 'full_observation_sha256': hashlib.sha256(encoded.encode()).hexdigest()}
                failures.append(detail)
            for key in ('automatic_finalization', 'validation', 'public_output_contract',
                        'output_contract', 'contract', 'artifact_validation'):
                visit(value.get(key), path + '.' + key, depth + 1)
        visit(result, 'result')
        return failures[:20]
    @staticmethod
    def failed(result):
        return bool(FeedbackJournal.failure_details(result))
    def observe(self,tool_name:str,arguments:dict,result:dict):
        if tool_name in ['read_analysis_feedback','record_analysis_reflection']:return None
        args={k:v for k,v in arguments.items()if k not in ['code']}
        if 'code'in arguments:args['declared_code_sha256']=hashlib.sha256(str(arguments['code']).encode()).hexdigest()
        args=json.loads(json.dumps(args,ensure_ascii=False)[:20000]) if len(json.dumps(args,ensure_ascii=False))<=20000 else {'arguments_status':'too_large_not_retained'}
        serialized=json.dumps(result,ensure_ascii=False,default=str)
        # Store a bounded original observation, never synthesized diagnosis.
        kept=result if len(serialized)<=18000 else {'status':result.get('status'),'observation_prefix':serialized[:16000],'full_observation_sha256':hashlib.sha256(serialized.encode()).hexdigest(),'truncated':True}
        failed=self.failed(result)
        return self._write('observation',{'tool':tool_name,'arguments':args,'failed':failed,'result':kept,'failure_details':self.failure_details(result),
            'evidence_scope':'Actual product tool response; neither a private reference nor expert judgment.'})
    def reflect(self,observation_id:str,hypothesis:str,next_check:str,knowledge_ids:list[str]|None=None):
        original=self._read(observation_id)
        if original.get('kind')!='observation'or not original.get('failed'):raise ValueError('Reflection must reference a real failed observation')
        for text in [hypothesis,next_check]:
            if not isinstance(text,str)or not 10<=len(text)<=1800:raise ValueError('Give a bounded substantive hypothesis and falsifiable next check')
        ids=knowledge_ids or []
        if not isinstance(ids,list)or len(ids)>8 or any(not isinstance(x,str)or len(x)>200 for x in ids):raise ValueError('Bounded knowledge references required')
        reflection=self._write('reflection',{'observation_id':observation_id,'hypothesis':hypothesis,'next_check':next_check,'knowledge_ids':ids,
            'authorship':'analysis_agent_model','verification_status':'hypothesis_only_not_yet_verified','source_observation_time':original['time']})
        return {'status':'ok','reflection_id':reflection['id'],'observation_id':observation_id,'verification_status':'hypothesis_only_not_yet_verified',
            'next':'Use evidence/data/runtime tools to test your hypothesis, then revise your own code and execute. Do not claim the reflection itself fixed the failure.'}
    def recent(self,limit=6):
        if type(limit)is not int or not 1<=limit<=12:raise ValueError('Feedback limit must be 1..12')
        records=[]
        for path in self.root.glob('*.json'):
            record=self._read(path.stem);records.append(record)
        records.sort(key=lambda x:(x['time'],x['id']))
        failures=[r for r in records if r['kind']=='observation'and r.get('failed')]
        reflections=[r for r in records if r['kind']=='reflection']
        executions=[r for r in records if r.get('tool')=='run_python']
        return {'status':'ok','failed_observations':failures[-limit:],'model_reflections':reflections[-limit:],'recent_execution_observations':executions[-2:],
            'total_observations':sum(r['kind']=='observation'for r in records),'total_failures':len(failures),'total_reflections':len(reflections),
            'scope':'Actual tool observations and model hypotheses. Later exit0 is not proof that an earlier scientific issue was resolved.'}

