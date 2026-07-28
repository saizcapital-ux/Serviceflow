# Serviceflow — Architecture

## 1. System overview

Serviceflow is a **multi-tenant SaaS**. A *tenant* is one service center
(a repair shop business). Each tenant has staff users, customers, equipment
assets, and work orders. Customers of a tenant get restricted portal accounts.

```
                          ┌──────────────────────────────┐
                          │          Browser              │
                          │  Staff App   │  Customer Portal│
                          │  (HTML/CSS/JS)                 │
                          └───────────────┬───────────────┘
                                          │ HTTPS / JSON (JWT)
                                          ▼
                          ┌──────────────────────────────┐
                          │        FastAPI backend        │
                          │  ┌────────────────────────┐   │
                          │  │ API routers (REST)     │   │
                          │  ├────────────────────────┤   │
                          │  │ Auth / RBAC middleware │   │
                          │  ├────────────────────────┤   │
                          │  │ Services (domain logic)│   │
                          │  ├────────────────────────┤   │
                          │  │ SQLAlchemy ORM models  │   │
                          │  └────────────────────────┘   │
                          └───────────────┬───────────────┘
                                          ▼
                          ┌──────────────────────────────┐
                          │   PostgreSQL (SQLite in dev)  │
                          └──────────────────────────────┘
```

## 2. Backend design

**Framework:** FastAPI — async-ready, type-safe, auto-generates OpenAPI docs.

**Layering (dependencies point downward):**

1. **API layer** (`app/api/routers/*`) — thin HTTP handlers. Parse/validate with
   Pydantic, enforce auth, delegate to services, serialize responses.
2. **Service layer** (`app/services/*`) — domain logic: status transitions,
   quote totals, work-order numbering, portal scoping.
3. **Model layer** (`app/models/*`) — SQLAlchemy ORM. Single source of truth for
   the schema.
4. **Core** (`app/core/*`) — configuration, DB session lifecycle, security
   primitives (hashing, JWT).

**Why this split:** routers stay testable and dumb; business rules live in one
place; swapping SQLite→Postgres or REST→GraphQL touches only the edges.

## 3. Multi-tenancy

- Every tenant-scoped row carries an `organization_id`.
- The authenticated user's `organization_id` is injected into every query via a
  dependency (`get_current_user`), so one tenant can never read another's data.
- Customer-portal users additionally carry a `customer_id`; their queries are
  scoped to **their own** equipment and work orders only.

This is **shared-database, shared-schema** multi-tenancy — the cheapest to run
and simplest to operate at MVP/early scale. A future move to schema-per-tenant
or DB-per-tenant is possible for large enterprise customers without changing the
API contract.

## 4. Authentication & authorization

- **Passwords:** bcrypt via `passlib`.
- **Sessions:** stateless **JWT** access tokens (`Authorization: Bearer <token>`).
- **RBAC roles:**
  | Role            | Scope                                                     |
  |-----------------|-----------------------------------------------------------|
  | `owner`         | Full access, billing, user management                     |
  | `manager`       | All operational data, reporting                           |
  | `service_writer`| Create/edit work orders, quotes, customers                |
  | `technician`    | Assigned jobs, log labor, add findings                    |
  | `customer`      | Portal only — own equipment, job status, approve quotes   |

- A `require_roles(...)` dependency guards each endpoint.

## 5. Core domain: the work-order lifecycle

The repair job (`WorkOrder`) is the heart of the system. It moves through a
defined state machine (see [DATA_MODEL.md](DATA_MODEL.md)); every transition is
recorded in `WorkOrderEvent` to build the timeline the customer sees.

## 6. Frontend design

- **No build step required** — plain ES modules + a CSS design-token system, so
  it runs on any static host and is trivial to hand off.
- **Two apps, one design language:** the internal *Staff App* and the external
  *Customer Portal* share `assets/css/design-system.css`.
- **API client** (`assets/js/api.js`) centralizes fetch, auth headers, and error
  handling.
- Production path: this can be lifted into React/Vite later; the API contract and
  design tokens carry over unchanged.

## 7. Environments & configuration

Configuration is via environment variables (12-factor), read in
`app/core/config.py`:

| Variable          | Default                | Purpose                        |
|-------------------|------------------------|--------------------------------|
| `DATABASE_URL`    | `sqlite:///serviceflow.db` | DB connection                |
| `SECRET_KEY`      | dev key (change!)      | JWT signing                    |
| `ACCESS_TOKEN_TTL_MIN` | `720`             | Token lifetime                 |
| `CORS_ORIGINS`    | `*` (dev)              | Allowed frontends              |

## 8. Non-functional roadmap

- **Testing:** pytest + httpx for API; the service layer is unit-testable.
- **Migrations:** Alembic (models are already declarative).
- **Files/photos:** S3-compatible object storage (interface stubbed).
- **Async jobs:** email/SMS notifications via a task queue (Celery/RQ).
- **Observability:** structured logging, request IDs, `/health` endpoint.

See [ROADMAP.md](ROADMAP.md) for sequencing.
