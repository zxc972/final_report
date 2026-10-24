"""Four internal-review attempt credits inside the existing global budget.

Coding cannot borrow the review allocation. Protocol retries use new logical
calls; every actual provider HTTP attempt, including transport/compat retries,
also consumes the same four-credit pool. Native logical/HTTP meters are retained.
"""
from contextlib import contextmanager
from contextvars import ContextVar
RESERVED_REVIEW_ATTEMPTS=4
ACTIVE_REVIEW_BUDGET=ContextVar('primatex_review_attempt_budget',default=None)

class ReviewBudgetExceeded(RuntimeError):
    pass

class AgentBudgetExceeded(RuntimeError):
    pass

class ReviewBudget:
    def __init__(self,tools):
        self.tools=tools
        saved=tools.control_store.latest('review_budget') if tools.control_store else None
        record=saved['record'] if saved else {}
        self.logical=record.get('review_logical_calls',0)
        self.http=record.get('review_http_attempts',0)
    @property
    def enabled(self):
        return self.tools.session is not None and getattr(self.tools,'_internal_review_model',None) is not None
    @property
    def maximum(self):
        from .analysis_agent import MAX_MODEL_CALLS
        return MAX_MODEL_CALLS
    @property
    def reserve(self):return min(RESERVED_REVIEW_ATTEMPTS,max(0,self.maximum-1)) if self.enabled else 0
    @property
    def nonreview(self):return max(0,self.tools.model_calls-self.logical)
    def before(self,review=False):
        if not self.enabled:return
        if review and max(self.logical,self.http)>=self.reserve:
            raise ReviewBudgetExceeded('Internal review reservation exhausted; no further review or transport retry is authorized')
        if not review and self.nonreview>=self.maximum-self.reserve:
            raise AgentBudgetExceeded('Agent model budget exhausted; the internal-review reservation cannot be used for coding or repair')
    def after(self,review=False):
        if self.enabled and review:self.logical+=1
        self.persist()
    def consume_http(self):
        with self.tools._lock:
            if self.http>=self.reserve:raise ReviewBudgetExceeded('Internal review HTTP attempt reservation exhausted before native charge/send')
            self.http+=1;self.persist()
    def snapshot(self):
        return {'enabled':self.enabled,'total_logical_limit':self.maximum,'review_reserved_attempts':self.reserve,
                'nonreview_limit':self.maximum-self.reserve,'nonreview_model_calls':self.nonreview,
                'review_logical_calls':self.logical,'review_http_attempts':self.http,
                'review_credits_used':max(self.logical,self.http),
                'review_credits_remaining':max(0,self.reserve-max(self.logical,self.http)),
                'budget_units_used':self.nonreview+max(self.logical,self.http),
                'transport_retries_charge_review_pool':True,'native_logical_http_counters_not_reset':True}
    def persist(self):
        if self.tools.control_store:self.tools.control_store.save('review_budget',self.snapshot())

def get(tools):
    value=getattr(tools,'_review_budget',None)
    if value is None:value=tools._review_budget=ReviewBudget(tools)
    return value

@contextmanager
def review_scope(tools):
    budget=get(tools);token=ACTIVE_REVIEW_BUDGET.set(budget if budget.enabled else None)
    try:yield
    finally:ACTIVE_REVIEW_BUDGET.reset(token)

def reserve_http_attempt():
    budget=ACTIVE_REVIEW_BUDGET.get()
    if budget is not None:budget.consume_http()

def coding_available(tools):
    budget=get(tools)
    return tools.model_calls<budget.maximum and (not budget.enabled or budget.nonreview<budget.maximum-budget.reserve)

def notice(tools):
    b=get(tools)
    if not b.enabled:return ''
    return f'Model budget: non-review {b.nonreview}/{b.maximum-b.reserve} including the router. {b.reserve} internal-review attempt credits are protected within the total {b.maximum}; coding/repair cannot borrow them. Finish execution and reporting before the non-review allowance is exhausted.'
