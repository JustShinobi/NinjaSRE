#!/usr/bin/env sh
# Create the local cluster and install the chaos framework on it.
#
# One command, idempotent, and it checks its prerequisites before doing
# anything. A script that fails half way through leaves a cluster that is neither
# usable nor obviously broken, which is the worst of the three states.
set -eu

CLUSTER_NAME="${CLUSTER_NAME:-ninjasre}"
CHAOS_NAMESPACE="${CHAOS_NAMESPACE:-chaos-testing}"
CHAOS_VERSION="${CHAOS_VERSION:-2.7.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"

need() {
	command -v "$1" >/dev/null 2>&1 || {
		echo "test-infra/kind/setup.sh needs '$1' and it is not on PATH." >&2
		echo "Install it and run this again; nothing has been created." >&2
		exit 1
	}
}

need kind
need kubectl
need helm

if kind get clusters 2>/dev/null | grep -qx "${CLUSTER_NAME}"; then
	echo "cluster '${CLUSTER_NAME}' already exists — reusing it"
else
	echo "creating cluster '${CLUSTER_NAME}'…"
	kind create cluster --config "${HERE}/cluster.yaml" --name "${CLUSTER_NAME}" --wait 300s
fi

kubectl cluster-info --context "kind-${CLUSTER_NAME}" >/dev/null

echo "installing the chaos framework…"
helm repo add chaos-mesh https://charts.chaos-mesh.org --force-update >/dev/null
helm repo update chaos-mesh >/dev/null
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
	--namespace "${CHAOS_NAMESPACE}" \
	--create-namespace \
	--version "${CHAOS_VERSION}" \
	--set chaosDaemon.runtime=containerd \
	--set chaosDaemon.socketPath=/run/containerd/containerd.sock \
	--set dashboard.create=false \
	--wait --timeout 600s

echo "waiting for the chaos framework to be ready…"
kubectl wait --namespace "${CHAOS_NAMESPACE}" \
	--for=condition=Available deployment --all --timeout=300s

cat <<MESSAGE

Ready. The chaos suite will find this cluster automatically.

  make chaos-run           run every experiment against it
  make e2e-demo-setup      add the demo application and its stack
  make chaos-teardown      delete the cluster

MESSAGE
