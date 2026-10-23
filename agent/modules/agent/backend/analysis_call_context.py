"""Actual provider-call provenance; checkpoint resumes enter this scope again."""

from contextlib import contextmanager
from contextvars import ContextVar

MODEL_SOURCE = ContextVar("primatex_model_source_node", default=None)
HTTP_ATTEMPT = ContextVar("primatex_native_http_attempt", default=None)


@contextmanager
def model_source(node):
    token = MODEL_SOURCE.set(node)
    try:
        yield
    finally:
        MODEL_SOURCE.reset(token)


def source_node(default="analysis.direct"):
    return MODEL_SOURCE.get() or default
