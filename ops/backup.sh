#!/bin/sh
# Nightly logical backup of the VROS database. Keeps VROS_BACKUP_KEEP_DAYS days (default 14).
# Runs inside the `backup` service (docker-compose.prod.yml). Copy /backups off the server
# regularly: a backup on the same disk does not survive losing the disk.
set -eu

KEEP_DAYS="${VROS_BACKUP_KEEP_DAYS:-14}"

while true; do
  stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
  target="/backups/vros-${stamp}.dump"
  if pg_dump --format=custom --file="${target}.partial"; then
    mv "${target}.partial" "${target}"
    echo "backup ok: ${target}"
  else
    rm -f "${target}.partial"
    echo "backup FAILED at ${stamp}" >&2
  fi
  find /backups -name 'vros-*.dump' -mtime "+${KEEP_DAYS}" -delete
  sleep 86400
done
