# Deploying Serviceflow to the web

This gets you a **fully working, publicly reachable** Serviceflow — staff app,
customer portal, and live API — without running anything on your own computer.

Serviceflow is two pieces, so it's hosted in two places:

| Piece | What it is | Where it's hosted |
|-------|------------|-------------------|
| **Frontend** | Static HTML/CSS/JS (`frontend/`) | **Netlify** (already set up) |
| **Backend** | FastAPI + PostgreSQL (`backend/`) | **Render** (this guide) |

The frontend already auto-deploys to Netlify. The only thing missing for a
*working* app is the backend + database — that's what you'll deploy below, then
point the frontend at it with a one-line edit.

Everything here is done in the browser. No terminal, no local install.

---

## Step 1 — Deploy the backend + database to Render

Render reads [`render.yaml`](../render.yaml) in this repo and provisions
everything automatically: a free PostgreSQL database **and** the API service.

1. Go to **<https://dashboard.render.com>** and sign in with GitHub (free).
2. Click **New → Blueprint**.
3. Select this repository (**`saizcapital-ux/Serviceflow`**) and the branch
   you want to deploy (e.g. `claude/saas-framework-design-uep2i5`, or `main`
   once merged).
4. Render detects `render.yaml` and shows a plan: **serviceflow-db** (Postgres)
   + **serviceflow-api** (web service). Click **Apply**.

Render will build the service, run database migrations, seed the demo tenant
**once**, and start the API. First build takes a few minutes.

When it's done, open the **serviceflow-api** service — its URL is at the top,
something like:

```
https://serviceflow-api.onrender.com
```

Confirm it's alive by visiting **`<that-url>/health`** — you should see
`{"status":"ok",...}`. The interactive API docs are at **`<that-url>/docs`**.

> **Free-tier note:** Render spins the service down after ~15 minutes idle, so
> the *first* request after a nap takes ~30–50s to wake up. Subsequent requests
> are fast. Upgrade the service to a paid instance to keep it always-on.

---

## Step 2 — Point the frontend at your backend

Open [`frontend/config.js`](../frontend/config.js) and set the URL to the
Render service URL from Step 1:

```js
window.SERVICEFLOW_API = "https://serviceflow-api.onrender.com";
```

Commit that change. Netlify redeploys the frontend automatically. That's the
only wiring between the two halves.

> Why an edit and not automatic? The frontend and backend are deployed
> independently, so the frontend has to be told the backend's address. This one
> line is it — no build step, no environment plumbing.

---

## Step 3 — Open the app

Use your Netlify URL:

- **Production site:** <https://serviceflowappv2.netlify.app>
- **Per-PR preview:** the `deploy-preview-…` link Netlify comments on each PR

Sign in with a seeded demo account:

| Role | Email | Password |
|------|-------|----------|
| Owner / Admin | admin@apexrepair.com | Password123 |
| Service Writer | writer@apexrepair.com | Password123 |
| Technician | tech@apexrepair.com | Password123 |
| Customer portal | buyer@acmepower.com | Password123 |

You now have a live, multi-user web app with real data, quotes, invoices, PDFs,
and the customer portal — all in the browser.

---

## How the production setup differs from dev

- **Database:** PostgreSQL on Render (dev uses zero-config SQLite).
- **Schema:** managed by **Alembic migrations** (`alembic upgrade head` on every
  deploy). In production the app does *not* auto-create tables — that's why
  `SERVICEFLOW_ENVIRONMENT=production` is set.
- **Demo data:** seeded **once** by `python -m app.bootstrap`, which only runs
  the seed when the database has no users yet. Re-deploys never wipe your data.
  (`python -m app.seed` — the dev seeder — *does* drop and recreate everything;
  don't run it against production.)
- **CORS:** `SERVICEFLOW_CORS_ORIGINS=*`. Auth is Bearer-token based (no
  cookies), so a wildcard is safe and lets every Netlify preview URL reach the
  API. Lock it down to your exact origins if you later add cookie auth.

## Environment variables (set for you by `render.yaml`)

| Variable | Value | Purpose |
|----------|-------|---------|
| `SERVICEFLOW_ENVIRONMENT` | `production` | Use Alembic, not auto-create |
| `SERVICEFLOW_DATABASE_URL` | *(from the Render DB)* | Postgres connection |
| `SERVICEFLOW_SECRET_KEY` | *(auto-generated)* | JWT signing key |
| `SERVICEFLOW_CORS_ORIGINS` | `*` | Allowed browser origins |
| `SERVICEFLOW_APP_BASE_URL` | your Netlify URL | QR deep-links & billing redirects |

### Optional integrations (leave unset for the demo)

- **Stripe billing** — set `SERVICEFLOW_STRIPE_SECRET_KEY` to take real
  subscriptions. Unset, billing runs in mock mode (checkout activates instantly).
- **S3 attachments** — set `SERVICEFLOW_STORAGE_BACKEND=s3` plus the
  `SERVICEFLOW_S3_*` vars. Unset, files are stored on local disk.
- **SMTP email** — **required for launch.** Until it's set, invites, password
  resets, and quote/status emails are only logged to the console — no one
  actually receives them. Use a transactional email provider (SendGrid,
  Postmark, Mailgun, Amazon SES) and set on the Render service:

  | Variable | Example | Notes |
  |----------|---------|-------|
  | `SERVICEFLOW_SMTP_HOST` | `smtp.postmarkapp.com` | provider's SMTP host |
  | `SERVICEFLOW_SMTP_PORT` | `587` | 587 = STARTTLS, 465 = implicit TLS |
  | `SERVICEFLOW_SMTP_SSL` | `false` | set `true` only for port 465 |
  | `SERVICEFLOW_SMTP_USER` | *(provider username / API token)* | |
  | `SERVICEFLOW_SMTP_PASSWORD` | *(provider password / API token)* | |
  | `SERVICEFLOW_EMAIL_FROM` | `no-reply@yourshop.com` | a verified sender on your domain |

  Verify it's active: `GET /health` returns `"email": "smtp"` once a host is set
  (it reads `"console"` otherwise). For best deliverability, set up SPF/DKIM for
  your sending domain with your provider.

  > On Render's free tier the API's local disk is **ephemeral** — uploaded
  > attachments are lost on redeploy/restart. Use the S3 backend for durable
  > files in production.

---

## Alternative hosts

`render.yaml` targets Render, but the backend is a standard FastAPI app and runs
anywhere that runs Python + Postgres (Railway, Fly.io, a VM). The only
requirements are: install `backend/requirements.txt`, set the environment
variables above, run `alembic upgrade head`, then start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Point `frontend/config.js`
at whatever URL you get.
