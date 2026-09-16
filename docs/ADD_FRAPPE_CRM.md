# Adding apps (Frappe CRM, custom apps) via the `apps/` folder

This stack no longer fetches apps from GitHub at build time. **Every app folder
under `./apps` is baked into the image, built, and installed on the site
automatically** — no Dockerfile, compose, or `create-site.sh` changes needed.

Current apps:

| App | Role |
|-----|------|
| `vendor_billing` | Vendors, agreements, invoices, KYC (Desk + portal APIs) |
| `hr_portal` | HR + attendance SPA at `/hr` (custom Vue frontend, same pattern as CRM) |
| `bench_control` | Bench control plane UI at `/control` (sites + apps; System Manager) |

They share one Frappe site by default. Use `INSTALL_APPS` / `CONTROL_SITE_NAME` to put
`bench_control` on a dedicated site if you prefer.

---

## Add an app

1. Put the app in `apps/` — folder name must equal the app name:

   ```bash
   # example: Frappe CRM
   git clone https://github.com/frappe/crm apps/crm        # or: git submodule add ...
   ```

2. Rebuild and redeploy:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
   ```

That's it. The image build pip-installs every `apps/*` folder that has a
`pyproject.toml`, builds its assets, and `create-site` runs
`install-app <name>` + `migrate` on the site (idempotent — safe on redeploys).

### App requirements (the contract)

- Folder name = app name (`apps/hr_portal` → app `hr_portal`).
- `pyproject.toml` present (standard bench app layout).
- **Custom frontend / SPA:** add a root `package.json` with a `build` script —
  `bench build` then builds it automatically (same as `hr_portal` and `crm`):

  ```json
  {
    "private": true,
    "scripts": {
      "postinstall": "cd frontend && yarn install --check-files",
      "build": "cd frontend && yarn build"
    }
  }
  ```

  Also commit a minimal `yarn.lock` so the build's
  `yarn install --frozen-lockfile` succeeds (see `apps/hr_portal/yarn.lock`).

### Removing an app

Delete the folder from `apps/`, rebuild — **but first uninstall it from the
site** or `migrate` will fail on the missing app code:

```bash
docker compose exec backend bench --site <site> uninstall-app <app> --yes --no-backup
```

> **One-time note for sites that had CRM:** CRM was previously fetched from
> GitHub and installed by default. Before deploying the apps-folder image to an
> existing site, run `uninstall-app crm` as above (this drops CRM tables).
> To keep using CRM, move it into `apps/crm` instead — then nothing changes.

---

## After install

| URL | App |
|-----|-----|
| `https://desk…/app` | Desk (Vendor Billing workspace) |
| `https://desk…/hr` | HR Portal SPA |
| `https://desk…/crm` | Frappe CRM SPA (if `apps/crm` present) |

---

## Notes

- **ERPNext** is not required for CRM core. Optional ERPNext hooks activate only if ERPNext is installed later.
- **Vendor ↔ CRM linking** (e.g. Vendor → CRM Organization) is not automatic; add custom fields/links later if you need that.
- Large third-party apps (CRM) make image builds slower (Node frontend assets) — the yarn cache mount keeps rebuilds fast.
