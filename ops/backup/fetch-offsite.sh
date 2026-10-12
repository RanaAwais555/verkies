#!/bin/sh
# Disaster recovery (slice 7.2): fetch the newest off-site copy and decrypt it.
#   fetch-offsite.sh <private key file> <output folder>
# Writes <output folder>/restore.dump (and restore-documents.tar.gz when there is one), ready for
# pg_restore. Uses the same "offsite" remote and VROS_BACKUP_REMOTE_PATH as backup.sh.
set -eu

key="$1"
out="$2"
remote="offsite:${VROS_BACKUP_REMOTE_PATH:?set VROS_BACKUP_REMOTE_PATH}"

for var in $(env | sed -n 's/^\(RCLONE_CONFIG_OFFSITE_[A-Z_]*\)=$/\1/p'); do
  unset "${var}"
done

newest() { rclone lsf --files-only --include "$1" "${remote}" | sort | tail -n 1; }

dump="$(newest 'vros-2*.dump.age')"
if [ -z "${dump}" ]; then
  echo "No database copy found at ${remote}" >&2
  exit 1
fi
mkdir -p "${out}/.fetch"
rclone copyto "${remote}/${dump}" "${out}/.fetch/${dump}"
age -d -i "${key}" -o "${out}/restore.dump" "${out}/.fetch/${dump}"
echo "database: ${dump} -> ${out}/restore.dump"

# The documents archive made in the same cycle, if there was one.
stamp="${dump#vros-}"
stamp="${stamp%.dump.age}"
files="vros-documents-${stamp}.tar.gz.age"
if rclone lsf --files-only --include "${files}" "${remote}" | grep -q .; then
  rclone copyto "${remote}/${files}" "${out}/.fetch/${files}"
  age -d -i "${key}" -o "${out}/restore-documents.tar.gz" "${out}/.fetch/${files}"
  echo "documents: ${files} -> ${out}/restore-documents.tar.gz"
fi
rm -rf "${out}/.fetch"
