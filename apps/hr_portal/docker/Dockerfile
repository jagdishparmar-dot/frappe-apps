# Production image: bench + hr_portal + CRM with frontends built at image build time.
# Runtime only creates/migrates the site and starts processes — no yarn/pip/get-app loops.
# syntax=docker/dockerfile:1

ARG FRAPPE_BRANCH=version-16
ARG CRM_BRANCH=main

FROM frappe/bench:latest AS builder

ARG FRAPPE_BRANCH
ARG CRM_BRANCH
ENV BENCH_DIR=/home/frappe/frappe-bench

USER frappe
WORKDIR /home/frappe

RUN bench init frappe-bench \
	--frappe-branch "${FRAPPE_BRANCH}" \
	--python python3.14 \
	--skip-redis-config-generation \
	--ignore-exist

WORKDIR /home/frappe/frappe-bench

RUN bench get-app --branch "${CRM_BRANCH}" crm

COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/hr_portal
COPY --chown=frappe:frappe docker/Procfile.prod ./Procfile

RUN ./env/bin/pip install -q -e apps/hr_portal -e apps/crm

RUN cd apps/hr_portal/frontend \
	&& yarn install --frozen-lockfile \
	&& yarn build

RUN cd apps/crm/frontend \
	&& yarn install --frozen-lockfile \
	&& NODE_OPTIONS="--max-old-space-size=4096" yarn build

RUN mkdir -p sites/assets \
	&& ln -sfn "${BENCH_DIR}/apps/hr_portal/hr_portal/public" sites/assets/hr_portal \
	&& ln -sfn "${BENCH_DIR}/apps/crm/crm/public" sites/assets/crm \
	&& printf 'frappe\nhr_portal\ncrm\n' > sites/apps.txt

FROM frappe/bench:latest AS runtime

USER root
COPY docker/frappe-entrypoint.sh /usr/local/bin/frappe-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/frappe-entrypoint.sh \
	&& chmod +x /usr/local/bin/frappe-entrypoint.sh

USER frappe
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench
ENV BENCH_DIR=/home/frappe/frappe-bench \
	FRAPPE_ENV=production \
	MIGRATE_ON_START=1 \
	SEED_DEMO_DATA=0 \
	BUILD_ASSETS_ON_START=0

ENTRYPOINT ["/usr/local/bin/frappe-entrypoint.sh"]
CMD ["start"]
