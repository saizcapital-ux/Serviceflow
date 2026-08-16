"""Serviceflow API — FastAPI application entrypoint."""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routers import (
    analytics,
    attachments,
    audit,
    auth,
    billing,
    checklists,
    customers,
    dashboard,
    developer,
    integration,
    invites,
    invoices,
    locations,
    maintenance,
    notifications,
    onboarding,
    parts,
    portal,
    receivables,
    search,
    spec_templates,
    tests as tests_router,
    team,
    work_orders,
)
from app.core.config import settings
from app.core.database import Base, engine

# Zero-config dev: auto-create tables on startup. In production set
# SERVICEFLOW_ENVIRONMENT=production and manage schema with Alembic
# (`alembic upgrade head`) instead.
if settings.environment != "production":
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Serviceflow API",
    version="0.1.0",
    description="SaaS platform for industrial repair service centers "
    "(motors, valves, actuators, pumps, blowers).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Structured access logging. Uvicorn configures the root handler; we just make
# sure our app logger propagates at INFO so request lines are emitted.
logging.getLogger("serviceflow").setLevel(logging.INFO)
_access_log = logging.getLogger("serviceflow.access")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id to every request/response and log one line per call."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        _access_log.exception(
            "%s %s -> 500 %.1fms request_id=%s", request.method, request.url.path, duration_ms, request_id
        )
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    _apply_security_headers(response)
    _access_log.info(
        "%s %s -> %d %.1fms request_id=%s",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    return response


def _apply_security_headers(response) -> None:
    """Baseline hardening headers applied to every API response."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-XSS-Protection", "0")  # rely on modern browser defaults, not the legacy filter
    if settings.environment == "production":
        # Only meaningful over HTTPS (Render terminates TLS); browsers ignore on http.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a clean JSON 500 (with the request id) instead of leaking a stack
    trace. The request_context middleware already logged the traceback."""
    request_id = getattr(request.state, "request_id", None)
    resp = JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id},
    )
    if request_id:
        resp.headers["X-Request-ID"] = request_id
    _apply_security_headers(resp)
    return resp

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(audit.router)
app.include_router(developer.router)
app.include_router(integration.router)
app.include_router(billing.router)
app.include_router(team.router)
app.include_router(team.team_router)
app.include_router(invites.router)
app.include_router(search.router)
app.include_router(spec_templates.router)
app.include_router(tests_router.router)
app.include_router(locations.router)
app.include_router(maintenance.router)
app.include_router(customers.router)
app.include_router(work_orders.router)
app.include_router(parts.router)
app.include_router(checklists.router)
app.include_router(invoices.router)
app.include_router(receivables.router)
app.include_router(attachments.router)
app.include_router(notifications.router)
app.include_router(onboarding.router)
app.include_router(portal.router)


@app.get("/health", tags=["system"])
def health():
    """Liveness: the process is up (no dependencies checked)."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "email": "smtp" if settings.email_configured else "console",
    }


@app.get("/ready", tags=["system"])
def ready():
    """Readiness: verify the database is reachable. Returns 503 if not, so load
    balancers and uptime monitors can route/alert correctly."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via the error path
        _access_log.warning("Readiness check failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "error"})
    return {"status": "ready", "database": "ok"}
