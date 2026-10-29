# Bench image for the unit_tests CI job: Frappe, ERPNext and HRMS on
# version-15, plus the MariaDB client wrapper. Built by build.sh.

FROM frappe/bench:latest

ARG FRAPPE_BRANCH=version-15
# The image's default Python can be newer than phamos supports (<3.14).
ARG PYTHON_VERSION=3.11
WORKDIR /home/frappe

# Bench with Frappe, ERPNext and HRMS; assets are not needed for tests.
# Without assets.json, rendering web pages fails in bundled_asset().
# --junit-xml-output imports xmlrunner, a Frappe dev dependency the bench image does not ship.
RUN bench init --frappe-branch "$FRAPPE_BRANCH" --python "$PYTHON_VERSION" \
      --skip-redis-config-generation --skip-assets frappe-bench \
 && cd frappe-bench \
 && bench get-app --branch "$FRAPPE_BRANCH" --skip-assets erpnext \
 && bench get-app --branch "$FRAPPE_BRANCH" --skip-assets hrms \
 && mkdir -p sites/assets && echo '{}' > sites/assets/assets.json \
 && bench set-config -g db_host mariadb \
 && bench set-config -g db_port 3306 \
 && bench set-config -g redis_cache redis://redis-cache:6379 \
 && bench set-config -g redis_queue redis://redis-queue:6379 \
 && bench set-config -g redis_socketio redis://redis-queue:6379 \
 && ./env/bin/pip install "unittest-xml-reporting~=3.2.0"

# The MariaDB 11 client in frappe/bench requires TLS. The 10.6 service has no
# certificates, so the client exits with ERROR 2026. bench execs mariadb directly
# and does not pass --skip-ssl, so put a wrapper first on PATH.
RUN mkdir -p /home/frappe/bin \
 && for cmd in mariadb mysql mariadb-dump mysqldump; do \
      real="$(command -v "$cmd" || true)"; \
      [ -n "$real" ] || continue; \
      printf '#!/bin/sh\nexec %s --skip-ssl "$@"\n' "$real" > "/home/frappe/bin/$cmd"; \
      chmod +x "/home/frappe/bin/$cmd"; \
    done \
 && printf '[client]\nskip-ssl\n[mysql]\nskip-ssl\n[mariadb]\nskip-ssl\n' > /home/frappe/.my.cnf \
 && chmod 600 /home/frappe/.my.cnf
ENV PATH=/home/frappe/bin:$PATH

WORKDIR /home/frappe/frappe-bench
