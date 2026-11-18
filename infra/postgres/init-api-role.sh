#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<'SQL'
\getenv api_password POSTGRES_API_PASSWORD
CREATE ROLE demoforge_api LOGIN NOINHERIT NOSUPERUSER NOBYPASSRLS PASSWORD :'api_password';
SQL
