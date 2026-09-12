# Adding Frappe CRM with Vendor Directory

[Frappe CRM](https://github.com/frappe/crm) is the official open-source CRM. It runs on **plain Frappe v15/v16** (ERPNext is optional for extra integrations).

This stack can install custom apps and CRM on the same site:

| App | Role |
|-----|------|
| `vendor_directory` | Vendor master, portal users, KYC (Desk + Next.js portal) |
| `vendor_billing` | Vendor billing Desk app (agreements, invoices, KYC workflow) |
| `crm` | Leads / Deals / CRM UI at `/crm` |

They share one Frappe site, one DB, and the same Desk login.

---

## How it is wired

1. **Image build** (`docker/frappe/Dockerfile`)  
   - Always copies/installs `vendor_directory` and `vendor_billing`  
   - If `INSTALL_CRM=1` (default): `bench get-app crm` + build CRM frontend assets  

2. **Site bootstrap** (`docker/frappe/create-site.sh`)  
   - New site: `--install-app vendor_directory --install-app vendor_billing --install-app crm`  
   - Existing site: `install-app` each app (idempotent) + `migrate`  

3. **Compose / Coolify env**  
   - `INSTALL_CRM=1` (build arg + runtime)  
   - `CRM_BRANCH=main` (stable for Frappe v16)

---

## Enable / rebuild

### Local

```bash
# .env
INSTALL_CRM=1
CRM_BRANCH=main

docker compose -f docker-compose.yml -f docker-compose.dev.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Coolify

1. Set env: `INSTALL_CRM=1`, `CRM_BRANCH=main`  
2. **Rebuild** the Frappe image (required — CRM is baked into the image)  
3. Redeploy so `create-site` installs/migrates `crm` on the site  

First CRM build is slower (Node frontend assets).

---

## After install

| URL | App |
|-----|-----|
| `https://desk…/app` | Desk (Vendor Directory + Vendor Billing workspaces) |
| `https://desk…/crm` | Frappe CRM SPA |
| `https://portal…` | Vendor Portal (unchanged) |

Desk apps switcher should list **CRM**, **Vendor Directory**, and **Vendor Billing**.

---

## Disable CRM

```bash
INSTALL_CRM=0
```

Rebuild the image. Existing sites keep CRM data unless you uninstall:

```bash
bench --site <site> uninstall-app crm
```

---

## Notes

- **ERPNext** is not required for CRM core. Optional ERPNext hooks activate only if ERPNext is installed later.  
- **Vendor ↔ CRM linking** (e.g. Vendor → CRM Organization) is not automatic; add custom fields/links later if you need that.  
- Existing Coolify volumes: rebuild image, then redeploy — `create-site` will `install-app crm` on the existing site.  
