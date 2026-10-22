"""Server-controlled coding profiles shared by the API and research entrypoints."""
from __future__ import annotations
import os
from urllib.parse import urlsplit


def bounded_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (ValueError, TypeError):
        raise ValueError(name + ' must be a bounded integer') from None
    if not minimum <= value <= maximum:
        raise ValueError(name + ' is outside its supported bounds')
    return value


def coding_model_options(model: str, base_url: str) -> dict:
    url = urlsplit(base_url)
    confirmed_provider = (url.scheme == 'https' and url.hostname == 'inferaiapi.com'
                          and url.port in (None, 443) and url.path.rstrip('/') == '/v1'
                          and not url.username and not url.password and not url.query
                          and not url.fragment)
    confirmed_model = model.lower().startswith('deepseek-v4')
    confirmed = confirmed_provider and confirmed_model
    options = {
        'timeout': bounded_setting('ANALYSIS_MODEL_TIMEOUT_SECONDS', 150 if confirmed else 60, 30, 300),
        'max_retries': 0,
        'max_tokens': bounded_setting('ANALYSIS_MODEL_MAX_TOKENS', 20000 if confirmed else 4096, 1024, 32768),
    }
    # This provider/model combination was tested with real calls. Do not send a
    # provider-specific extension to unverified providers or unrelated models.
    # The confirmed gateway rejects the thinking extension. Omit it before
    # the first HTTP request; no compatibility retry is needed for this field.
    return options
