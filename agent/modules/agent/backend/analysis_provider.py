"""Narrow, bounded compatibility fallback for optional provider fields.

Only explicit HTTP400 unknown/unsupported thinking is eligible. Other bad
requests, auth/rate/context errors propagate unchanged. Every retry still passes
through the configured audited HTTP client. No scientific output is repaired.
"""
from __future__ import annotations
import threading,warnings
from typing import Any
from pydantic import PrivateAttr
from openai import BadRequestError
from langchain_openai import ChatOpenAI

def unsupported_thinking(error:Exception)->bool:
    if not isinstance(error,BadRequestError):return False
    body=getattr(error,'body',None)
    if not isinstance(body,dict):return False
    detail=body.get('error',body)
    if not isinstance(detail,dict):return False
    message=str(detail.get('message','')).lower();param=str(detail.get('param','')).lower()
    named=param=='thinking'or '"thinking"'in message or "'thinking'"in message
    return named and any(x in message for x in ('unknown_parameter','unknown field','unsupported parameter','unrecognized request argument'))

class CompatibleChatOpenAI(ChatOpenAI):
    _compat_lock:Any=PrivateAttr(default_factory=threading.RLock)
    _thinking_removed:bool=PrivateAttr(default=False)
    def _remove_rejected_thinking(self,error:Exception)->bool:
        if self.streaming or not unsupported_thinking(error):return False
        with self._compat_lock:
            if self._thinking_removed or not isinstance(self.extra_body,dict)or 'thinking'not in self.extra_body:return False
            body=dict(self.extra_body);body.pop('thinking');self.extra_body=body or None;self._thinking_removed=True
            warnings.warn('Gateway explicitly rejected optional thinking; one retry omits only that field. Original HTTP error remains auditable.',RuntimeWarning,stacklevel=2)
            return True
    def _mark(self,result:Any,retried:bool)->Any:
        if self._thinking_removed:
            for generation in result.generations:
                generation.message.response_metadata={**generation.message.response_metadata,
                    'provider_compatibility':{'omitted_optional_fields':['thinking'],'reason':'explicit upstream unknown parameter','retry_in_this_call':retried}}
        return result
    def _generate(self,messages,stop=None,run_manager=None,**kwargs):
        retried=False
        try:result=super()._generate(messages,stop=stop,run_manager=run_manager,**kwargs)
        except BadRequestError as exc:
            if not self._remove_rejected_thinking(exc):raise
            retried=True;result=super()._generate(messages,stop=stop,run_manager=run_manager,**kwargs)
        return self._mark(result,retried)
    async def _agenerate(self,messages,stop=None,run_manager=None,**kwargs):
        retried=False
        try:result=await super()._agenerate(messages,stop=stop,run_manager=run_manager,**kwargs)
        except BadRequestError as exc:
            if not self._remove_rejected_thinking(exc):raise
            retried=True;result=await super()._agenerate(messages,stop=stop,run_manager=run_manager,**kwargs)
        return self._mark(result,retried)
