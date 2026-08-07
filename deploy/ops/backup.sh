#!/bin/sh
# One artefact holding everything NinjaSRE persists, plus the manifest that
# makes restoring it into a different release a decision rather than a gamble.
#
# ADR 0004's single datastore is what makes this a single command: relational
# rows, pgvector embeddings, and the Apache AGE graph are one database, so one
# `pg_dump` covers all three and there is no second snapshot whose consistency
# with the first anybody has to reason about.
#
# The manifest is written *first* and read *first*. It records the schema
# revision, the extension versions, the row counts per data shape, and the
# fingerprint of the encryption key — never the key. `restore.sh` reads it
# before it writes anything, which is how a version mismatch is caught before
# a half-restore rather than after one.
#
# The dump carries ciphertext for every stored credential. Back the encryption
# key up separately, and not beside this file: a dump and its key in one place
# is a dump with the credentials in it.
#
# Usage:
#     sh deploy/ops/backup.sh [DESTINATION_DIRECTORY]
#
# Reads NINJASRE_DATABASE_URL from the environment.

set -eu

DESTINATION="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="${DESTINATION}/ninjasre-${STAMP}"
ARCHIVE="${WORK}.tar.gz"

if [ -z "${NINJASRE_DATABASE_URL:-}" ]; then
    echo "NINJASRE_DATABASE_URL is not set; there is nothing to back up." >&2
    exit 2
fi

mkdir -p "${WORK}"

# --no-owner and --no-privileges so the dump restores under whichever role the
# target uses. Without them a restore into a differently-owned database fails
# on every ALTER TABLE ... OWNER TO, which is a bad thing to discover at three
# in the morning.
echo "Dumping the database..." >&2
pg_dump "${NINJASRE_DATABASE_URL}" \
    --no-owner \
    --no-privileges \
    --format=plain \
    --file "${WORK}/database.sql"

echo "Writing the manifest..." >&2
python deploy/ops/manifest.py --dump "${WORK}/database.sql" --output "${WORK}/manifest.json" >/dev/null

tar -czf "${ARCHIVE}" -C "${DESTINATION}" "$(basename "${WORK}")"
rm -rf "${WORK}"

echo "${ARCHIVE}"
