#!/bin/bash
set -euo pipefail

umask 077

if [[ "$#" -ne 1 || "$1" != run ]]; then
  printf 'offsite bootstrap은 run argument 하나만 허용합니다.\n' >&2
  exit 64
fi

readonly ENTRYPOINT=/Users/homeserver/Server/apps/our-ledger/runtime-config/current/scripts/offsite-backup-production.sh

if [[ ! -f "$ENTRYPOINT" || -L "$ENTRYPOINT" || ! -O "$ENTRYPOINT" || ! -x "$ENTRYPOINT" ]]; then
  printf 'offsite runtime entrypoint authority를 확인할 수 없습니다.\n' >&2
  exit 1
fi

exec /usr/bin/env -i \
  HOME=/Users/homeserver \
  LANG=C \
  LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  "$ENTRYPOINT" run
