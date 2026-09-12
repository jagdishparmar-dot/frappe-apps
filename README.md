# Vendor Directory

**Frappe Desk** = admin (create vendors, register portal logins, review KYC)  
**Next.js Vendor Portal** = vendor self-service (login, update profile, upload KYC docs)

## Deploy on Coolify

See **[docs/COOLIFY_DEPLOY.md](docs/COOLIFY_DEPLOY.md)** — Coolify proxy assigns domains to `vendor-web` and `frappe-nginx`.

## Local quick start

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

| URL | Who |
|-----|-----|
| http://localhost/ | Vendor Portal (gateway) |
| http://localhost:3000 | Vendor Portal (direct) |
| http://localhost:8080 | Frappe Desk (admin) |

**Desk:** `Administrator` / `ADMIN_PASSWORD` (default in `.env.example` is `changeme`)

### Admin setup for a vendor

1. Desk → **Vendor** → New  
2. Save → **Create Portal User** (login email + password)  
3. Share credentials with the vendor  

### Vendor portal

1. Open http://localhost/login  
2. Sign in with portal login ID  
3. Update **My Profile**, upload **KYC Documents**, **Submit for KYC review**

## Layout

```
apps/vendor_directory/   # Frappe admin app + portal APIs
apps/vendor_billing/     # Frappe vendor billing Desk app
frontend/vendor-web/     # Vendor Portal (Next.js)
docker/                  # Images + nginx templates
docs/COOLIFY_DEPLOY.md   # Coolify production guide
docs/ADD_FRAPPE_CRM.md   # Install official Frappe CRM alongside this stack
docker-compose.yml       # Coolify / production compose
docker-compose.dev.yml   # Local ports + gateway overlay
```

## Optional: Frappe CRM

Set `INSTALL_CRM=1` (default) and rebuild — see [docs/ADD_FRAPPE_CRM.md](docs/ADD_FRAPPE_CRM.md). CRM UI: `/crm` on the Desk domain.