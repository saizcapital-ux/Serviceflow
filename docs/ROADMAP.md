# Serviceflow — Product Roadmap

A pragmatic path from the current MVP to a sellable, scalable SaaS.

## ✅ MVP (this repository)

- Multi-tenant data model (org → users, customers, equipment, work orders)
- JWT auth + role-based access (owner / manager / service_writer / technician / customer)
- Work-order lifecycle with an enforced status **state machine** + event timeline
- Inspection findings, quotes with line items & totals
- Customer portal: live status tracker, history, **online quote approval**
- Field-service job type
- Staff dashboard (KPIs + pipeline)
- REST API with OpenAPI docs; HTML/CSS/JS staff app + portal; seed/demo data

## ✅ v1 — "Run a real shop" (delivered)

| Area | Status |
|------|--------|
| **Billing (theirs)** | ✅ Invoices from approved quotes + branded PDF export (QuickBooks/Xero sync still open) |
| **Billing (yours)**  | ✅ Stripe subscriptions, plans & seats, mock mode; card capture UI open |
| **Labor & costing**  | ✅ Time entries in UI; labor vs. estimate margin on each job |
| **Files/photos**     | ✅ Uploads with pluggable local/S3 storage backend |
| **Notifications**    | ✅ Email on status change & quote sent (SMTP/console); SMS stub; async queue open |
| **Scheduling**       | ✅ Field dispatch board + technician assignment |
| **Migrations**       | ✅ Alembic wired; initial migration; CI verifies up/down |
| **Testing/CI**       | ✅ pytest suite (28 tests) + GitHub Actions (tests, migrations, JS syntax) |

### v1 follow-ups still open
- Accounting sync (QuickBooks/Xero), Stripe card-capture UI & customer portal for billing
- Async task queue for notifications (Celery/RQ) + SMS provider (Twilio)

## ✅ v2 — "Grow" (delivered)

- ✅ Inventory & parts catalog with reorder points + job consumption
- ✅ QR asset tags (scan to open the asset) + printable labels
- ✅ Customer PO tracking & approval limits
- ✅ Reporting suite (throughput, turnaround, revenue, workload, pipeline)
- ✅ Job checklists / travelers (per-equipment-type templates)
- ✅ Installable PWA (manifest + service worker, offline app shell)

### v2 follow-ups still open
- Barcode (not just QR) scanning from a camera; first-pass-yield metric
- Offline **job capture** (queue writes while offline, sync on reconnect)
- Fully configurable statuses per shop

## 🏔 v3 — "Scale & enterprise"

- Multi-location / multi-warehouse tenants
- SSO (SAML/OIDC), audit logs, granular permissions
- API keys & webhooks for customer ERP integration
- Schema-per-tenant option for large accounts
- SLA tracking and predictive maintenance insights

## Engineering hardening (continuous)

- Move frontend to Vite + React when interactivity demands it (API contract and
  design tokens already carry over)
- Structured logging, request IDs, error tracking (Sentry)
- Rate limiting, refresh tokens, password reset & invite flows
- Containerization (Docker) + IaC; managed Postgres; automated backups
