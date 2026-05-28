#!/bin/sh
# Provision Miniflux's database & user inside the shared Niouzou Postgres.
# Postgres runs scripts from /docker-entrypoint-initdb.d/ once, on the first
# boot of an empty data dir.
#
# Miniflux owns its own database, so it can CREATE EXTENSION hstore at boot.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER miniflux WITH PASSWORD '${MINIFLUX_DB_PASSWORD:-miniflux}';
    CREATE DATABASE miniflux OWNER miniflux;
EOSQL
