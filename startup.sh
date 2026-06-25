#!/bin/bash
# Azure App Service startup — persistent data dirs + optional one-time migration.
# Portal: Configuration → General settings → Startup Command = bash startup.sh
set -euo pipefail

DB_PATH="${DATABASE_PATH:-/home/data/mine.db}"
UPLOAD_DIR="${UPLOAD_FOLDER:-/home/data/uploads}"
WWWROOT="/home/site/wwwroot"
PORT="${PORT:-8000}"

mkdir -p "$(dirname "$DB_PATH")"
mkdir -p "$UPLOAD_DIR"

# One-time migration from default wwwroot paths (no-op if persistent data already exists).
if [ -f "$WWWROOT/mine.db" ] && [ ! -f "$DB_PATH" ]; then
  echo "MiNe: migrating database to $DB_PATH"
  cp "$WWWROOT/mine.db" "$DB_PATH"
fi

if [ -d "$WWWROOT/uploads" ]; then
  shopt -s nullglob
  www_files=( "$WWWROOT/uploads/"* )
  if [ "${#www_files[@]}" -gt 0 ] && [ -z "$(ls -A "$UPLOAD_DIR" 2>/dev/null || true)" ]; then
    echo "MiNe: migrating uploads to $UPLOAD_DIR"
    cp -r "$WWWROOT/uploads/"* "$UPLOAD_DIR"/
  fi
fi

echo "MiNe: DATABASE_PATH=$DB_PATH"
echo "MiNe: UPLOAD_FOLDER=$UPLOAD_DIR"
echo "MiNe: listening on 0.0.0.0:$PORT"

exec waitress-serve --host=0.0.0.0 --port="$PORT" wsgi:app
