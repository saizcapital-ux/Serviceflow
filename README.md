# Serviceflow

**The operating system for industrial repair service centers.**

Serviceflow is a multi-tenant SaaS platform for shops that repair and overhaul
rotating and flow equipment — **electric motors, valves, Limitorque actuators,
pumps, blowers, gearboxes and more**. It runs the full repair lifecycle from
equipment intake to shipped-and-invoiced, adds field-service dispatch, and gives
your customers a self-service portal to track the status and history of every
asset they've ever sent you.

---

## Why Serviceflow

Repair shops still run on whiteboards, spreadsheets, and paper travelers. That
means lost job history, no visibility for customers, quotes that slip, and no
data on shop throughput. Serviceflow replaces all of it with one system of
record:

- **Work-order lifecycle** — Intake → Inspection → Quote → Approval → Repair →
  Test → Ship, with a full status timeline on every job.
- **Asset-centric history** — Every motor, valve, pump and actuator has a
  permanent nameplate + repair history, so the 5th visit is faster than the 1st.
- **Field service** — Schedule and dispatch technicians for on-site work with the
  same job engine used in the shop.
- **Customer portal** — Your customers log in to see live job status, approve
  quotes, and pull the complete service history of their equipment.
- **Multi-tenant** — Every service center is an isolated tenant; Serviceflow is
  sold as a subscription.

---

## Tech stack

| Layer      | Technology                                             |
|------------|--------------------------------------------------------|
| Backend    | Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2      |
| Auth       | JWT (access tokens), bcrypt password hashing, RBAC     |
| Database   | PostgreSQL (production) · SQLite (zero-config dev)      |
| Frontend   | HTML5, modern CSS (design tokens), vanilla JS (ES modules) |
| API        | REST + OpenAPI 3 (auto-generated docs at `/docs`)      |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full picture.

---

## Quick start (dev)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed            # creates SQLite db + demo data
uvicorn app.main:app --reload # API on http://localhost:8000  (docs at /docs)

# 2. Frontend (any static server)
cd ../frontend
python -m http.server 5173    # open http://localhost:5173
```

### Demo logins (created by the seed script)

| Role              | Email                     | Password    |
|-------------------|---------------------------|-------------|
| Owner / Admin     | admin@apexrepair.com      | Password123 |
| Service Writer    | writer@apexrepair.com     | Password123 |
| Technician        | tech@apexrepair.com       | Password123 |
| **Customer** portal | buyer@acmepower.com     | Password123 |

---

## Repository layout

```
Serviceflow/
├── backend/            FastAPI application (API, models, auth, business logic)
│   └── app/
│       ├── core/       config, database, security
│       ├── models/     SQLAlchemy ORM models (the data model)
│       ├── schemas/    Pydantic request/response schemas
│       ├── api/        route handlers grouped by resource
│       └── seed.py     demo data generator
├── frontend/           HTML/CSS/JS client (staff app + customer portal)
│   ├── assets/         design system CSS, JS modules
│   ├── app/            staff-facing screens
│   └── portal/         customer-facing screens
├── docs/               architecture, data model, API, roadmap, design
└── scripts/            dev helpers
```

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design, components, security
- [Data model](docs/DATA_MODEL.md) — entities, relationships, status workflow
- [API reference](docs/API.md) — endpoints and examples
- [UI/UX & wireframes](docs/DESIGN.md) — screens, flows, design system
- [Product roadmap](docs/ROADMAP.md) — MVP → v1 → scale

---

## License

Proprietary — © Serviceflow. All rights reserved.
