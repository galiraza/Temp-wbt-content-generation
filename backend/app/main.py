import hmac
import logging
import uuid

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.config import API_KEY, CORS_ALLOW_ORIGINS
from app.errors import AppError
from app.logging_config import configure_logging
from app.routers import (
    ad_angles,
    angle_images,
    angles,
    blog_generation,
    client_export,
    health,
    industries,
    logo,
    post_generation,
    post_images,
    posts,
    reel_images,
    reels,
    reviews,
    content_generation,
    website_content,
)

# Schema is always managed by Alembic migrations against Supabase Postgres —
# see alembic/. Run `alembic upgrade head` before starting the app.

configure_logging()
logger = logging.getLogger("app")

app = FastAPI(
    title="Meta Ads Angles API",
    description="Every endpoint requires the `X-API-Key` header. Click **Authorize** "
    "above and paste the key once — it'll be sent automatically on every "
    "'Try it out' request in this page.",
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version="1.0.0", description=app.description, routes=app.routes)
    schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    }
    for path in schema["paths"].values():
        for operation in path.values():
            operation["security"] = [{"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi

# Every route requires a valid X-API-Key header, except the API docs and the
# CORS preflight (OPTIONS) requests, which never carry custom headers.
_EXEMPT_PATHS = {"/docs", "/openapi.json", "/redoc", "/health"}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _error_response(request: Request, status_code: int, detail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": _request_id(request)},
    )


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.method == "OPTIONS" or request.url.path in _EXEMPT_PATHS:
        return await call_next(request)

    provided = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(provided, API_KEY):
        logger.warning("auth_failed request_id=%s path=%s", _request_id(request), request.url.path)
        return _error_response(request, 401, "Invalid or missing API key")

    return await call_next(request)


@app.middleware("http")
async def catch_unhandled(request: Request, call_next):
    """Last-resort net for anything the exception handlers below don't cover.

    FastAPI's own `@app.exception_handler(Exception)` runs in Starlette's
    ServerErrorMiddleware, which sits *outside* every middleware including
    CORS — so its 500 reaches the browser with no CORS headers and the frontend
    reports "couldn't reach the server" instead of showing the real error.
    Catching here, inside CORSMiddleware, keeps 500s readable in the browser.
    """
    try:
        return await call_next(request)
    except Exception:
        logger.exception(
            "unhandled_error request_id=%s path=%s", _request_id(request), request.url.path
        )
        return _error_response(request, 500, "Something went wrong on our end. Please try again.")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# Added last, so it wraps everything above: an error response is useless to the
# browser without CORS headers on it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Same shape as every other error response, so the frontend only ever has
    to read `detail` and `request_id`."""
    if exc.status_code >= 500:
        logger.error(
            "http_error request_id=%s path=%s status=%s detail=%s",
            _request_id(request),
            request.url.path,
            exc.status_code,
            exc.detail,
        )
    response = _error_response(request, exc.status_code, exc.detail)
    for key, value in (exc.headers or {}).items():
        response.headers[key] = value
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "validation_error request_id=%s path=%s errors=%s",
        _request_id(request),
        request.url.path,
        exc.errors(),
    )
    # Pydantic's raw error list is unreadable in a UI banner; turn it into
    # "Company name: field required" while keeping the full list in the log.
    messages = []
    for error in exc.errors():
        field = " → ".join(str(p) for p in error.get("loc", ()) if p not in ("body", "query"))
        message = error.get("msg", "is invalid")
        messages.append(f"{field}: {message}" if field else message)
    return _error_response(request, 422, "; ".join(messages) or "The submitted data was invalid.")


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.error(
        "app_error request_id=%s path=%s status=%s internal=%s",
        _request_id(request),
        request.url.path,
        exc.status_code,
        exc.internal or exc.message,
    )
    return _error_response(request, exc.status_code, exc.message)


@app.exception_handler(requests.RequestException)
async def upstream_request_handler(request: Request, exc: requests.RequestException):
    """A dependency we call over HTTP (Supabase Storage, HQ, an LLM API) never
    answered. Not our bug, and retrying often works — so 502, not 500."""
    logger.exception("upstream_error request_id=%s path=%s", _request_id(request), request.url.path)
    return _error_response(
        request, 502, "An external service didn't respond. Please try again in a moment."
    )


@app.exception_handler(OperationalError)
async def db_unavailable_handler(request: Request, exc: OperationalError):
    """Postgres unreachable — Supabase down, network dropped, DNS failed, or the
    connection pool is exhausted. Distinct from a query bug, and worth telling
    the user plainly because retrying is genuinely the right move."""
    logger.exception("db_unavailable request_id=%s path=%s", _request_id(request), request.url.path)
    return _error_response(
        request, 503, "Can't reach the database right now. Please try again in a moment."
    )


@app.exception_handler(SQLAlchemyError)
async def db_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("db_error request_id=%s path=%s", _request_id(request), request.url.path)
    return _error_response(request, 503, "A database error occurred. Please try again.")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Backstop for anything raised outside the middleware stack. Note this
    response bypasses CORS — see catch_unhandled above, which is what actually
    handles unhandled errors during a request."""
    logger.exception("unhandled_error request_id=%s path=%s", _request_id(request), request.url.path)
    return _error_response(request, 500, "Something went wrong on our end. Please try again.")

# Images live in Supabase Storage now (see app.storage) and are served
# directly from there via their public URLs — no local /uploads mount needed.

app.include_router(health.router)
app.include_router(ad_angles.router)
app.include_router(angles.router)
app.include_router(angle_images.router)
app.include_router(industries.router)
app.include_router(client_export.router)
app.include_router(logo.router)
app.include_router(post_generation.router)
app.include_router(blog_generation.router)
app.include_router(posts.router)
app.include_router(post_images.router)
app.include_router(reels.router)
app.include_router(reel_images.router)
app.include_router(reviews.router)
app.include_router(website_content.router)
app.include_router(content_generation.router)


@app.on_event("startup")
def _recover_abandoned_runs():
    """Clear website-content runs abandoned by a previous process.

    Generation runs on a daemon thread with no queue behind it, so a restart
    leaves its rows on "generating" and the UI polls them forever. This process
    has just started, so anything still marked generating belongs to a process
    that no longer exists. Best-effort: a database that is briefly unreachable
    must not stop the app from booting.
    """
    try:
        from app.services.website_content_service import recover_abandoned_runs

        recovered = recover_abandoned_runs()
        if recovered:
            logger.warning("startup_recovered_website_runs count=%s", recovered)
    except Exception:
        logger.exception("startup_recovery_failed")
