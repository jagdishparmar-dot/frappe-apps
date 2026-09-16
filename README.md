# Vendor Billing + HR Portal

**Frappe Desk** = admin via **Vendor Billing** (vendors, agreements, invoices, KYC). Portal APIs live on the Frappe site (`vendor_billing.portal.*`); deploy any separate vendor UI elsewhere if needed.

**HR Portal** = Frappe app with a custom Vue SPA (like Frappe CRM) served at **`/hr`** on the Desk domain — employees, attendance, leave, shifts, payroll.

## Deploy on Coolify

See **[docs/COOLIFY_DEPLOY.md](docs/COOLIFY_DEPLOY.md)** — Coolify proxy assigns a domain to `frappe-nginx`.

## Local quick start

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

| URL | Who |
|-----|-----|
| http://vendors.localhost:8080 | Frappe Desk (admin) — add `127.0.0.1 vendors.localhost` to hosts if needed |
| http://vendors.localhost:8080/hr | HR Portal SPA (HR roles) |
| http://vendors.localhost:8080/control | Bench Control (System Manager) — sites & apps |

**Desk:** `Administrator` / `ADMIN_PASSWORD` (default in `.env.example` is `changeme`)

### Admin setup

1. Desk → **VB Vendor** → New  
2. Review KYC, agreements, and invoices in Vendor Billing  
3. Open **/control** to create extra sites and install apps already in the image  

## Layout

```
apps/                    # Every app folder here is built + installed automatically
apps/vendor_billing/     # Frappe Vendor Billing Desk app + portal APIs
apps/hr_portal/          # Frappe HR Portal app + Vue SPA frontend (/hr)
apps/bench_control/      # Bench control plane UI (/control) — manage sites/apps
docker/                  # Frappe image + nginx templates
docs/COOLIFY_DEPLOY.md   # Coolify production guide
docs/ADD_FRAPPE_CRM.md   # Add Frappe CRM (or any app) via the apps/ folder
docker-compose.yml       # Coolify / production compose
docker-compose.dev.yml   # Local published Desk port + multi-site Host routing
```

## Adding an app (incl. Frappe CRM)

Drop any valid Frappe app folder into `apps/` (folder name = app name, with
`pyproject.toml`) and rebuild — the image installs and builds it automatically,
and `create-site` installs it on the site. See [docs/ADD_FRAPPE_CRM.md](docs/ADD_FRAPPE_CRM.md).
