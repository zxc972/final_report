"""Bounded source/graph evidence retrieval; candidate evidence never authorizes analysis."""
from __future__ import annotations
import hashlib,json,os,subprocess,threading
from pathlib import Path
from typing import Any
_RESEARCH_LOCK=threading.Lock()
class ResearchEvidenceRetriever:
    def __init__(self,root:Path):
        original=Path(root)
        if original.is_symlink():raise ValueError('Research root must not be a symlink')
        self.root=original.resolve(strict=True)
        if not self.root.is_dir():raise ValueError('Research root must be a directory')
        config=self._bytes('config.json',2*1024*1024)
        self.config=json.loads(config)
        if self.config.get('schema')!='primatex.research_retrieval.v1':raise ValueError('Unknown research evidence protocol')
        self.python=Path(self.config['python'])
        if not self.python.is_absolute() or not self.python.is_file():raise ValueError('Registered Python runtime unavailable')
        self.release_sha256=hashlib.sha256(config).hexdigest()
        self._verify()
    def _bytes(self,name:str,limit:int)->bytes:
        p=self.root/name
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(self.root) or p.stat().st_size>limit:raise ValueError('Invalid bounded research release file')
        return p.read_bytes()
    def _verify(self):
        for name,key,limit in [('worker.py','worker_sha256',200000),('documents.json','documents_sha256',24*1024*1024),('domain_graph.json','domain_graph_sha256',24*1024*1024)]:
            if hashlib.sha256(self._bytes(name,limit)).hexdigest()!=self.config[key]:raise ValueError('Research evidence release digest mismatch')
    def _invoke(self,payload:dict[str,Any])->dict[str,Any]:
        self._verify()
        env={'PATH':os.defpath,'HOME':os.environ.get('HOME','/tmp'),'HF_HUB_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false','OMP_NUM_THREADS':'2','LANG':'C.UTF-8'}
        with _RESEARCH_LOCK:
            proc=subprocess.run([str(self.python),str(self.root/'worker.py')],input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=75,env=env)
        if len(proc.stdout.encode())>120000:raise ValueError('Research evidence response exceeds bounds')
        # Library diagnostics may precede the worker protocol line; only that final JSON is used.
        lines=[line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:raise ValueError('Research worker returned no response')
        try:result=json.loads(lines[-1])
        except ValueError:raise ValueError('Research worker returned invalid JSON') from None
        if not isinstance(result,dict) or proc.returncode or result.get('status')!='ok':
            raise ValueError('Research retrieval failed: '+str(result.get('error_type','worker_error')))
        result['release_sha256']=self.release_sha256
        result['retrieval_provider_http_calls']=0
        result['runtime_version_binding']='Source snapshots only; applicability and installed versions must be checked'
        return result
    def search(self,query:str,limit:int=5,high_level_keywords:list[str]|None=None,low_level_keywords:list[str]|None=None)->dict[str,Any]:
        if not isinstance(query,str) or not 1<=len(query)<=1000 or type(limit)is not int or not 1<=limit<=8:raise ValueError('Bounded nonempty research query and limit 1..8 required')
        for terms in [high_level_keywords,low_level_keywords]:
            if terms is not None and (not isinstance(terms,list) or len(terms)>8 or any(not isinstance(t,str) or not 1<=len(t)<=150 for t in terms)):raise ValueError('Invalid bounded keyword list')
        return self._invoke({'operation':'search','query':query,'limit':limit,'high_level_keywords':high_level_keywords or [query],'low_level_keywords':low_level_keywords or [query]})
    def read(self,source_id:str,start_char:int=0,max_chars:int=8000)->dict[str,Any]:
        if not isinstance(source_id,str) or not 1<=len(source_id)<=200 or type(start_char)is not int or start_char<0 or type(max_chars)is not int or not 100<=max_chars<=12000:raise ValueError('Invalid registered source read')
        if '/' in source_id or '\\' in source_id or '\x00' in source_id:raise ValueError('Use a registered source or graph node ID, never a path')
        return self._invoke({'operation':'read','source_id':source_id,'start_char':start_char,'max_chars':max_chars})
