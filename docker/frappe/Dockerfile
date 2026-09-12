# Plain Frappe + vendor_directory + vendor_billing (+ optional Frappe CRM)
ARG FRAPPE_VERSION=v16
FROM frappe/build:${FRAPPE_VERSION} AS builder

ARG FRAPPE_BRANCH=version-16
ARG FRAPPE_PATH=https://github.com/frappe/frappe
ARG FRAPPE_VERSION=v16
# Frappe CRM (https://github.com/frappe/crm) — main is stable for Frappe v15/v16
ARG CRM_BRANCH=main
ARG INSTALL_CRM=1

USER frappe

RUN bench init \
  --frappe-branch=${FRAPPE_BRANCH} \
  --frappe-path=${FRAPPE_PATH} \
  --no-procfile \
  --no-backups \
  --skip-redis-config-generation \
  --verbose \
  /home/frappe/frappe-bench \
  && cd /home/frappe/frappe-bench \
  && echo "{}" > sites/common_site_config.json \
  && find apps -mindepth 1 -path "*/.git" | xargs rm -fr

COPY --chown=frappe:frappe apps/vendor_directory /home/frappe/frappe-bench/apps/vendor_directory
COPY --chown=frappe:frappe apps/vendor_billing /home/frappe/frappe-bench/apps/vendor_billing

RUN cd /home/frappe/frappe-bench \
  && ./env/bin/pip install --quiet --no-cache-dir -e apps/vendor_directory \
  && ./env/bin/pip install --quiet --no-cache-dir -e apps/vendor_billing \
  && if [ "${INSTALL_CRM}" = "1" ]; then \
       bench get-app crm https://github.com/frappe/crm --branch "${CRM_BRANCH}" \
       && ./env/bin/pip install --quiet --no-cache-dir -e apps/crm \
       && bench build --app frappe --app vendor_billing --app crm; \
     else \
       bench build --app frappe --app vendor_billing; \
     fi \
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
COPY --chown=frappe:frappe docker/frappe/write-api-credentials.py /home/frappe/write-api-credentials.py
# Bake nginx template into the image (avoid Coolify bind-mount file→dir issues)
COPY docker/frappe/nginx/frappe.conf.template /templates/nginx/frappe.conf.template

USER frappe
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["start.sh"]
