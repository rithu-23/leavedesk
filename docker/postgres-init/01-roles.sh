#!/bin/bash
# Runs ONCE, when the postgres container starts with an empty data volume
# (files in /docker-entrypoint-initdb.d). To run it again: docker compose down -v
#
# Creates the two roles from SCHEMA.md section 6 and the test database:
#   leavedesk_migrator  owns the schema; runs Alembic (DDL allowed)
#   leavedesk_app       used by the API and the worker; data only, no DDL; timeouts set
# Passwords come from the environment (.env via docker-compose.yml), never from this file.
set -euo pipefail

: "${MIGRATOR_PASSWORD:?MIGRATOR_PASSWORD must be set}"
: "${APP_PASSWORD:?APP_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v migrator_password="$MIGRATOR_PASSWORD" -v app_password="$APP_PASSWORD" <<'SQL'
CREATE ROLE leavedesk_migrator LOGIN PASSWORD :'migrator_password';
CREATE ROLE leavedesk_app LOGIN PASSWORD :'app_password';

-- A stuck query or lock must never hang a request (SCHEMA.md 6, SPEC BR-10)
ALTER ROLE leavedesk_app SET statement_timeout = '5s';
ALTER ROLE leavedesk_app SET lock_timeout = '2s';
ALTER ROLE leavedesk_app SET idle_in_transaction_session_timeout = '10s';

CREATE DATABASE leavedesk_test;
SQL

# Same privileges in the main and the test database.
for db in "$POSTGRES_DB" leavedesk_test; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<'SQL'
ALTER DATABASE :"DBNAME" OWNER TO leavedesk_migrator;
REVOKE ALL ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO leavedesk_app;

ALTER SCHEMA public OWNER TO leavedesk_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO leavedesk_app;  -- USAGE only: no CREATE, so no DDL

-- Every table and sequence the migrator creates from now on is usable by the app.
-- Revisions take back UPDATE/DELETE on the append-only tables (SCHEMA.md 4.8, 4.9).
ALTER DEFAULT PRIVILEGES FOR ROLE leavedesk_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO leavedesk_app;
ALTER DEFAULT PRIVILEGES FOR ROLE leavedesk_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO leavedesk_app;
SQL
done

echo "leavedesk roles and databases ready"
