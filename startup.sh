#!/bin/bash
# Azure App Service startup — uses project-root mine.db + uploads from git deploy.
# Portal: Configuration → General settings → Startup Command = bash startup.sh
set -euo pipefail

cd /home/site/wwwroot

DB_PATH="${DATABASE_PATH:-mine.db}"
UPLOAD_DIR="${UPLOAD_FOLDER:-uploads}"
PORT="${PORT:-8000}"

if [[ "$DB_PATH" != /* ]]; then
  DB_PATH="/home/site/wwwroot/$DB_PATH"
fi
if [[ "$UPLOAD_DIR" != /* ]]; then
  UPLOAD_DIR="/home/site/wwwroot/$UPLOAD_DIR"
fi

mkdir -p "$(dirname "$DB_PATH")"
mkdir -p "$UPLOAD_DIR"

echo "MiNe: DATABASE_PATH=$DB_PATH"
echo "MiNe: UPLOAD_FOLDER=$UPLOAD_DIR"
echo "MiNe: listening on 0.0.0.0:$PORT"

exec waitress-serve --host=0.0.0.0 --port="$PORT" wsgi:app
