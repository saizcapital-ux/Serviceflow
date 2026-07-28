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

## 🔜 v1 — "Run a real shop" (next)

| Area | Work |
|------|------|
| **Billing (theirs)** | Invoices from approved quotes; PDF export; QuickBooks/Xero sync |
| **Billing (yours)**  | Stripe subscriptions, plans & seats, trial→paid |
| **Labor & costing**  | Technician time entries in UI; labor vs. estimate margin reporting |
| **Files/photos**     | S3 uploads for nameplate pics, inspection photos, test reports |
| **Notifications**    | Email/SMS on status change & quote sent (task queue) |
| **Scheduling**       | Field dispatch calendar, technician assignment board |
| **Migrations**       | Alembic; seed → fixtures separation |
| **Testing/CI**       | pytest suite for the service layer + API; GitHub Actions |

## 🌤 v2 — "Grow"

- Inventory & parts catalog with reorder points
- Barcode/QR asset tags (scan to open the asset)
- Customer PO tracking & approval limits
- Reporting suite (throughput, turnaround time, first-pass yield, revenue)
- Configurable workflows per shop (custom statuses, checklists/travelers)
- Mobile technician app (PWA) with offline job capture

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
