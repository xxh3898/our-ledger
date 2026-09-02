#!/bin/bash
set -euo pipefail

umask 077

if [[ "$#" -ne 0 ]]; then
  printf 'backup bootstrap은 argument를 허용하지 않습니다.\n' >&2
  exit 64
fi

readonly ENTRYPOINT=/Users/homeserver/Server/apps/our-ledger/runtime-config/current/scripts/backup-production.sh

if [[ ! -f "$ENTRYPOINT" || -L "$ENTRYPOINT" || ! -O "$ENTRYPOINT" || ! -x "$ENTRYPOINT" ]]; then
  printf 'backup runtime entrypoint authority를 확인할 수 없습니다.\n' >&2
  exit 1
fi

exec /usr/bin/env -i \
  HOME=/Users/homeserver \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  "$ENTRYPOINT" \
  --project-name our-ledger-production \
  --env-file /Users/homeserver/Server/apps/our-ledger/.env \
  --backup-dir /Users/homeserver/Server/backups/our-ledger/data
