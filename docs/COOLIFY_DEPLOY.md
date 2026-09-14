# Deploy Vendor Billing + HR Portal on Coolify

This stack runs **Frappe Desk** behind Coolify’s proxy (Traefik/Caddy). Coolify assigns a domain and TLS.
The same domain also serves the **HR Portal SPA** at `/hr` and (optionally) **Frappe CRM** at `/crm`.

| Coolify service | Role | Internal port |
|-----------------|------|----------------|
| **frappe-nginx** | Frappe Desk + HR SPA (`/hr`) + API + socket.io | `8080` |

Everything else (`db`, Redis, `backend`, workers, websocket, scheduler) stays **private** — do not attach domains to them.

---

## 1. Prerequisites

- Coolify server with Docker (proxy enabled)
- Git repo with this project (Coolify **Docker Compose** build pack)
- One DNS record pointing at the Coolify server:
  - `desk.yourdomain.com` → Frappe Desk
- At least **4 GB RAM** recommended (Frappe image build is heavy)

---

## 2. Create the resource

1. Coolify → **Project** → **Add Resource** → **Docker Compose** (from Git)
2. Select this repository and branch
3. Compose file: `docker-compose.yml` (default — **not** `docker-compose.dev.yml`)
4. Save / parse the compose file so Coolify lists all services

---

## 3. Set environment variables (before first deploy)

In Coolify → **Environment Variables**, set at least:

| Variable | Example | Notes |
|----------|---------|--------|
| `MYSQL_ROOT_PASSWORD` | long random secret | MariaDB root |
| `ADMIN_PASSWORD` | long random secret | Frappe `Administrator` |
| `FRAPPE_SITE_NAME` | `desk.yourdomain.com` | **Must equal Desk hostname** (no `https://`) |
| `SITE_HOST_NAME` | `https://desk.yourdomain.com` | Public HTTPS origin for Frappe |
| `FRAPPE_VERSION` | `v16` | Optional |
| `FRAPPE_BRANCH` | `version-16` | Optional |

### Critical: site name = Desk domain

Frappe’s site folder is named after `FRAPPE_SITE_NAME`. Nginx and socket.io also use that hostname.

- Set `FRAPPE_SITE_NAME` / `SITE_HOST_NAME` to the **final Desk domain before the first successful `create-site` run**.
- Changing the Desk domain later usually means recreating the `sites` volume (data loss) or a manual site migration.

`SITE_HOST_NAME` must be a **full** URL (`https://desk.yourdomain.com`). Do not leave it as bare `https://` — that breaks Coolify URL parsing and Frappe config.

---

## 4. Assign domains in Coolify

After Coolify parses the stack:

1. Open service **frappe-nginx** → Domains → `https://desk.yourdomain.com` → port **8080**

Ensure WebSocket / HTTPS is allowed for the Desk domain (Coolify proxy handles `/socket.io` on the same host).

Compose publishes container port `8080` without binding a fixed host port, so Coolify’s proxy can route to it.

---

## 5. Deploy

1. Click **Deploy**
2. First build can take **10–30+ minutes** (Frappe bench init + assets)
3. Watch logs for:
   - `configurator` completed
   - `create-site` → `Site bootstrap complete`
   - `backend` / `frappe-nginx` healthy

### First-boot checklist

| Check | How |
|-------|-----|
| Desk | `https://desk.yourdomain.com` → login `Administrator` / `ADMIN_PASSWORD` |
| HR Portal SPA | `https://desk.yourdomain.com/hr` → login with a user that has an HR role |
| API ping | `https://desk.yourdomain.com/api/method/ping` → `{"message":"pong"}` |

---

## 6. Post-deploy admin steps

1. Desk → **Vendor Billing** → create vendors, agreements, invoices  
2. Review KYC and payment workflow in Desk  
3. HR Portal → open `/hr` (users need an HR role: HR Admin / HR Manager / HR Employee, assigned in Desk → User)  

---

## 7. Architecture (Coolify)

```
Internet
   │
   ▼
Coolify Proxy (TLS)
   └── desk.yourdomain.com    →  frappe-nginx:8080
                                    ├── backend:8000
                                    └── websocket:9000
                                         │
                              db / redis-cache / redis-queue
```

---

## 8. Volumes / persistence

Coolify keeps named volumes across redeploys:

| Volume | Data |
|--------|------|
| `db-data` | MariaDB |
| `sites` | Frappe sites, files, credentials |
| `redis-queue-data` | Queue persistence |
| `logs` | Bench logs |

Back up **`db-data` + `sites`** before major upgrades.

---

## 9. Updates / redeploy

1. Push to Git (or trigger Coolify redeploy)
2. Image rebuilds if Dockerfile / app code changed
3. `create-site` is idempotent: existing site → migrate only  
4. After code changes to the Frappe app, ensure migrate ran (check `create-site` / `backend` logs)

> **One-time migration — CRM removal:** the image no longer fetches Frappe CRM
> from GitHub. If the site previously had `crm` installed, uninstall it **before**
> the first deploy of this image, or `migrate` will fail on the missing app code:
>
> ```bash
> docker compose exec backend bench --site <site> uninstall-app crm --yes --no-backup
> ```
>
> (Drops CRM tables. To keep CRM, add it as `apps/crm` instead — see
> [ADD_FRAPPE_CRM.md](ADD_FRAPPE_CRM.md).)

---

## 10. Local development

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

| URL | Service |
|-----|---------|
| http://localhost:8080 | Desk |

Keep `FRAPPE_SITE_NAME=vendors.localhost` locally.

---

## 11. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Desk blank / wrong site | `FRAPPE_SITE_NAME` ≠ domain Host header. Align both; recreate `sites` if created with wrong name. |
| Socket.io / realtime errors | Desk domain must serve `/socket.io`; Host/Origin use `FRAPPE_SITE_NAME`. |
| 502 / No Available Server | Service unhealthy or wrong port on Coolify domain (must be 8080). |
| Build OOM | Use a larger Coolify server or remote build server. |
| `create-site` stuck | Check `db` healthy + Redis; inspect `create-site` logs. |
| `The string https:// is no valid url` | Incomplete Coolify/env URL. Set full `SITE_HOST_NAME=https://desk…` (or leave empty until domains exist). Redeploy after pulling latest compose (empty `SERVICE_URL_*` magic vars were removed). |
| `mount ... frappe.conf.template ... not a directory` | Fixed by baking the nginx template into the image (no file bind-mount). Redeploy/rebuild from latest `main`. |
| `backend` unhealthy on first boot | Normal — Gunicorn preloads the app before forking workers (can take 60-90s). The `start_period: 90s` healthcheck gives it enough time. If still failing after 90s, check `docker compose logs backend`. |
| `frappe-nginx` never starts | Depends on `backend: service_healthy`. If backend healthcheck fails, nginx is blocked. Fix backend first. |
| Memory limit errors (`OOMKilled`) | Increase `BACKEND_MEM_LIMIT` / `DB_MEM_LIMIT` in Coolify env vars. Default limits suit a 4 GB server. |
| Workers consuming too much CPU | Set `GUNICORN_WORKERS=N` to cap worker count. Default is `2×nproc+1`; lower it if co-hosting other services. |

### Force site recreate (destructive)

Only if you must change `FRAPPE_SITE_NAME` and accept data loss:

1. Stop the stack in Coolify  
2. Remove volumes `sites` and optionally `db-data`  
3. Set correct env vars  
4. Deploy again  

---

## 12. Security checklist

- [ ] Strong `MYSQL_ROOT_PASSWORD` and `ADMIN_PASSWORD`  
- [ ] Desk on an HTTPS domain  
- [ ] No domains on DB / Redis / backend  
- [ ] Restrict who can access Desk (VPN / IP allowlist / SSO if needed)  

---

## Reference links

- [Coolify Docker Compose build pack](https://coolify.io/docs/applications/build-packs/docker-compose)  
- [Coolify domains](https://coolify.io/docs/knowledge-base/domains)  
