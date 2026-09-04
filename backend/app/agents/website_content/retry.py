"""Retrying a flaky model call.

Lives on its own rather than inside pipeline.py because both the pipeline and the
refinement loop need it, and refine.py cannot import pipeline.py -- pipeline
imports refine.

Same helper, same reasoning, as app.agents.blog_generation.pipeline._with_retry:
transient network blips to the model APIs happen in this environment and succeed
on a retry. Observed during a live run, when a single dropped connection to
Anthropic took out two sections' refinement loops at the same instant.

A missing key, a refusal or a dead dependency will not fix itself on a retry and
raises immediately. A structured-output schema mismatch is the exception: that is
one bad reply, and asking again usually gets a valid one -- client.structured_llm
flags those `retryable`.
"""

import time

from app.errors import UpstreamServiceError

MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.5


def with_retry(func, *args, **kwargs):
    """Calls func, retrying transient failures up to MAX_ATTEMPTS times."""
    last_exc: Exception = RuntimeError("with_retry called with zero attempts")
    for attempt in range(MAX_ATTEMPTS):
        try:
            return func(*args, **kwargs)
        except UpstreamServiceError as exc:
            if not getattr(exc, "retryable", False) and not _is_transient(exc):
                raise
            last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS)
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY_SECONDS)
    raise last_exc


def _is_transient(exc: UpstreamServiceError) -> bool:
    """True when the model was never reached, as opposed to answering badly.

    text_llm raises a plain (non-retryable) UpstreamServiceError for any call
    that threw, which lumps "the network dropped" in with "the model refused".
    Only the first is worth retrying, and the internal detail is what separates
    them -- client.is_connection_error walks the same exception names.
    """
    internal = (getattr(exc, "internal", None) or "").lower()
    return any(
        token in internal
        for token in ("connection", "timeout", "network", "dns", "getaddrinfo")
    )
