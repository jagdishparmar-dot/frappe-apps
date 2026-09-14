# HR Portal (Frappe v16 custom app)

Single-company HR + attendance. Phase **F1**: masters, hire, settings, documents, Expo login against Frappe.

This is not multi-tenant. Desk (`/app`) is for System Manager. Everyone else uses `/hr`.

## What F1 includes

- Masters: `HR Site`, `HR Shift`, `HR Shift Assignment`, `HR Leave Type`, `HR Holiday`, `HR Vendor`, `HR Employee Document`
- Hire / update / reset-password / deactivate via `@frappe.whitelist()` (creates User + `HR Employee`)
- SPA: Employees list/new/detail, Settings, Sites, Shifts catalog, My HR profile + documents
- Mobile: `EXPO_PUBLIC_FRAPPE_URL` → Frappe login (API key/secret), session, profile, documents
- Punch, leave apply, and roster remain later phases

## Local Docker (recommended)

Reuses images already on this machine: `frappe/bench`, `mariadb:11.8`, `redis:7-alpine`, `axllent/mailpit`. Same layout as the vendor-billing stack. **Stop that stack first** if it is bound to `:8000` / `:9000` / `:8025`.

```bash
cd frappe-app/hr_portal
copy .env.example .env
docker compose up --build
```

| What | URL |
|------|-----|
| Desk | http://localhost:8000 — `Administrator` / `admin` |
| HR SPA | http://localhost:8000/hr — `hr.admin@example.com` / `admin` |
| Employee ESS | http://localhost:8000/hr — `emp@example.com` / `admin` |
| Mailpit | http://localhost:8025 |

First boot runs `bench init` (10–20 min) into the `frappe-bench` volume. Later `docker compose up` only migrates and starts.

After pulling F1 code onto an existing volume:

```bash
docker compose exec frappe bash -lc "cd /home/frappe/frappe-bench && bench --site localhost migrate"
```

Rebuild the SPA (from Windows, `frappeProxy` stays false):

```bash
cd frappe-app/hr_portal/frontend
npx vite build
```

Dockerfile: [`docker/Dockerfile`](./docker/Dockerfile) (`FROM frappe/bench:latest`). Entrypoint: [`docker/frappe-entrypoint.sh`](./docker/frappe-entrypoint.sh).

```bash
docker compose logs -f frappe
docker compose exec frappe bash
# inside the container:
cd /home/frappe/frappe-bench
bench --site localhost run-tests --app hr_portal
```

## Expo against local Frappe

In `checkin-mobile/.env`:

```
EXPO_PUBLIC_FRAPPE_URL=http://localhost:8000
```

Android emulator: `http://10.0.2.2:8000`. Physical device: your LAN IP. Hire the person in `/hr`, then log in on Expo with that email and temp password.

## Install (existing Linux bench)

Frappe v16 does not run natively on Windows. Use the Compose file above, or a host bench.

```bash
cd frappe-bench
bench get-app hr_portal /path/to/EMPLOYEE-TRACKER/frappe-app/hr_portal
bench --site hrms.localhost install-app hr_portal
bench --site hrms.localhost migrate
cd apps/hr_portal/frontend && yarn && yarn build
bench --site hrms.localhost clear-cache
```

## Tests

```bash
bench --site localhost run-tests --app hr_portal
```

Covers F0 permission isolation plus F1 hire, geofence-requires-site, mobile login token, and document isolation.

## Next (Phase F2)

Attendance punch, geofence, regularization, reports. Remove remaining Appwrite usage from Expo.
