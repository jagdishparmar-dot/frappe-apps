# Coldverse Vendor Billing

Separate project from `coldverse-vendor-manager` (the current Next.js + PostgreSQL monolith).

This repo is the Frappe custom app for the **admin portal** (Phase 1 DocTypes in-tree) plus a Next.js **vendor portal** that talks only to Frappe APIs.

| Deployable | Path | Runtime |
|------------|------|---------|
| Admin (Desk) | `vendor_billing/` (this git root is the Frappe app) | **Frappe v16** / MariaDB / Python 3.14 |
| Vendor portal | [`portal/`](./portal) | Next.js 16, separate host |

Vendors never log into Desk. Staff never use the Next portal.

## Locked decisions

- MariaDB is the system of record (Postgres in the old app is ETL source only).
- Admin IAM, File/storage, Workflows, Data Import, Print Formats → Frappe.
- Vendor UI stays Next.js (`/portal/[token]` + OTP).
- Portal calls Frappe whitelist methods (`vendor_billing.portal.*`).
- Two deployments; portal sets `FRAPPE_URL` (and API key) in env.
- **Frappe Framework v16** (not v15, not ERPNext). Python **3.14** (Frappe v16 requirement).

See [docs/portal-api-contract.md](./docs/portal-api-contract.md), [docs/frappe-roles.md](./docs/frappe-roles.md), [docs/PHASE1.md](./docs/PHASE1.md), [docs/PHASE2.md](./docs/PHASE2.md), and [docs/PHASE3.md](./docs/PHASE3.md).

## Repository layout

```
coldverse-vendor-billing/          ← git root = Frappe app (bench get-app)
  vendor_billing/                  Python package
    hooks.py
    portal.py                      whitelist API
    portal_auth.py                 OTP session guard
    install.py                     creates VB* roles
    docker_setup.py                Compose bootstrap (keys, mail, demo vendor)
    vendor_billing/doctype/        Phase 1 DocTypes
  docker-compose.yml
  docker/
  portal/                          Next.js vendor app
  docs/
  pyproject.toml
```

`bench get-app <this-git-url>` clones the whole repo (including `portal/`). Frappe ignores `portal/`. Deploy Next from `portal/` on its own host.

## Local Docker (recommended)

MariaDB 11.8, Redis, Frappe v16 Desk, Mailpit, and the Next portal:

```bash
cp .env.example .env
docker compose up --build
```

| What | URL |
|------|-----|
| Desk | http://localhost:8000 — `Administrator` / `admin` |
| Portal | http://localhost:3000/portal/demo-vendor-token |
| Mailpit (OTP / mail) | http://localhost:8025 |

First boot clones Frappe and takes 10–20 minutes. Full runbook: [docs/DOCKER.md](./docs/DOCKER.md).

## Frappe admin (host bench)

Requires an existing **Frappe v16** bench (MariaDB, Redis, **Python 3.14**). Skip this if you use Compose.

```bash
# new bench (once)
bench init frappe-bench --frappe-branch version-16
cd frappe-bench

bench get-app /path/to/coldverse-vendor-billing --skip-assets
# or after the remote exists:
# bench get-app https://github.com/<org>/coldverse-vendor-billing.git

bench --site <site> install-app vendor_billing
bench --site <site> migrate
bench start
```

Do not install this app on a v15 bench. `pyproject.toml` declares `frappe = ">=16.0.0,<17.0.0"`.

Desk: `http://localhost:8000`. Create a User, assign a `VB *` role. Create an API key for a user with role **VB Portal Gateway** and put it in the portal env (below).

## Vendor portal (host Next)

```bash
cd portal
cp .env.example .env.local
# set FRAPPE_URL=http://localhost:8000
npm install
npm run dev
```

Portal: `http://localhost:3000/portal/<vendor-token>`.

In Docker (`developer_mode`) the OTP is printed to the Frappe console and shown on the portal page. After OTP the vendor workspace (invoices, KYC, profile, agreements, notifications) is live. See [docs/PHASE2.md](./docs/PHASE2.md).

Staff admin is Frappe Desk, not this Next app. See [docs/PHASE3.md](./docs/PHASE3.md).

## Env (portal)

| Variable | Purpose |
|----------|---------|
| `FRAPPE_URL` | Frappe origin (admin host) |
| `FRAPPE_API_KEY` / `FRAPPE_API_SECRET` | Next BFF → Frappe `Authorization` header (skips CSRF). User should have role `VB Portal Gateway` only. |
| `PORTAL_ORIGIN` | Public vendor host, used later for share links |

The browser talks to the Next origin only. Next server-side routes forward to `{FRAPPE_URL}/api/method/vendor_billing.portal.*`. Do not send Frappe `sid` to the portal domain.

## What is not here yet (Phase 4+)

- ETL of remaining invoices, agreements, audit, notifications, and KYC document bytes from the old PostgreSQL app
- Decommission of Better Auth / Next admin in `coldverse-vendor-manager`

## Relation to the old app

`../coldverse-vendor-manager` stays production until cutover. Do not dual-write Prisma and Frappe.
