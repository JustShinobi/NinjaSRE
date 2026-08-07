#!/usr/bin/env sh
# Delete the local cluster.
#
# Deleting the cluster removes every fault, every namespace, and the demo with
# it, which is why teardown does not try to unwind anything first: a cleanup
# step that failed would be a reason not to delete a cluster that is about to
# cease existing.
set -eu

CLUSTER_NAME="${CLUSTER_NAME:-ninjasre}"

if ! command -v kind >/dev/null 2>&1; then
	echo "'kind' is not on PATH; nothing to delete through." >&2
	exit 1
fi

if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
	echo "deleting cluster '${CLUSTER_NAME}'…"
	kind delete cluster --name "${CLUSTER_NAME}"
	echo "gone."
else
	echo "cluster '${CLUSTER_NAME}' does not exist — nothing to do."
fi
