"""Identity-confined downloads of real generated analysis files.

Does not weaken the general file browser's hidden-file policy. Credentials,
checkpoints and protected receipts remain outside each downloadable run.
"""
from __future__ import annotations
import hashlib,re
from pathlib import Path
from typing import Any
from pydantic import BaseModel,Field
MAX_DOWNLOAD_BYTES=64*1024*1024
class AnalysisFileRequest(BaseModel):
    conversation_id:str=Field(alias='conversationId',min_length=1,max_length=256)
    run_id:str=Field(alias='runId',pattern=r'^[0-9a-f]{32}$')
    path:str=Field(min_length=1,max_length=1024)
    context:dict[str,Any]=Field(default_factory=dict)

def read_analysis_file(workspace:Path,user_id:str,conversation_id:str,run_id:str,relative_path:str)->tuple[bytes,str]:
    """Read a single regular nonhidden file using descriptor-confined opens.

    The server recomputes owner/conversation/run location; caller paths cannot
    choose a host directory. Original inputs and other conversations are absent.
    Successful download is not file validation or scientific review.
    """
    from .analysis_agent import _read_regular
    if not re.fullmatch(r'[0-9a-f]{32}',run_id):raise ValueError('Invalid analysis run ID')
    parts=relative_path.split('/')
    if (any(p in ('','.','..')or p.startswith('.')for p in parts)
        or any(c in relative_path for c in ('\\',':','\x00','\r','\n'))):
        raise ValueError('Use a relative nonhidden output filename')
    owner_conversation=hashlib.sha256((user_id+'\x00'+conversation_id).encode()).hexdigest()[:32]
    path=Path(workspace)/'.analysis_runs'/owner_conversation/run_id/relative_path
    # Anchored at the approved workspace. O_NOFOLLOW applies at every component,
    # O_NONBLOCK + fstat rejects FIFOs/devices, and size is bounded before response.
    data=_read_regular(path,Path(workspace),MAX_DOWNLOAD_BYTES+1)
    if len(data)>MAX_DOWNLOAD_BYTES:raise OverflowError('Analysis file exceeds the bounded download limit')
    return data,parts[-1]


def list_generated_scripts(workspace:Path,user_id:str,conversation_id:str,run_id:str)->list[dict]:
    """Expose source filenames from protected execution receipts, never their private paths."""
    from .analysis_agent import _read_regular
    import json
    if not isinstance(run_id,str)or not re.fullmatch(r'[0-9a-f]{32}',run_id):return []
    digest=hashlib.sha256((user_id+'\x00'+conversation_id).encode()).hexdigest()[:32]
    root=Path(workspace)/'.analysis_runs'/digest
    receipts=root/'.execution_receipts'/run_id
    grouped={}
    for p in sorted(receipts.glob('*.json'))[:64]:
        try:
            receipt=json.loads(_read_regular(p,Path(workspace),65537))
            if not isinstance(receipt,dict):continue
            path=receipt.get('script','')
            if not isinstance(path,str)or not path.startswith('/work/'):continue
            path=path[len('/work/'):]
            current,_=read_analysis_file(workspace,user_id,conversation_id,run_id,path)
            sha=hashlib.sha256(current).hexdigest()
            item=grouped.setdefault(path,{'path':path,'sha256_current':sha,'matches_executed_code':False,'executions':[]})
            item['matches_executed_code']|=sha==receipt.get('script_sha256_before')==receipt.get('script_sha256_after')
            result=receipt.get('result',{})
            if not isinstance(result,dict):result={}
            item['executions'].append({'status':result.get('status'),'exit_code':result.get('exit_code'),'sha256_executed':receipt.get('script_sha256_before')})
        except (OSError,ValueError,OverflowError,TypeError):continue
    return list(grouped.values())


class AnalysisJobStatusRequest(BaseModel):
    conversation_id:str=Field(alias="conversationId",min_length=1,max_length=256)
    run_id:str=Field(alias="runId",pattern=r"^[0-9a-f]{32}$")
    job_id:str=Field(alias="jobId",pattern=r"^[0-9a-f]{32}$")
    context:dict[str,Any]=Field(default_factory=dict)
