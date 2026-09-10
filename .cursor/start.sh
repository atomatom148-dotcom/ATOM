#!/usr/bin/env bash
# Idempotent per-boot startup for ATOM V9 Thin.
# Brings up the local PostgreSQL server and resets a disposable, empty
# `atom_test` database so the DB-backed integration tests (which require an
# empty database, exactly like CI's ephemeral postgres service) pass on a
# fresh boot.
set -euo pipefail

# Locate the installed cluster (version/name) dynamically.
read -r PG_VER PG_CLUSTER PG_STATUS < <(pg_lsclusters -h | awk '{print $1, $2, $4}')
: "${PG_VER:?no PostgreSQL cluster found}"
: "${PG_CLUSTER:?no PostgreSQL cluster found}"

# Start the cluster only if it is not already online (idempotent).
if [ "${PG_STATUS:-down}" != "online" ]; then
  sudo pg_ctlcluster "$PG_VER" "$PG_CLUSTER" start
fi

# Wait for the server to accept connections.
for _ in $(seq 1 30); do
  if pg_isready -q; then break; fi
  sleep 1
done
pg_isready

# Ensure the `postgres` login has the password the test URLs expect, then reset
# the disposable test database to a pristine, empty state. Dropping the database
# first removes objects owned by roles created by the migrations/tests, so the
# subsequent role cleanup succeeds; the tests re-create everything they need.
sudo -u postgres psql -v ON_ERROR_STOP=1 -d postgres <<'SQL'
ALTER USER postgres PASSWORD 'postgres';
DROP DATABASE IF EXISTS atom_test;
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT rolname FROM pg_roles
    WHERE rolname NOT LIKE 'pg\_%' AND rolname <> 'postgres'
  LOOP
    EXECUTE format('DROP OWNED BY %I CASCADE', r.rolname);
    EXECUTE format('DROP ROLE IF EXISTS %I', r.rolname);
  END LOOP;
END $$;
CREATE DATABASE atom_test;
SQL

echo "PostgreSQL cluster ${PG_VER}/${PG_CLUSTER} online; atom_test reset to empty."
