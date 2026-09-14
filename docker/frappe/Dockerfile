# syntax=docker/dockerfile:1
# Plain Frappe + every app found in ./apps (vendor_billing, hr_portal, ...)
#
# To add an app: drop its folder into apps/ (folder name = app name, with a
# pyproject.toml). No Dockerfile / compose / create-site changes needed.
# To add Frappe CRM later: clone it into apps/crm (it builds like any other app).
#
# Layer order = rarely-changing → frequently-changing, so app code edits only
# rebuild the cheap layers (Frappe itself is never re-cloned or re-built).
ARG FRAPPE_VERSION=v16
FROM frappe/build:${FRAPPE_VERSION} AS builder

ARG FRAPPE_BRANCH=version-16
ARG FRAPPE_PATH=https://github.com/frappe/frappe
ARG FRAPPE_VERSION=v16

USER frappe

# 1) Bench init WITHOUT assets (--skip-assets) — every asset is built exactly
#    once in the layers below. Cached unless FRAPPE_* args change.
RUN bench init \
  --frappe-branch=${FRAPPE_BRANCH} \
  --frappe-path=${FRAPPE_PATH} \
  --no-procfile \
  --no-backups \
  --skip-redis-config-generation \
  --skip-assets \
  --verbose \
  /home/frappe/frappe-bench \
  && cd /home/frappe/frappe-bench \
  && echo "{}" > sites/common_site_config.json \
  && find apps -mindepth 1 -path "*/.git" | xargs rm -fr

# 2) Frappe Desk assets — own layer: local app changes never rebuild these.
RUN cd /home/frappe/frappe-bench && bench build --apps frappe

# 3) Local apps — one wildcard copy; everything below is cheap on code changes.
COPY --chown=frappe:frappe apps/ /home/frappe/frappe-bench/apps/

# 4) Install every app in apps/ + build all assets in ONE bench build:
#    - Any folder with a pyproject.toml is pip-installed (folder name = app name).
#    - apps.txt is synced BEFORE the build so bench links every app's public/
#      dir into sites/assets (baked into the image below) — without this,
#      /assets/<app>/... would 404 at runtime.
#    - Apps with a root package.json "build" script (hr_portal, crm, ...) get
#      their frontend built by esbuild's run_build_command_for_apps (yarn cache
#      mount keeps dependency installs fast on rebuilds).
#    - App node_modules are deleted after the build: only the built assets are
#      needed at runtime (apps/frappe/node_modules stays — socketio.js needs it).
RUN --mount=type=cache,target=/home/frappe/.cache/yarn,uid=1000,gid=1000 \
    cd /home/frappe/frappe-bench \
  && for app in $(ls -1 apps); do \
       [ "${app}" = "frappe" ] && continue; \
       [ -f "apps/${app}/pyproject.toml" ] || { echo "Skipping ${app}: no pyproject.toml"; continue; }; \
       echo "Installing app: ${app}"; \
       ./env/bin/pip install --quiet --no-cache-dir -e "apps/${app}"; \
     done \
  && ls -1 apps > sites/apps.txt \
  && bench_build_apps="$(ls -1 apps | grep -v '^frappe$' | paste -sd, -)" \
  && echo "Building assets for apps: ${bench_build_apps}" \
  && bench build --apps "${bench_build_apps}" \
  && for app in $(ls -1 apps); do \
       [ "${app}" = "frappe" ] && continue; \
       rm -rf "apps/${app}/node_modules" "apps/${app}/frontend/node_modules"; \
     done \
  && find apps -mindepth 1 -path "*/.git" | xargs rm -fr || true

FROM frappe/base:${FRAPPE_VERSION} AS backend

USER frappe

COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

RUN cp -r /home/frappe/frappe-bench/sites/assets /home/frappe/frappe-bench/assets \
  && rm -rf /home/frappe/frappe-bench/sites/assets

VOLUME [ \
  "/home/frappe/frappe-bench/sites", \
  "/home/frappe/frappe-bench/logs" \
]

USER root
COPY --chmod=755 docker/frappe/resources/main-entrypoint.sh /usr/local/bin/entrypoint.sh
COPY --chmod=755 docker/frappe/resources/start.sh /usr/local/bin/start.sh
COPY --chmod=755 --chown=frappe:frappe docker/frappe/create-site.sh /home/frappe/create-site.sh
# Bake nginx template into the image (avoid Coolify bind-mount file→dir issues)
COPY docker/frappe/nginx/frappe.conf.template /templates/nginx/frappe.conf.template

USER frappe
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["start.sh"]
