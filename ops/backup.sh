#!/bin/sh
# Nightly backup of the VROS database and of uploaded documents (storage/documents, mounted
# read-only). Keeps VROS_BACKUP_KEEP_DAYS days (default 14).
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
  if [ -d /data/storage/documents ]; then
    files="/backups/vros-documents-${stamp}.tar.gz"
    if tar -czf "${files}.partial" -C /data/storage documents; then
      mv "${files}.partial" "${files}"
      echo "documents backup ok: ${files}"
    else
      rm -f "${files}.partial"
      echo "documents backup FAILED at ${stamp}" >&2
    fi
  fi
  find /backups -name 'vros-*.dump' -mtime "+${KEEP_DAYS}" -delete
  find /backups -name 'vros-documents-*.tar.gz' -mtime "+${KEEP_DAYS}" -delete
  sleep 86400
done
