#!/bin/sh
# FR-018 and SC-004: back up, restore into a clean instance, and verify.
#
# A backup procedure nobody has restored is a procedure nobody has, so this runs
# the whole cycle against a real PostgreSQL carrying both extensions rather than
# against a fixture. What it proves, in order:
#
#   1. `backup.sh` produces one artefact with a manifest in it;
#   2. `check.py` reads that manifest and permits the restore;
#   3. `restore.sh` brings a *clean* database up from the artefact;
#   4. the row counts in the restored database match the manifest's, per shape —
#      relational, vector, and graph;
#   5. a truncated artefact is refused rather than restored quietly.
#
# Step 5 is the one worth having. Steps 1 to 4 prove the happy path; step 5
# proves the check that stops a half-copied archive from becoming a database
# that is missing rows nobody notices.
#
# Skips with a message when there is no container runtime, rather than failing.
# A suite that went red on every laptop is a suite somebody deletes.
#
# Usage:
#     sh test-infra/backup/cycle.sh

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="ninjasre-postgres-backup-cycle"
CONTAINER="ninjasre-backup-cycle"
WORK="$(mktemp -d)"

if ! command -v docker >/dev/null 2>&1; then
    echo "SKIP: no container runtime, so there is no PostgreSQL to back up." >&2
    echo "      Install Docker or Podman and run this again." >&2
    exit 0
fi

cleanup() {
    docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
    rm -rf "${WORK}"
}
trap cleanup EXIT

cd "${REPO_ROOT}"

echo "Building the datastore image..." >&2
docker build -q -f deploy/images/postgres.Dockerfile -t "${IMAGE}" . >/dev/null

echo "Starting it..." >&2
docker run -d --name "${CONTAINER}" \
    -e POSTGRES_USER=ninjasre \
    -e POSTGRES_PASSWORD=ninjasre \
    -e POSTGRES_DB=ninjasre \
    -p 55433:5432 \
    "${IMAGE}" >/dev/null

ATTEMPT=0
until docker exec "${CONTAINER}" pg_isready -U ninjasre -d ninjasre >/dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ "${ATTEMPT}" -gt 60 ]; then
        echo "The database never became ready." >&2
        exit 1
    fi
    sleep 1
done

export NINJASRE_DATABASE_URL="postgresql://ninjasre:ninjasre@127.0.0.1:55433/ninjasre"
export NINJASRE_DATABASE_ENCRYPTION_KEY="$(openssl rand -base64 32)"

echo "Migrating and seeding..." >&2
PYTHONPATH="${REPO_ROOT}" uv run python test-infra/backup/seed.py

echo "Backing up..." >&2
ARCHIVE="$(sh deploy/ops/backup.sh "${WORK}")"

echo "Restoring into a clean database..." >&2
docker exec "${CONTAINER}" psql -U ninjasre -d postgres -c "CREATE DATABASE restored" >/dev/null
RESTORE_URL="postgresql://ninjasre:ninjasre@127.0.0.1:55433/restored"

echo "Verifying..." >&2
NINJASRE_DATABASE_URL="${RESTORE_URL}" sh deploy/ops/restore.sh "${ARCHIVE}"
PYTHONPATH="${REPO_ROOT}" NINJASRE_DATABASE_URL="${RESTORE_URL}" \
    uv run python test-infra/backup/verify.py --archive "${ARCHIVE}"

echo "Checking that a truncated artefact is refused..." >&2
PYTHONPATH="${REPO_ROOT}" uv run python test-infra/backup/truncate_check.py --archive "${ARCHIVE}"

echo "Backup, restore, and verification all passed." >&2
