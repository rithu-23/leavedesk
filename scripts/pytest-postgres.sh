#!/bin/bash
# Run the whole test suite against the PostgreSQL test database (SPEC DB-1).
# Needs: docker compose up -d db, and TEST_DATABASE_URL / TEST_MIGRATION_DATABASE_URL in .env.
# Extra arguments go to pytest, e.g.  scripts/pytest-postgres.sh tests/api -q
set -euo pipefail
cd "$(dirname "$0")/.."

TEST_DATABASE_URL=$(grep -E '^TEST_DATABASE_URL=' .env | cut -d= -f2-)
if [[ -z "$TEST_DATABASE_URL" ]]; then
  echo "TEST_DATABASE_URL is missing from .env" >&2
  exit 1
fi

DATABASE_URL="$TEST_DATABASE_URL" exec python -m pytest "$@"
