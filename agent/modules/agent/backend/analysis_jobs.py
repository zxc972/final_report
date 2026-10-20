"""Detached bounded computation for complete model-generated analysis programs.

Uses the existing namespace executor and unchanged artifact validator. Durable
submission is not successful analysis. Survives HTTP/server exit; does not
automatically resume interrupted imaging commands or certify science.
"""
from __future__ import annotations
import fcntl,hashlib,json,os,re,shutil,signal,stat,subprocess,sys,threading,time,uuid
from pathlib import Path
from typing import Any,Callable
from .analysis_profile import bounded_setting
MAX_JOB_SECONDS=bounded_setting('ANALYSIS_MAX_JOB_SECONDS',7200,1,86400)
MAX_JSON=4*1024*1024
MAX_STAGE_BYTES=1024**3
MAX_FILES=20000
ACTIVE={'preparing','queued','running','verifying','cancelling'}
UNCERTAIN={'unknown_after_worker_exit'}

def enabled()->bool:return os.environ.get('ANALYSIS_ENABLE_BACKGROUND_JOBS','0')=='1'
def _agent():
    from . import analysis_agent
    return analysis_agent
def _read(path:Path,root:Path)->dict:
    raw=_agent()._read_regular(path,root,MAX_JSON+1)
    if len(raw)>MAX_JSON:raise ValueError('Job record exceeds bounds')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Invalid job record')
    return value
def _write(path:Path,root:Path,value:dict)->None:
    data=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    if len(data.encode())>MAX_JSON:raise ValueError('Job record exceeds bounds')
    _agent()._write_regular(path,root,data)
def _hash(path:Path,root:Path)->str:
    with _agent()._parent_fd(path,root)as parent:
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb')as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):raise ValueError('Only regular job files may be hashed')
            return hashlib.file_digest(handle,'sha256').hexdigest()
def _job_root(workdir:Path)->Path:
    W=Path(workdir).absolute();_agent()._no_links(W,W.parent)
    if not W.is_dir():raise FileNotFoundError('Analysis run does not exist')
    root=W.parent/'.analysis_jobs'/W.name;_agent()._no_links(root,W.parent)
    root.mkdir(parents=True,exist_ok=True,mode=0o700);return root
def input_snapshot(roots:list[Path])->list[dict]:
    rows=[]
    for root in roots:
        _agent()._no_links(root,root.parent)
        for p in sorted(root.rglob('*')):
            rel=p.relative_to(root)
            if any(x.startswith('.')for x in rel.parts)or p.is_symlink():continue
            if p.is_file():
                rows.append({'root':str(root),'path':str(rel),'bytes':p.stat().st_size,'sha256':_hash(p,root)})
                if len(rows)>MAX_FILES:raise ValueError('Too many input files for bounded job provenance')
    return rows
def _digest(value:Any)->str:return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def _identity(pid:Any)->dict|None:
    """Record Linux start ticks, never signal an unrelated recycled PID."""
    if type(pid)is not int or pid<=0:return None
    try:
        raw=Path(f'/proc/{pid}/stat').read_text();fields=raw[raw.rfind(')')+2:].split()
        if fields[0]in{'Z','X'}:return None
        return {'pid':pid,'start_ticks':fields[19]}
    except(OSError,IndexError):return None
def _same_process(record:dict)->bool:
    current=_identity(record.get('pid'))
    return bool(current and current=={k:record.get(k)for k in current})
def _launch(directory:Path)->int:
    with(directory/'worker.log').open('xb')as log:
        process=subprocess.Popen([sys.executable,'-m','backend.analysis_jobs','worker',str(directory)],
            cwd=Path(__file__).resolve().parent.parent,stdin=subprocess.DEVNULL,stdout=log,
            stderr=subprocess.STDOUT,start_new_session=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        return process.pid
def _verify_completed(directory:Path,W:Path,meta:dict)->None:
    receipt=_read(directory/'artifact_receipt.json',directory);execution=_read(directory/'execution_receipt.json',directory)
    if(receipt['execution_receipt_sha256']!=_hash(directory/'execution_receipt.json',directory)
       or execution['source_sha256_before']!=meta['source_sha256']
       or execution['source_sha256_after']!=meta['source_sha256']
       or execution['result'].get('status')!='success'or execution['result'].get('exit_code')!=0):
        raise ValueError('Execution receipt integrity mismatch')
    output=W/meta['output_relative']
    if(_hash(output/'analysis_manifest.json',W)!=receipt['manifest_sha256']
       or _hash(output/meta['source_relative'],W)!=meta['source_sha256']
       or _hash(directory/'source.py',directory)!=meta['source_sha256']):
        raise ValueError('Manifest or executed source changed after completion')
    for artifact in receipt['validation']['artifacts']:
        path=artifact['path'];_agent()._required_artifact_contract([path])
        if _hash(output/path,W)!=artifact['sha256']:raise ValueError('An output changed after completion')
def status(workdir:Path,job_id:str)->dict:
    if not isinstance(job_id,str)or not re.fullmatch(r'[a-f0-9]{32}',job_id):raise ValueError('Invalid analysis job ID')
    root=_job_root(workdir);directory=root/job_id;_agent()._no_links(directory,root)
    meta=_read(directory/'job.json',directory);state=_read(directory/'state.json',directory)
    if state.get('status')in ACTIVE:
        try:launch=_read(directory/'launch.json',directory)
        except FileNotFoundError:launch={}
        if time.time()-meta['created']>15 and not _same_process(launch):
            state={**state,'status':'unknown_after_worker_exit','message':'No completion record. Inspect retained logs; no automatic restart.'}
    if state.get('status')=='completed':
        try:_verify_completed(directory,Path(workdir),meta)
        except(OSError,ValueError,KeyError,TypeError)as exc:
            state={**state,'status':'output_integrity_failed','message':str(exc),
                'validation':{**state.get('validation',{}),'valid':False,'passed':False,'errors':[str(exc)]}}
    public={k:state[k]for k in('status','message','started','finished','validation','execution','input_integrity')if k in state}
    prefix=meta['output_relative'];artifacts=[{**row,'path':prefix+'/'+row['path']}for row in(state.get('validation')or{}).get('artifacts',[])]
    try:current_sha=_hash(Path(workdir)/prefix/meta['source_relative'],Path(workdir))
    except(OSError,ValueError):current_sha=None
    matched=(state.get('execution')or{}).get('exit_code')==0 and current_sha==meta['source_sha256']
    return {'job_id':job_id,'source_path':meta['source_relative'],'source_sha256':meta['source_sha256'],
        'source_sha256_current':current_sha,'source_matches_executed_code':matched,
        'output_relative':prefix,'job_timeout_seconds':meta['timeout_seconds'],'provider_requests_in_worker':0,
        'artifacts':artifacts,**public}
def _stage_inventory(W:Path,artifacts:list[dict])->list[dict]:
    excluded={x['path']for x in artifacts}|{'analysis_manifest.json'};rows=[];total=0
    for p in sorted(W.rglob('*')):
        rel=p.relative_to(W)
        if(rel.parts[0]=='job_outputs'or any(x.startswith('.')for x in rel.parts)or p.is_symlink()or rel.as_posix()in excluded):continue
        if p.is_file():
            size=p.stat().st_size;total+=size
            if total>MAX_STAGE_BYTES or len(rows)>=2000:raise ValueError('Staging exceeds bounds; use readonly /inputs for original data')
            rows.append({'path':rel.as_posix(),'bytes':size,'sha256':_hash(p,W)})
    return rows
def submit(workdir:Path,input_roots:list[Path],source:Path,timeout_seconds:int,
           artifacts:list[dict],required:list[str],reserve:Callable[[],None],*,
           launcher:Callable[[Path],int]|None=None)->dict:
    if not enabled():raise ValueError('Background analysis jobs are not enabled by the operator')
    if type(timeout_seconds)is not int or not 1<=timeout_seconds<=MAX_JOB_SECONDS:
        raise ValueError(f'Background timeout must be an integer in1..{MAX_JOB_SECONDS}')
    W=Path(workdir).absolute();source=Path(source).absolute()
    if not source.is_relative_to(W)or source.suffix!='.py':raise ValueError('Submit generated Python beneath /work')
    raw=_agent()._read_regular(source,W,_agent().MAX_CODE_BYTES+1)
    if len(raw)>_agent().MAX_CODE_BYTES:raise ValueError('Generated Python is too large')
    compile(raw,str(source),'exec')
    from .analysis_validation import _RULES,_METADATA
    if not isinstance(artifacts,list)or not 1<=len(artifacts)<=32:raise ValueError('Declare the complete1..32 output artifact contract')
    for spec in artifacts:
        if not isinstance(spec,dict)or spec.get('kind')not in _RULES:raise ValueError('Unsupported job artifact declaration')
        if set(spec)-(_RULES[spec['kind']]|_METADATA):raise ValueError('Unsupported job artifact constraints')
        _agent()._required_artifact_contract([spec.get('path')])
    paths=[x['path']for x in artifacts]
    if len(set(paths))!=len(paths)or source.relative_to(W).as_posix()in paths:raise ValueError('Declare unique output paths separate from generated source')
    if not _agent()._required_artifact_coverage(required,artifacts)['complete']:raise ValueError('Declare all caller-required artifacts')
    root=_job_root(W)
    with(root/'.submission.lock').open('a+')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        snapshots=input_snapshot(input_roots);staged=_stage_inventory(W,artifacts)
        source_sha=hashlib.sha256(raw).hexdigest()
        signature=_digest({'source':source_sha,'inputs':snapshots,'staging':staged,'timeout':timeout_seconds,'artifacts':artifacts,'required':required})
        for old_dir in sorted(root.iterdir()):
            if not old_dir.is_dir()or not re.fullmatch(r'[a-f0-9]{32}',old_dir.name):continue
            old=_read(old_dir/'job.json',old_dir);current=status(W,old_dir.name)
            if old['signature']==signature:return {**current,'reused':True,'computed':current['status']=='completed'}
            if current['status']in ACTIVE|UNCERTAIN:raise ValueError('An active or unaccounted-for job already exists; inspect its recorded result')
        reserve();job_id=uuid.uuid4().hex;directory=root/job_id;directory.mkdir(mode=0o700)
        output=W/'job_outputs'/job_id
        meta={'schema_version':'primatex.analysis_job.v1','job_id':job_id,'created':time.time(),'workdir':str(W),
            'output_relative':output.relative_to(W).as_posix(),'source_relative':source.relative_to(W).as_posix(),
            'source_sha256':source_sha,'input_roots':[str(x)for x in input_roots],'inputs_sha256':_digest(snapshots),
            'timeout_seconds':timeout_seconds,'artifacts':artifacts,'required_artifacts':required,'signature':signature,
            'staged_files':staged,'staged_bytes':sum(x['bytes']for x in staged),'declared_outputs_inherited':False,
            'budget_scope':'Separate bounded compute job; foreground budgets and cumulative provider ledger unchanged.'}
        _write(directory/'job.json',directory,meta)
        _write(directory/'state.json',directory,{'status':'preparing','message':'Freezing job inputs and code'})
        try:
            _agent()._no_links(output,W);output.mkdir(parents=True,exist_ok=False)
            for row in staged:
                original=W/row['path'];target=output/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(original,target)
                if _hash(target,output)!=row['sha256']:raise ValueError('A staging file changed during submission')
            frozen=directory/'source.py';frozen.write_bytes(raw);frozen.chmod(0o400)
            if _hash(output/meta['source_relative'],output)!=source_sha:raise ValueError('Staged source differs from submitted code')
            _write(directory/'inputs.json',directory,{'files':snapshots})
            _write(directory/'state.json',directory,{'status':'queued','message':'Submitted, not computed or validated'})
            pid=(launcher or _launch)(directory)
            _write(directory/'launch.json',directory,{**(_identity(pid)or{'pid':pid}),'time':time.time()})
        except Exception as exc:
            _write(directory/'state.json',directory,{'status':'failed','finished':time.time(),'message':'Job preparation/launch failed: '+str(exc)[:800]})
        return {**status(W,job_id),'reused':False,'computed':False}
class JobCancelled(Exception):pass
def cancel(workdir:Path,job_id:str)->dict:
    current=status(workdir,job_id)
    if current['status']not in ACTIVE:return current
    directory=_job_root(workdir)/job_id
    _write(directory/'cancel_requested.json',directory,{'requested':time.time()})
    try:launch=_read(directory/'launch.json',directory)
    except FileNotFoundError:launch={}
    if _same_process(launch):os.kill(launch['pid'],signal.SIGTERM)
    return {**status(workdir,job_id),'cancel_requested':True}
def worker(directory:Path,*,executor_factory=None)->dict:
    from .analysis_executor import SandboxExecutor
    from .analysis_finalization import derive_manifest
    from .analysis_validation import ArtifactValidator,MANIFEST_NAME
    directory=Path(directory).absolute();meta=_read(directory/'job.json',directory);W=Path(meta['workdir'])
    if directory!=_job_root(W)/meta['job_id']:raise ValueError('Worker metadata location mismatch')
    with(directory/'.worker.lock').open('a+')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        previous=_read(directory/'state.json',directory)
        if previous['status']not in{'queued','running'}:return previous
        output=W/meta['output_relative'];_agent()._no_links(output,W)
        state={'status':'running','started':time.time(),'message':'Real isolated computation in progress'}
        _write(directory/'state.json',directory,state)
        old_handler=None
        if threading.current_thread()is threading.main_thread():
            old_handler=signal.getsignal(signal.SIGTERM)
            def interrupted(signum,frame):raise JobCancelled('Cancelled by the authenticated owner')
            signal.signal(signal.SIGTERM,interrupted)
        try:
            if(directory/'cancel_requested.json').exists():raise JobCancelled('Cancelled before execution')
            roots=[Path(x)for x in meta['input_roots']]
            if _digest(input_snapshot(roots))!=meta['inputs_sha256']:raise ValueError('Inputs changed after submission')
            snapshot=directory/'source.py';before=_hash(snapshot,directory)
            if before!=meta['source_sha256']:raise ValueError('Frozen source integrity mismatch')
            script=output/meta['source_relative']
            if _hash(script,output)!=before:raise ValueError('Staged source differs from submitted code')
            executor=(executor_factory or SandboxExecutor)(output,roots)
            result=executor.run(script,timeout_seconds=meta['timeout_seconds'],frozen_source=snapshot)
            after=_hash(snapshot,directory)
            execution={'schema_version':'primatex.analysis_job_execution.v1','job_id':meta['job_id'],'timestamp':time.time(),
                'source_relative':meta['source_relative'],'source_sha256_before':before,'source_sha256_after':after,
                'source_is_readonly_bind':True,'result':result}
            _write(directory/'execution_receipt.json',directory,execution)
            state.update(status='verifying',execution=result);_write(directory/'state.json',directory,state)
            if result.get('status')!='success'or result.get('exit_code')!=0 or before!=after:raise ValueError('Execution did not finish successfully with unchanged source')
            if _digest(input_snapshot(roots))!=meta['inputs_sha256']:raise ValueError('Source inputs changed during computation')
            state['input_integrity']={'unchanged':True,'digest':meta['inputs_sha256']}
            old=output/MANIFEST_NAME;_agent()._no_links(old,output)
            if old.exists():old.rename(output/('.previous-job-manifest-'+uuid.uuid4().hex+'.json'))
            manifest,observations=derive_manifest(output,meta['artifacts']);content=json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)
            _agent()._write_regular(output/MANIFEST_NAME,output,content)
            validation=ArtifactValidator().validate(output)
            coverage=_agent()._required_artifact_coverage(meta['required_artifacts'],validation.get('artifacts',[]))
            validation.update(required_artifact_coverage=coverage,independent_numeric_status='not_performed',scientific_status='not_evaluated')
            valid=validation.get('valid')is True and coverage['complete'];validation['valid']=validation['passed']=valid
            _write(directory/'artifact_receipt.json',directory,{'schema_version':'primatex.analysis_job_artifacts.v1',
                'job_id':meta['job_id'],'execution_receipt_sha256':_hash(directory/'execution_receipt.json',directory),
                'manifest_sha256':hashlib.sha256(content.encode()).hexdigest(),'supplied_constraints':meta['artifacts'],
                'observations':observations,'validation':validation})
            state.update(status='completed'if valid else'failed',validation=validation,
                message='Computation/file checks complete; independent numerical/scientific review not performed.'if valid else'Declared outputs failed file/coverage checks')
        except JobCancelled as exc:state.update(status='cancelled',message=str(exc))
        except Exception as exc:state.update(status='failed',message=str(exc)[:1600])
        finally:
            if old_handler is not None:signal.signal(signal.SIGTERM,old_handler)
        state['finished']=time.time();_write(directory/'state.json',directory,state);return state
if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='worker':raise SystemExit('Use trusted worker entrypoint')
    worker(Path(sys.argv[2]))