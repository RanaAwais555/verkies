#!/bin/sh
# VROS backups (slice 7.2). Runs in the `backup` service (docker-compose.prod.yml), once a day:
#
# 1. dump     pg_dump of the database into /backups (custom format).
# 2. documents  a tarball of uploaded documents (storage/documents, mounted read-only).
# 3. offsite  both encrypted with age to VROS_BACKUP_AGE_RECIPIENT (a public key: this server
#             cannot decrypt its own off-site copies) and uploaded with rclone to the "offsite"
#             remote (RCLONE_CONFIG_OFFSITE_* settings) under VROS_BACKUP_REMOTE_PATH. Nothing is
#             ever sent off the server unencrypted.
# 4. drill    once a week (and on the first run), the latest dump is restored into a scratch
#             database and checked (ops/backup/restore-drill.sh), then the scratch copy dropped.
#
# Each step is recorded in the backup_runs table, which the app (Settings > System) and
# Prometheus (/metrics, alert rules) read. Local copies are kept VROS_BACKUP_KEEP_DAYS days,
# off-site copies VROS_BACKUP_OFFSITE_KEEP_DAYS days.
set -eu

KEEP_DAYS="${VROS_BACKUP_KEEP_DAYS:-14}"
OFFSITE_KEEP_DAYS="${VROS_BACKUP_OFFSITE_KEEP_DAYS:-30}"
DRILL_WEEKDAY="${VROS_BACKUP_DRILL_WEEKDAY:-7}"  # 1 = Monday ... 7 = Sunday
RECIPIENT="${VROS_BACKUP_AGE_RECIPIENT:-}"
REMOTE_PATH="${VROS_BACKUP_REMOTE_PATH:-}"
INTERVAL="${VROS_BACKUP_INTERVAL_SECONDS:-86400}"

# Compose passes every RCLONE_CONFIG_OFFSITE_* setting, empty when unused; rclone would read an
# empty value as a real one (an empty port), so drop the empty ones.
for var in $(env | sed -n 's/^\(RCLONE_CONFIG_OFFSITE_[A-Z_]*\)=$/\1/p'); do
  unset "${var}"
done

# record <kind> <status> <started (epoch)> <bytes> <detail>
record() {
  psql -q -v ON_ERROR_STOP=1 \
    -v kind="$1" -v status="$2" -v started="$3" -v bytes="$4" -v detail="$5" <<'SQL' \
    || echo "could not record backup run $1 $2" >&2
INSERT INTO backup_runs (kind, status, started_at, bytes, detail)
VALUES (:'kind', :'status', to_timestamp(:'started'), NULLIF(:'bytes', '')::bigint, NULLIF(:'detail', ''));
SQL
}

size_of() { wc -c < "$1" | tr -d ' '; }

offsite() {
  started="$(date +%s)"
  if [ -z "${REMOTE_PATH}" ] && [ -z "${RECIPIENT}" ]; then
    record offsite skipped "${started}" "" "Not set up: set VROS_BACKUP_AGE_RECIPIENT and VROS_BACKUP_REMOTE_PATH"
    return
  fi
  if [ -z "${RECIPIENT}" ]; then
    record offsite failed "${started}" "" "VROS_BACKUP_AGE_RECIPIENT is not set; backups are never sent off the server unencrypted"
    return
  fi
  if [ -z "${REMOTE_PATH}" ]; then
    record offsite failed "${started}" "" "VROS_BACKUP_REMOTE_PATH is not set"
    return
  fi
  staging="/backups/.offsite"
  rm -rf "${staging}" && mkdir -p "${staging}"
  total=0
  count=0
  for file in "$@"; do
    [ -f "${file}" ] || continue
    out="${staging}/$(basename "${file}").age"
    if ! age -r "${RECIPIENT}" -o "${out}" "${file}"; then
      rm -rf "${staging}"
      record offsite failed "${started}" "" "Encryption failed for $(basename "${file}")"
      return
    fi
    total=$((total + $(size_of "${out}")))
    count=$((count + 1))
  done
  if rclone copy "${staging}" "offsite:${REMOTE_PATH}" \
    && rclone check --size-only --one-way "${staging}" "offsite:${REMOTE_PATH}"; then
    rclone delete --min-age "${OFFSITE_KEEP_DAYS}d" --include 'vros-*.age' "offsite:${REMOTE_PATH}" \
      || echo "could not prune old off-site copies" >&2
    record offsite ok "${started}" "${total}" "${count} encrypted file(s) uploaded to offsite:${REMOTE_PATH}"
  else
    record offsite failed "${started}" "${total}" "Upload to offsite:${REMOTE_PATH} failed or did not verify"
  fi
  rm -rf "${staging}"
}

drill_due() {
  [ "$(date -u +%u)" = "${DRILL_WEEKDAY}" ] && return 0
  done_before="$(psql -tA -c "SELECT count(*) FROM backup_runs WHERE kind = 'drill' AND status = 'ok'" 2>/dev/null || echo 0)"
  [ "${done_before}" = "0" ]
}

while true; do
  stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
  dump="/backups/vros-${stamp}.dump"
  files="/backups/vros-documents-${stamp}.tar.gz"

  started="$(date +%s)"
  if pg_dump --format=custom --file="${dump}.partial"; then
    mv "${dump}.partial" "${dump}"
    record dump ok "${started}" "$(size_of "${dump}")" "$(basename "${dump}")"
    echo "backup ok: ${dump}"
  else
    rm -f "${dump}.partial"
    record dump failed "${started}" "" "pg_dump failed; see the backup container's log"
    echo "backup FAILED at ${stamp}" >&2
  fi

  started="$(date +%s)"
  if [ -d /data/storage/documents ]; then
    if tar -czf "${files}.partial" -C /data/storage documents; then
      mv "${files}.partial" "${files}"
      record documents ok "${started}" "$(size_of "${files}")" "$(basename "${files}")"
      echo "documents backup ok: ${files}"
    else
      rm -f "${files}.partial"
      record documents failed "${started}" "" "tar failed; see the backup container's log"
      echo "documents backup FAILED at ${stamp}" >&2
    fi
  else
    record documents skipped "${started}" "" "No uploaded documents yet"
  fi

  if [ -f "${dump}" ]; then
    offsite "${dump}" "${files}"
    if drill_due; then
      started="$(date +%s)"
      if detail="$(/bin/sh /ops/restore-drill.sh "${dump}" 2>&1)"; then
        record drill ok "${started}" "" "$(basename "${dump}"): ${detail}"
      else
        record drill failed "${started}" "" "$(basename "${dump}"): ${detail}"
      fi
      echo "restore drill: ${detail}"
    fi
  fi

  find /backups -maxdepth 1 -name 'vros-*.dump' -mtime "+${KEEP_DAYS}" -delete
  find /backups -maxdepth 1 -name 'vros-documents-*.tar.gz' -mtime "+${KEEP_DAYS}" -delete
  sleep "${INTERVAL}"
done
