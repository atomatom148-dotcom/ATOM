#!/usr/bin/env bash
# Idempotent Cloud Agent install for ATOM V9 Thin.
# Prepares the Python quant pipeline and a local PostgreSQL server so the full
# CI test suite (including the DB-backed integration tests) can run.
set -euo pipefail

# 1) System: PostgreSQL server for DB-backed integration tests. CI runs these
#    against an ephemeral postgres:16 service; we install a local server so the
#    same tests run here. Skip the apt work when a cluster is already present
#    (e.g. when booting from a prebuilt environment snapshot).
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postgresql postgresql-contrib
fi

# 2) Python dependencies pinned by requirements.txt, plus pytest (matches CI).
python3 -m pip install --user -r requirements.txt pytest

# 3) Expose the disposable test-database URLs to agent shells, mirroring CI's
#    H2C_TEST_DATABASE_URL job variable. The dedicated `atom_test` database is
#    reset to an empty state on every boot by .cursor/start.sh. Guarded so the
#    block is written at most once.
BASHRC="$HOME/.bashrc"
MARKER="# >>> ATOM V9 Thin test database URLs >>>"
if ! grep -qF "$MARKER" "$BASHRC" 2>/dev/null; then
  {
    echo "$MARKER"
    echo 'export H2C_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/atom_test"'
    echo 'export POSTGRES_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/atom_test"'
    echo "# <<< ATOM V9 Thin test database URLs <<<"
  } >> "$BASHRC"
fi
