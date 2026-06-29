#!/bin/sh
set -eu

: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

export PGHOST="$POSTGRES_HOST"
export PGPORT="$POSTGRES_PORT"
export PGDATABASE="$POSTGRES_DB"
export PGUSER="$POSTGRES_USER"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGSSLMODE="${POSTGRES_SSLMODE:-require}"

echo "Applying database schema to $PGHOST:$PGPORT/$PGDATABASE"
psql --set ON_ERROR_STOP=1 --file ./01_schema.sql

echo "Applying seed data to $PGHOST:$PGPORT/$PGDATABASE"
psql --set ON_ERROR_STOP=1 --file ./02_seed.sql

echo "Database initialization complete."
