"""Serviceflow API — FastAPI application entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    analytics,
    attachments,
    auth,
    billing,
    customers,
    dashboard,
    invoices,
    notifications,
    portal,
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

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(billing.router)
app.include_router(team.router)
app.include_router(customers.router)
app.include_router(work_orders.router)
app.include_router(invoices.router)
app.include_router(attachments.router)
app.include_router(notifications.router)
app.include_router(portal.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}
