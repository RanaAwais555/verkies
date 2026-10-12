#!/bin/sh
# Restore drill (slice 7.2): proves a dump restores. Restores it into a scratch database on the
# same server, checks it, prints one line saying what was found, and drops the scratch copy.
# Exits non-zero if anything does not match. The live database is only read, never written.
#   restore-drill.sh /backups/vros-<time>.dump
set -eu

dump="$1"
scratch="vros_restore_drill"
live="${PGDATABASE:-vros}"

cleanup() { dropdb --if-exists "${scratch}" >/dev/null 2>&1 || true; }
trap cleanup EXIT

cleanup
createdb "${scratch}"
if ! pg_restore --no-owner --exit-on-error -d "${scratch}" "${dump}" >/tmp/restore-drill.log 2>&1; then
  echo "pg_restore failed: $(tail -n 3 /tmp/restore-drill.log | tr '\n' ' ')"
  exit 1
fi

q() { psql -tA -d "$1" -c "$2"; }
tables_sql="SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
version_sql="SELECT version_num FROM alembic_version"
restored_tables="$(q "${scratch}" "${tables_sql}")"
live_tables="$(q "${live}" "${tables_sql}")"
restored_version="$(q "${scratch}" "${version_sql}")"
live_version="$(q "${live}" "${version_sql}")"

if [ "${restored_tables}" != "${live_tables}" ]; then
  echo "restored ${restored_tables} tables, the live database has ${live_tables}"
  exit 1
fi
if [ "${restored_version}" != "${live_version}" ]; then
  echo "restored schema version ${restored_version}, the live database is at ${live_version}"
  exit 1
fi
counts=""
for table in users accounts research_runs evidence audit_log; do
  counts="${counts}${table} $(q "${scratch}" "SELECT count(*) FROM ${table}"), "
done
echo "restored ${restored_tables} tables at schema ${restored_version}; ${counts%, }"
