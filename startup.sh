#!/bin/bash
# Azure App Service startup — code in wwwroot; live data under /home/data/mine (survives deploy).
# Portal: Configuration → General settings → Startup Command = bash startup.sh
set -euo pipefail

cd /home/site/wwwroot

PERSIST_ROOT="${MINE_AZURE_DATA_ROOT:-/home/data/mine}"
DB_PATH="${DATABASE_PATH:-$PERSIST_ROOT/mine.db}"
UPLOAD_DIR="${UPLOAD_FOLDER:-$PERSIST_ROOT/uploads}"
PORT="${PORT:-8000}"

if [[ "$DB_PATH" != /* ]]; then
  DB_PATH="/home/site/wwwroot/$DB_PATH"
fi
if [[ "$UPLOAD_DIR" != /* ]]; then
  UPLOAD_DIR="/home/site/wwwroot/$UPLOAD_DIR"
fi

mkdir -p "$(dirname "$DB_PATH")"
mkdir -p "$UPLOAD_DIR"

# Seed persistent store from wwwroot once (first deploy after this change, or empty store).
if [[ ! -f "$DB_PATH" && -f /home/site/wwwroot/mine.db ]]; then
  echo "MiNe: seeding persistent DB from wwwroot mine.db"
  cp -n /home/site/wwwroot/mine.db "$DB_PATH" || true
fi
if [[ -d /home/site/wwwroot/uploads ]]; then
  echo "MiNe: merging wwwroot uploads into persistent uploads (no overwrite)"
  mkdir -p "$UPLOAD_DIR"
  cp -rn /home/site/wwwroot/uploads/. "$UPLOAD_DIR/" 2>/dev/null || \
    (cd /home/site/wwwroot/uploads && find . -type f -exec sh -c 'dest="'"$UPLOAD_DIR"'/${1#./}"; mkdir -p "$(dirname "$dest")"; [ -e "$dest" ] || cp "$1" "$dest"' _ {} \;)
fi

export DATABASE_PATH="$DB_PATH"
export UPLOAD_FOLDER="$UPLOAD_DIR"

echo "MiNe: DATABASE_PATH=$DB_PATH"
echo "MiNe: UPLOAD_FOLDER=$UPLOAD_DIR"
echo "MiNe: listening on 0.0.0.0:$PORT"

exec waitress-serve --host=0.0.0.0 --port="$PORT" wsgi:app
