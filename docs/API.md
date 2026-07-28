# Serviceflow — API Reference

Base URL (dev): `http://127.0.0.1:8000`
Interactive docs: `http://127.0.0.1:8000/docs` (OpenAPI/Swagger, auto-generated)

All endpoints except `/health` and `/api/auth/login` require
`Authorization: Bearer <token>`.

## Auth

| Method | Path              | Body                          | Notes                       |
|--------|-------------------|-------------------------------|-----------------------------|
| POST   | `/api/auth/login` | `{email, password}`           | Returns `{access_token, user}` |
| POST   | `/api/auth/token` | form `username`, `password`   | For Swagger "Authorize"     |
| GET    | `/api/auth/me`    | —                             | Current user                |

```bash
curl -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@apexrepair.com","password":"Password123"}'
```

## Dashboard (staff)

| Method | Path             | Notes                                        |
|--------|------------------|----------------------------------------------|
| GET    | `/api/dashboard` | KPIs, counts by status, recent work orders   |

## Customers & Equipment (staff)

| Method | Path                        | Notes                          |
|--------|-----------------------------|--------------------------------|
| GET    | `/api/customers?q=`         | List / search                  |
| POST   | `/api/customers`            | Create                         |
| GET    | `/api/customers/{id}`       | Detail (+ contacts)            |
| GET    | `/api/equipment?customer_id=` | List (optionally by customer)|
| POST   | `/api/equipment`            | Create asset                   |
| GET    | `/api/equipment/{id}`       | Detail                         |

## Work orders (staff)

| Method | Path                               | Notes                                  |
|--------|------------------------------------|----------------------------------------|
| GET    | `/api/work-orders`                 | Filters: `status`, `service_type`, `customer_id`, `open_only` |
| POST   | `/api/work-orders`                 | Create (auto-numbers `WO-YYYY-NNNN`)   |
| GET    | `/api/work-orders/{id}`            | Full detail (events, findings, quotes) |
| PATCH  | `/api/work-orders/{id}`            | Update fields                          |
| POST   | `/api/work-orders/{id}/status`     | `{status, message, visible_to_customer}` — validated by state machine |
| POST   | `/api/work-orders/{id}/findings`   | Add inspection finding                 |
| POST   | `/api/work-orders/{id}/quotes`     | `{lines:[...], tax_rate}` — computes totals |

## Customer portal (portal users only)

| Method | Path                                   | Notes                                   |
|--------|----------------------------------------|-----------------------------------------|
| GET    | `/api/portal/work-orders`              | Only the customer's own work orders     |
| GET    | `/api/portal/work-orders/{id}`         | Detail; internal-only events hidden     |
| GET    | `/api/portal/equipment`                | The customer's own equipment            |
| POST   | `/api/portal/quotes/{id}/decision`     | `{approve: bool, note}` — advances the WO |

## Errors

Standard HTTP codes with `{"detail": "..."}`:
`401` unauthenticated · `403` wrong role / cross-tenant · `404` not found ·
`409` invalid state transition or duplicate.
