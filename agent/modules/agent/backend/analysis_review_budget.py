"""Disjoint coding/review/revision logical pools; HTTP retries remain metered."""
from contextlib import contextmanager
from contextvars import ContextVar

RESERVED_REVIEW_ATTEMPTS = 4
RESERVED_REVISION_CALLS = 3
MAX_REVIEW_HTTP_PER_LOGICAL = 3
ACTIVE_REVIEW_BUDGET = ContextVar('primatex_review_attempt_budget', default=None)


class ReviewBudgetExceeded(RuntimeError):
    pass


class AgentBudgetExceeded(RuntimeError):
    pass


class ReviewBudget:
    def __init__(self, tools):
        self.tools = tools
        saved = tools.control_store.latest('review_budget') if tools.control_store else None
        record = saved['record'] if saved else {}
        self.logical = record.get('review_logical_calls', 0)
        self.http = record.get('review_http_attempts', 0)
        self.revision = record.get('revision_model_calls', 0)
        self.revision_open = record.get('revision_authorized', False)
        self.authorizations = list(record.get('revision_authorization_ids', []))
        self.http_by_logical = list(record.get('review_http_by_logical', []))

    @property
    def enabled(self):
        return self.tools.session is not None and getattr(self.tools, '_internal_review_model', None) is not None

    @property
    def maximum(self):
        from .analysis_agent import MAX_MODEL_CALLS
        return MAX_MODEL_CALLS

    @property
    def reserve(self):
        return min(RESERVED_REVIEW_ATTEMPTS, max(0, self.maximum - 1)) if self.enabled else 0

    @property
    def revision_reserve(self):
        return min(RESERVED_REVISION_CALLS, max(0, self.maximum - self.reserve - 1)) if self.enabled else 0

    @property
    def initial_limit(self):
        return self.maximum - self.reserve - self.revision_reserve

    @property
    def nonreview(self):
        return max(0, self.tools.model_calls - self.logical)

    @property
    def initial(self):
        return max(0, self.nonreview - self.revision)

    def before(self, review=False):
        if not self.enabled:
            return
        if review:
            if self.logical >= self.reserve:
                raise ReviewBudgetExceeded('Protected review logical allowance exhausted')
        elif self.revision_open:
            if self.revision >= self.revision_reserve:
                raise AgentBudgetExceeded('Protected post-review revision allowance exhausted')
        elif self.initial >= self.initial_limit:
            raise AgentBudgetExceeded('Initial coding allowance exhausted; review and revision reservations cannot be borrowed')

    def after(self, review=False):
        if self.enabled:
            if review:
                self.logical += 1
                self.http_by_logical.append(0)
            elif self.revision_open:
                self.revision += 1
        self.persist()

    def authorize_revision(self, review):
        if review.get('decision') != 'revise' or review.get('protocol_valid') is not True:
            raise ValueError('Revision reservation requires a valid revise decision')
        self.revision_open = True
        identity = review.get('review_id')
        if identity and identity not in self.authorizations:
            self.authorizations.append(identity)
        # Repeated revise decisions never replenish the three reserved calls.
        self.persist()

    def consume_http(self, retry_of=None):
        # Provider compatibility fallbacks/direct calls still require a logical
        # review charge. Ordinary retries reuse the existing native logical ID.
        if not retry_of and (not self.http_by_logical or self.http_by_logical[-1]):
            self.tools._tick(model=True, review=True)
        with self.tools._lock:
            if not self.http_by_logical:
                raise ReviewBudgetExceeded('No logical review reservation')
            if self.http_by_logical[-1] >= MAX_REVIEW_HTTP_PER_LOGICAL:
                raise ReviewBudgetExceeded('At most two transport retries per review logical call')
            self.http_by_logical[-1] += 1
            self.http += 1
            self.persist()

    def snapshot(self):
        return {'enabled': self.enabled, 'total_logical_limit': self.maximum,
                'review_reserved_attempts': self.reserve,
                'revision_reserved_calls': self.revision_reserve,
                'initial_coding_limit': self.initial_limit,
                'initial_coding_model_calls': self.initial,
                'nonreview_limit': self.maximum - self.reserve,
                'nonreview_model_calls': self.nonreview,
                'review_logical_calls': self.logical, 'review_http_attempts': self.http,
                'review_http_by_logical': list(self.http_by_logical),
                'review_transport_retries_maximum': MAX_REVIEW_HTTP_PER_LOGICAL - 1,
                'review_credits_used': self.logical,
                'review_credits_remaining': max(0, self.reserve - self.logical),
                'revision_model_calls': self.revision,
                'revision_credits_remaining': max(0, self.revision_reserve - self.revision),
                'revision_authorized': self.revision_open,
                'revision_authorization_ids': list(self.authorizations),
                'budget_units_used': self.tools.model_calls,
                'transport_retries_charge_review_pool': False,
                'native_logical_http_counters_not_reset': True}

    def persist(self):
        if self.tools.control_store:
            self.tools.control_store.save('review_budget', self.snapshot())


def get(tools):
    value = getattr(tools, '_review_budget', None)
    if value is None:
        value = tools._review_budget = ReviewBudget(tools)
    return value


@contextmanager
def review_scope(tools):
    budget = get(tools)
    from .analysis_transport import TRANSPORT_RETRY_LIMIT
    token = ACTIVE_REVIEW_BUDGET.set(budget if budget.enabled else None)
    retry_token = TRANSPORT_RETRY_LIMIT.set(2 if budget.enabled else TRANSPORT_RETRY_LIMIT.get())
    try:
        yield
    finally:
        TRANSPORT_RETRY_LIMIT.reset(retry_token)
        ACTIVE_REVIEW_BUDGET.reset(token)


def reserve_http_attempt(retry_of=None):
    budget = ACTIVE_REVIEW_BUDGET.get()
    if budget is not None:
        budget.consume_http(retry_of)


def coding_available(tools):
    budget = get(tools)
    if tools.model_calls >= budget.maximum:
        return False
    if not budget.enabled:
        return True
    return budget.revision < budget.revision_reserve if budget.revision_open else budget.initial < budget.initial_limit


def revision_available(tools):
    budget = get(tools)
    return budget.enabled and budget.revision_open and budget.revision < budget.revision_reserve


def notice(tools):
    b = get(tools)
    if not b.enabled:
        return ''
    return (f'Logical budget {b.maximum}: initial coding {b.initial}/{b.initial_limit}; '
            f'review {b.logical}/{b.reserve}; post-review revision {b.revision}/{b.revision_reserve} '
            f'(unlocked={b.revision_open}). Pools cannot be borrowed. '
            'Only a valid revise unlocks revision calls. Review transport retries are independently metered, at most two per logical call.')
