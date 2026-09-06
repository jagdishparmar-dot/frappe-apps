# Vendor Directory — Draft Design & Docker Deployment

> **Status:** Scaffolded (P1–P3 started)  
> **Stack:** Next.js (frontend) · Frappe Framework (backend/API) · Docker Compose  
> **Date:** 2026-09-05

---

## 1. Overview

A **Vendor Directory** application to **list, add, view, and edit** vendors with full commercial details (address, GST, bank).

| Layer | Role |
|--------|------|
| **Next.js** | UI for CRUD: list, create, detail, edit |
| **Frappe** | DocTypes, permissions, REST API, audit, storage |
| **Docker Compose** | Single deployable stack (Frappe + DB + Redis + Next.js) |

---

## 2. Goals & Non-Goals

### Goals
- CRUD for vendors from a modern web UI
- Store address, GST, and bank details on the Vendor record
- Auth via Frappe (session / API key)
- Deployable with Docker Compose on a single host
- Extensible for future modules (purchase orders, payments)

### Non-Goals (v1)
- Multi-company / multi-tenant UI complexity
- Native mobile apps
- Full ERPNext Purchase workflow (can link later)
- Offline-first PWA

---

## 3. High-Level Architecture

```
┌─────────────────┐     HTTPS / REST      ┌──────────────────────────┐
│  Next.js App    │ ◄──────────────────►  │  Frappe (Bench / Site)   │
│  (App Router)   │   /api/resource/...   │  Custom app: vendor_dir  │
│  Port 3000      │   /api/method/...     │  Port 8000 (+ nginx)     │
└─────────────────┘                       └────────────┬─────────────┘
                                                       │
                              ┌────────────────────────┼────────────────┐
                              ▼                        ▼                ▼
                         MariaDB /               Redis Cache      Redis Queue
                         PostgreSQL              + SocketIO
```

**Suggested custom Frappe app name:** `vendor_directory`  
**Suggested site name:** `vendors.localhost` (dev) / your domain (prod)

---

## 4. Data Model (Frappe DocTypes)

### 4.1 Vendor (main DocType)

| Field | Type | Notes |
|--------|------|--------|
| `vendor_name` | Data | Required, title field |
| `vendor_code` | Data | Unique, auto or manual |
| `status` | Select | Active / Inactive / Blacklisted |
| `vendor_type` | Select | Goods / Services / Both |
| `email` | Data | |
| `phone` | Data | |
| `website` | Data | |
| `contact_person` | Data | |
| `notes` | Text Editor | Free text |
| **Address** | | |
| `address_line1` | Data | |
| `address_line2` | Data | |
| `city` | Data | |
| `state` | Data | |
| `pincode` | Data | |
| `country` | Link → Country | Default India |
| **GST / Tax** | | |
| `gstin` | Data | Validate format (India) |
| `pan` | Data | |
| `gst_registration_type` | Select | Regular / Composition / Unregistered |
| `place_of_supply` | Data | State code / name |
| **Bank** | | |
| `bank_name` | Data | |
| `account_holder_name` | Data | |
| `account_number` | Data | Sensitive — role-restricted |
| `ifsc_code` | Data | |
| `branch` | Data | |
| `upi_id` | Data | Optional |

**Naming:** `VD-.####` or `vendor_code` as name.  
**Permissions:** System Manager / Vendor Manager (write); Vendor User (read). Roles are created on app install.

### 4.2 Optional (phase 2)
- Child table **Vendor Contact** (name, email, phone, role)
- Child table **Vendor Document** (file attach: GST certificate, cancelled cheque)
- Link to ERPNext **Supplier** if ERPNext is installed later

---

## 5. Next.js App — Screens & Routes

| Route | Purpose |
|--------|---------|
| `/` | Redirect to `/vendors` |
| `/vendors` | List + search + filters (status, city, GST type) |
| `/vendors/new` | Create form |
| `/vendors/[id]` | View (read-only detail) |
| `/vendors/[id]/edit` | Edit form |
| `/login` | Login against Frappe |

### UI modules
- **VendorList** — table/cards, pagination, debounce search
- **VendorForm** — sections: Basic · Address · GST · Bank
- **VendorDetail** — same sections, view mode
- Shared: auth layout, toast errors, loading states

### Tech choices (draft)
- Next.js 15 App Router + TypeScript
- Tailwind CSS (+ optional shadcn/ui)
- Server Actions or Route Handlers calling Frappe REST
- Env: `FRAPPE_URL`, `FRAPPE_SITE_NAME`, API key/secret or cookie proxy

---

## 6. Frappe API Usage

### List
```http
GET /api/resource/Vendor?fields=["name","vendor_name","gstin","city","status"]&limit_page_length=20
```

### Create
```http
POST /api/resource/Vendor
Content-Type: application/json

{ "vendor_name": "...", "gstin": "...", ... }
```

### Get / Update
```http
GET  /api/resource/Vendor/{name}
PUT  /api/resource/Vendor/{name}
```

### Auth options
1. **Dev:** Cookie session via Next.js BFF (proxy login to Frappe)
2. **Service:** API Key + API Secret in server-only env (never expose to browser)
3. **Prod preferred:** Next.js Route Handlers as BFF; browser talks only to Next.js

---

## 7. Repository / Folder Layout (draft)

```
Frappe Apps/
├── docs/
│   └── VENDOR_DIRECTORY_DRAFT.md          # this file
├── docker-compose.yml
├── .env.example
├── apps/
│   └── vendor_directory/                  # Frappe custom app
│       ├── vendor_directory/
│       │   ├── doctype/vendor/
│       │   ├── api/
│       │   └── hooks.py
│       └── pyproject.toml / setup.py
└── frontend/
    └── vendor-web/                        # Next.js app
        ├── app/
        ├── components/
        ├── lib/frappe.ts
        ├── Dockerfile
        └── package.json
```

---

## 8. Docker Deployment Draft

### 8.1 Services

| Service | Image / build | Port | Role |
|---------|----------------|------|------|
| `backend` | frappe/erpnext (or frappe-bench custom) | 8000 | Frappe + site + `vendor_directory` |
| `db` | mariadb:10.6 | 3306 | Database |
| `redis-cache` | redis:alpine | 6379 | Cache |
| `redis-queue` | redis:alpine | 6379 | Jobs |
| `frontend` | build `./frontend/vendor-web` | 3000 | Next.js |
| `nginx` (optional) | nginx | 80/443 | Reverse proxy |

> Prefer official **[frappe_docker](https://github.com/frappe/frappe_docker)** patterns for bench, then add Next.js as an extra Compose service.

### 8.2 Single deployable stack (implemented)

`docker-compose.yml` now runs the full stack:

| Service | Role |
|---------|------|
| `db` | MariaDB 11.8 |
| `redis-cache` / `redis-queue` | Cache + jobs |
| `configurator` / `create-site` | Bench config + site bootstrap |
| `backend` / `websocket` / `queue-*` / `scheduler` | Frappe runtime |
| `frappe-nginx` | Desk on `:8080` |
| `vendor-web` | Next.js UI on `:3000` |
| `gateway` | Edge nginx on `:80` |

Custom image `vendor-directory-frappe` builds **plain Frappe** (`frappe/build` → `frappe/base`) and bakes in `apps/vendor_directory` — **no ERPNext**.  
`create-site` installs only `vendor_directory` and writes API credentials to the `credentials` volume for `vendor-web`.

```bash
cp .env.example .env
docker compose up --build -d
```

### 8.3 Next.js Dockerfile (sketch)

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

Enable `output: 'standalone'` in `next.config.ts`.

### 8.4 Environment (`.env.example`)

```env
# Frappe
FRAPPE_URL=http://localhost:8000
FRAPPE_SITE_NAME=vendors.localhost
FRAPPE_API_KEY=
FRAPPE_API_SECRET=

# Next.js
NEXT_PUBLIC_APP_NAME=Vendor Directory
# Do NOT put API secrets in NEXT_PUBLIC_*

# DB (frappe_docker)
DB_PASSWORD=change-me
MYSQL_ROOT_PASSWORD=change-me
```

### 8.5 Bootstrap steps (ops)

1. Clone / place this repo; copy `.env.example` → `.env`
2. Start Frappe stack (frappe_docker or local bench) and create site
3. `bench get-app` / mount `apps/vendor_directory` → `bench install-app vendor_directory`
4. Create API key for a service user (or configure SSO later)
5. `docker compose up -d --build` for frontend (+ full stack if unified compose)
6. Open `http://localhost:3000`

---

## 9. Security Notes

- Bank account / GSTIN: restrict by Frappe roles; mask in list views
- All mutations through authenticated Frappe API
- CORS: allow only Next.js origin; prefer BFF over browser→Frappe direct
- Secrets only in Docker env / secret store — not in git
- HTTPS + reverse proxy in production

---

## 10. Implementation Phases

| Phase | Deliverable |
|-------|-------------|
| **P0 — Draft** | This document + compose/env sketches |
| **P1 — Backend** | Frappe app + Vendor DocType + permissions + validators (GSTIN/IFSC) |
| **P2 — Frontend** | Next.js CRUD + auth BFF |
| **P3 — Docker** | Unified compose, healthchecks, nginx TLS sample |
| **P4 — Hardening** | Audit trail, attachments, export CSV, role matrix |

---

## 11. Open Decisions

1. **ERPNext vs plain Frappe?** **Plain Frappe** — stack builds from `frappe/build` + `frappe/base` with only `vendor_directory` (no ERPNext).
2. **Auth UX:** Frappe login proxy vs OAuth vs API key for internal tools.
3. **DB:** MariaDB (frappe_docker default) vs Postgres.
4. **Domain:** Single host (`app.example.com` + `api.example.com`) vs path-based proxy.

---

## 12. Next Actions

- [x] Confirm DocType fields (especially GST + bank)
- [x] Scaffold `vendor_directory` Frappe app
- [x] Scaffold Next.js `vendor-web`
- [x] Add `docker-compose` for frontend (use frappe_docker for full bench)
- [x] Wire single deployable stack (db + redis + frappe + Next.js + gateway)
- [ ] Smoke-test `docker compose up --build` on target host
- [ ] Define sample seed vendors
- [ ] Optional: TLS / traefik override for production domains

### Scaffold locations

| Piece | Path |
|--------|------|
| Frappe app | `apps/vendor_directory/` |
| Vendor DocType | `.../doctype/vendor/` |
| Next.js UI | `frontend/vendor-web/` |
| Compose | `docker-compose.yml` |

---

*Scaffold complete — wire to a running Frappe site next.*
