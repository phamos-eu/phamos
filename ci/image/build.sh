#!/usr/bin/env bash
# Builds and pushes the image the unit_tests CI job runs in.
#
# Run on an arm64 host (the "hetzner" runner is arm64), after `docker login`
# to the GitLab registry:
#   REGISTRY_IMAGE=<registry>/phamos/phamos bash ci/image/build.sh
# Then set CI_BENCH_TAG in .gitlab-ci.yml to the tag printed at the end.
set -euo pipefail

: "${REGISTRY_IMAGE:?Set REGISTRY_IMAGE to the project registry path shown under Deploy > Container Registry}"
IMAGE="$REGISTRY_IMAGE/ci-bench"
TAG="v15-$(date +%Y%m%d)"
NET=phamos-ci-seed

cd "$(dirname "$0")"

# 1. Bench image. --no-cache so bench init fetches the latest version-15.
docker build --pull --no-cache -t phamos-ci-bench:base -f Dockerfile .

# 2. Fresh site on the same services as CI, saved to ./out.
rm -rf out && mkdir out && chmod 777 out
docker network create "$NET"
trap 'docker rm -f seed-mariadb seed-redis-cache seed-redis-queue >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true' EXIT
docker run -d --name seed-mariadb --network "$NET" --network-alias mariadb \
	-e MARIADB_ROOT_PASSWORD=root mariadb:10.6 \
	--character-set-server=utf8mb4 --collation-server=utf8mb4_unicode_ci
docker run -d --name seed-redis-cache --network "$NET" --network-alias redis-cache redis:7-alpine
docker run -d --name seed-redis-queue --network "$NET" --network-alias redis-queue redis:7-alpine

# Installing phamos needs the UOM "Hour", the tests need e.g. "Nos" and
# "All Item Groups": master data the ERPNext setup wizard would create.
# Same time zone as the container: without one Frappe assumes Asia/Kolkata.
docker run --rm --network "$NET" -v "$PWD/out:/out" phamos-ci-bench:base bash -euo pipefail -c '
	until mariadb -hmariadb -uroot -proot -e "SELECT 1" >/dev/null 2>&1; do sleep 2; done
	bench new-site test.localhost --db-name test_site --db-password test_site \
		--db-root-password root --mariadb-root-username root --mariadb-root-password root \
		--admin-password admin --mariadb-user-host-login-scope="%"
	bench --site test.localhost install-app erpnext
	bench --site test.localhost install-app hrms
	bench --site test.localhost execute erpnext.setup.setup_wizard.operations.install_fixtures.install --kwargs "{\"country\": \"Germany\"}"
	bench --site test.localhost execute frappe.db.set_single_value --args "[\"System Settings\", \"time_zone\", \"UTC\"]"
	bench --site test.localhost set-config allow_tests true
	mariadb-dump -hmariadb -uroot -proot --single-transaction --routines test_site | gzip > /out/seed.sql.gz
	tar -C sites -czf /out/site.tgz test.localhost
'

# 3. Final image with the saved site, then push.
docker build -t "$IMAGE:$TAG" -f Dockerfile.seed .
docker push "$IMAGE:$TAG"
echo "Pushed $IMAGE:$TAG"
echo "Set CI_BENCH_TAG: \"$TAG\" in .gitlab-ci.yml"
