#!/usr/bin/env sh
# Delete the cloud-backed cluster, and say what is left if anything is.
#
# Deleting the cluster does not delete what the cloud scenarios provisioned
# alongside it, so this ends by reporting what still carries the suite's tag.
# A teardown that said "done" while a database was still running would be the
# most expensive kind of quiet.
set -eu

CLUSTER_NAME="${CLUSTER_NAME:-ninjasre-e2e}"

if ! command -v eksctl >/dev/null 2>&1; then
	echo "'eksctl' is not on PATH; nothing to delete through." >&2
	exit 1
fi

if eksctl get cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1; then
	echo "deleting cluster '${CLUSTER_NAME}' (this takes about ten minutes)…"
	eksctl delete cluster --name "${CLUSTER_NAME}" --wait
	echo "cluster gone."
else
	echo "cluster '${CLUSTER_NAME}' does not exist — nothing to do."
fi

if command -v aws >/dev/null 2>&1; then
	echo
	echo "still tagged for this suite, if anything:"
	aws resourcegroupstaggingapi get-resources \
		--tag-filters "Key=ninjasre:suite,Values=e2e" \
		--query 'ResourceTagMappingList[].ResourceARN' \
		--output text || true
	echo
	echo "run 'make e2e-reap' to destroy anything above that no run is holding."
fi
