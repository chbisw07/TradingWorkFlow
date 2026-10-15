#!/usr/bin/env bash
# Private disposable PostgreSQL cluster: never reads deployment credentials.
set -euo pipefail
repo_root=$(cd -- "$(dirname -- "$0")/.." && pwd)
pg_bin=${TWF_PG_BINDIR:-$(pg_config --bindir)}
cluster=$(mktemp -d /tmp/twf-pg-test.XXXXXX)
cleanup() {
  "$pg_bin/pg_ctl" -D "$cluster/data" -m immediate stop >/dev/null 2>&1 || true
  rm -rf -- "$cluster"
}
trap cleanup EXIT INT TERM
"$pg_bin/initdb" -D "$cluster/data" -A trust -U twf_test --no-locale -E UTF8 >"$cluster/init.log"
# Private Unix socket only; trust authentication is never exposed over TCP.
"$pg_bin/pg_ctl" -D "$cluster/data" -l "$cluster/server.log" -o "-k $cluster -h '' -p 55439" start >/dev/null
"$pg_bin/createdb" -h "$cluster" -p 55439 -U twf_test twf_test_db1
export TWF_TEST_DATABASE_URL="postgresql+psycopg://twf_test@/twf_test_db1?host=$cluster&port=55439"
if [[ "${1:-}" == "--browser" ]]; then
  shift
  export TWF_BROWSER_POSTGRES_URL="$TWF_TEST_DATABASE_URL"
  cd "$repo_root/apps/web"
  npx playwright test "$@"
else
  cd "$repo_root/apps/api"
  .venv/bin/python -m pytest --db-backend=postgres "$@"
fi
