"""Typed errors for the things outside this app that can fail.

Every one of these carries a message that is safe to show a user verbatim: the
handlers in app.main turn them into a JSON body the frontend renders as-is, so
they must never contain a key, a connection string, or a raw driver traceback.
Put the diagnostic detail in `internal` instead — it is logged, never returned.
"""

from typing import Optional


class AppError(Exception):
    """Base for errors we deliberately surface to the frontend."""

    status_code = 500
    message = "Something went wrong. Please try again."

    def __init__(self, message: Optional[str] = None, *, internal: Optional[str] = None):
        self.message = message or self.message
        self.internal = internal
        super().__init__(self.message)


class UpstreamServiceError(AppError):
    """A third-party service we depend on failed or was unreachable.

    502 rather than 500: the request itself was fine, the dependency wasn't.
    `service` names it in the log so an outage is obvious without a traceback.
    """

    status_code = 502

    def __init__(
        self,
        service: str,
        message: Optional[str] = None,
        *,
        internal: Optional[str] = None,
    ):
        self.service = service
        super().__init__(
            message or f"{service} didn't respond. Please try again in a moment.",
            internal=internal,
        )


class AlreadyInProgressError(AppError):
    """The same job is already running for this request.

    409: the request is well-formed, but a duplicate would race the one
    already in flight - two overlapping runs both delete-and-replace the
    same rows, so whichever finishes first just gets overwritten, and any
    paid API calls it made were wasted.
    """

    status_code = 409

    def __init__(self, service: str, *, internal: Optional[str] = None):
        self.service = service
        super().__init__(
            f"{service} is already running for this request. Please wait for it to finish.",
            internal=internal,
        )


class ServiceNotConfiguredError(AppError):
    """A required environment variable is missing, so a feature can't run.

    503 because it's a deployment problem, not something the user did wrong —
    and unlike an outage, retrying won't help until someone sets the env var.
    """

    status_code = 503

    def __init__(self, service: str, *, internal: Optional[str] = None):
        self.service = service
        super().__init__(
            f"{service} is not configured on the server. Please contact support.",
            internal=internal,
        )
