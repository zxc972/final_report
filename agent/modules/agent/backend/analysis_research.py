"""Bounded source/graph evidence retrieval; candidate evidence never authorizes analysis."""
from __future__ import annotations
import hashlib,json,os,subprocess,threading
from pathlib import Path
from typing import Any
import collections
import math
import re
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

    def _source_documents(self) -> list[dict[str, Any]]:
        """Read only registered parents; never reinterpret a graph node as source text."""
        self._verify()
        documents = json.loads(self._bytes("documents.json", 24 * 1024 * 1024))
        if not isinstance(documents, list):
            raise ValueError("Invalid registered parent catalogue")
        seen = set()
        for document in documents:
            identifier = document.get("id")
            if (
                not isinstance(identifier, str)
                or not 1 <= len(identifier) <= 200
                or identifier in seen
                or not isinstance(document.get("text"), str)
                or not isinstance(document.get("url"), str)
            ):
                raise ValueError("Invalid or duplicate original parent")
            seen.add(identifier)
            digest = hashlib.sha256(document["text"].encode()).hexdigest()
            if digest != document.get("text_sha256"):
                raise ValueError("Original parent text digest mismatch")
        return documents

    @staticmethod
    def _text_tokens(text: str) -> list[str]:
        base = re.findall(r"[a-z][a-z0-9_]*|\d+", text.lower())
        return base + [
            part for word in base if "_" in word
            for part in word.split("_") if part
        ]

    def search_text(self, query: str, limit: int = 5) -> dict[str, Any]:
        """Reuse the registered worker's parent lexical scoring, without naive/mix calls.

        This is a text-only lexical baseline, not native LightRAG naive. No model,
        storage initialization, indexing or subprocess is needed for this search.
        Prefer explicit software and English technical entrypoint terms.
        """
        if not isinstance(query, str) or not 1 <= len(query) <= 1000:
            raise ValueError("A bounded nonempty research query is required")
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("Research limit must be an integer from 1 to 8")
        documents = self._source_documents()
        words = set(self._text_tokens(query))
        frequencies = collections.Counter()
        counts = {}
        for document in documents:
            terms = self._text_tokens(
                document["id"] + " " + document.get("heading", "") + " " + document["text"]
            )
            counts[document["id"]] = collections.Counter(terms)
            frequencies.update(set(terms))
        ranked = []
        for document in documents:
            terms = counts[document["id"]]
            score = sum(
                (1 + math.log(terms[word]))
                * math.log(1 + len(documents) / (1 + frequencies[word]))
                for word in words if terms[word]
            )
            if score:
                ranked.append((score, document["id"], document))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        sources = []
        for score, identifier, document in ranked[:limit]:
            text = document["text"]
            matches = [
                match.start() for match in re.finditer(r"[a-z][a-z0-9_]*", text.lower())
                if match.group() in words
            ]
            start = max(0, (matches[0] if matches else 0) - 180)
            end = min(len(text), start + 1400)
            sources.append({
                "source_id": identifier, "source_url": document["url"],
                "heading": document.get("heading"),
                "source_scope": document.get("source_scope"),
                "score": score, "text_sha256": document["text_sha256"],
                "excerpt": {
                    "text": text[start:end], "start_char": start, "end_char": end,
                    "truncated": start > 0 or end < len(text),
                },
            })
        return {
            "status": "ok", "route": "registered_parent_text_lexical_only",
            "sources": sources, "release_sha256": self.release_sha256,
            "retrieval_provider_http_calls": 0, "native_graph_calls": 0,
            "executable": False, "scientific_status": "not_evaluated",
        }

    def read_text(
        self, source_id: str, start_char: int = 0, max_chars: int = 8000,
    ) -> dict[str, Any]:
        documents = {document["id"]: document for document in self._source_documents()}
        if not isinstance(source_id, str) or source_id not in documents:
            raise ValueError("Unknown registered original parent ID")
        # Existing read protocol verifies the original bytes and bounded cursor.
        result = self.read(source_id, start_char, max_chars)
        if result.get("id") != source_id or not isinstance(result.get("text"), str):
            raise ValueError("Original source read returned an invalid response")
        result["heading"] = documents[source_id].get("heading")
        return result
