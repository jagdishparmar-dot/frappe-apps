# Bench Control

Frappe app that manages **sites** and **apps** on the shared Docker bench.

- UI: `/control` (System Manager / Bench Manager)
- Create / drop / rename / clone sites; set default site
- Install apps (single or multi-site), migrate (single + all)
- Backup / restore, clear cache, maintenance mode
- Reset Administrator password, host_name, safe site config
- Health, disk/DB size, app catalog versions, queue depth
- Error log viewer, job filters, create presets, live job logs

## Local

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
# http://vendors.localhost:8080/control  (Administrator / ADMIN_PASSWORD)
```

Rebuild the image before Coolify so API + UI assets are baked into nginx/backend.
New app **code** still requires putting a folder in `./apps` and rebuilding.
