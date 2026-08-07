#!/usr/bin/env sh
# Create the cloud-backed cluster and install the chaos framework on it.
#
# This one costs money for as long as it exists, so it prints what to run to
# make it stop, and it refuses to start without an explicit acknowledgement.
# Having credentials configured is not the same as consenting to spend.
set -eu

CLUSTER_NAME="${CLUSTER_NAME:-ninjasre-e2e}"
CHAOS_NAMESPACE="${CHAOS_NAMESPACE:-chaos-testing}"
CHAOS_VERSION="${CHAOS_VERSION:-2.7.0}"
HERE="$(cd "$(dirname "$0")" && pwd)"

need() {
	command -v "$1" >/dev/null 2>&1 || {
		echo "test-infra/eks/setup.sh needs '$1' and it is not on PATH." >&2
		echo "Install it and run this again; nothing has been created." >&2
		exit 1
	}
}

need eksctl
need kubectl
need helm
need aws

if [ "${NINJASRE_E2E_CLOUD:-}" = "" ]; then
	cat >&2 <<'MESSAGE'
This creates a managed Kubernetes cluster and three instances, and they cost
money from the moment they exist until they are deleted.

Set NINJASRE_E2E_CLOUD=1 to confirm, then run this again. `make chaos-setup`
creates a local cluster instead, which runs every chaos experiment for nothing.
MESSAGE
	exit 1
fi

if eksctl get cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1; then
	echo "cluster '${CLUSTER_NAME}' already exists — reusing it"
else
	echo "creating cluster '${CLUSTER_NAME}' (this takes about fifteen minutes)…"
	eksctl create cluster -f "${HERE}/cluster.yaml"
fi

eksctl utils write-kubeconfig --cluster "${CLUSTER_NAME}" >/dev/null
kubectl cluster-info >/dev/null

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
	--wait --timeout 900s

kubectl wait --namespace "${CHAOS_NAMESPACE}" \
	--for=condition=Available deployment --all --timeout=600s

cat <<MESSAGE

Ready — and billing. When you are finished:

  make chaos-teardown-eks

  make e2e-reap            sweep anything an earlier run left behind

MESSAGE
