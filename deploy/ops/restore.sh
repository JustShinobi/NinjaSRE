#!/bin/sh
# Restore a backup, after deciding whether it may be restored at all.
#
# The order is the whole design. The manifest is read and checked *before* a
# single statement runs, because the three failure modes this guards against
# all look like success until much later:
#
#   - a backup from a newer release, whose schema this code cannot describe;
#   - a backup whose extensions this server does not have, which restores
#     without the data that needed them;
#   - a backup whose credentials were encrypted under a different key, which
#     restores perfectly and leaves every integration unable to authenticate.
#
# `check.py` makes that decision and prints it. `restore` means go;
# `migrate_forward` means restore and then let the application's own startup
# migrate; `refuse` means stop, with the reason on stderr.
#
# Usage:
#     sh deploy/ops/restore.sh ARCHIVE.tar.gz
#
# Reads NINJASRE_DATABASE_URL. Restores into whatever that names, so point it
# at a clean database.

set -eu

ARCHIVE="${1:?usage: restore.sh ARCHIVE.tar.gz}"

if [ -z "${NINJASRE_DATABASE_URL:-}" ]; then
    echo "NINJASRE_DATABASE_URL is not set; there is nowhere to restore to." >&2
    exit 2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

tar -xzf "${ARCHIVE}" -C "${WORK}"
ROOT="$(find "${WORK}" -mindepth 1 -maxdepth 1 -type d | head -n 1)"

if [ ! -f "${ROOT}/manifest.json" ]; then
    echo "This archive has no manifest, so it cannot be version-checked." >&2
    echo "Restoring one blind is how a schema mismatch is found a week later." >&2
    exit 2
fi

echo "Checking the backup against this release..." >&2
DECISION="$(python deploy/ops/check.py --manifest "${ROOT}/manifest.json" --dump "${ROOT}/database.sql")"

case "${DECISION}" in
    refuse)
        exit 3
        ;;
    restore|migrate_forward)
        ;;
    *)
        echo "Unrecognised decision: ${DECISION}" >&2
        exit 1
        ;;
esac

echo "Restoring..." >&2
# ON_ERROR_STOP so a failure part-way is a failure, not a database that is
# half a backup and reports success.
psql "${NINJASRE_DATABASE_URL}" \
    --set ON_ERROR_STOP=on \
    --quiet \
    --file "${ROOT}/database.sql"

if [ "${DECISION}" = "migrate_forward" ]; then
    echo "Restored. This backup predates the running release: start the" >&2
    echo "application and its startup migration will bring the schema forward" >&2
    echo "under the advisory lock." >&2
else
    echo "Restored, at the schema revision this release expects." >&2
fi
