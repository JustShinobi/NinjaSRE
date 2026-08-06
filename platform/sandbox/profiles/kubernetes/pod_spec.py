"""The manifests a sandbox pod is made of, and why each field is not optional.

Two containers in one pod. The sandbox container holds the capability code and
has no route to anything; the Envoy sidecar holds the allow-list and is the only
thing with one. They share a network namespace, which is what makes "all egress
goes through the sidecar" a property of the pod rather than a convention.

The security context is where most of the isolation lives, and every field in it
closes a specific escape:

- ``readOnlyRootFilesystem`` — nothing a capability writes outside its scratch
  mount survives, and there is nowhere to drop a binary for the next execution.
- ``runAsNonRoot`` with an explicit uid — a container running as root is one
  kernel bug away from being root on the node.
- ``allowPrivilegeEscalation: false`` — no ``setuid`` binary can regain what the
  capability drop removed, which is what makes the drop worth doing.
- ``capabilities.drop: [ALL]`` — a capability that needs ``NET_ADMIN`` to do its
  job is a capability that can reconfigure the thing enforcing its allow-list.
- ``seccompProfile: RuntimeDefault`` — the syscall surface a container runtime
  considers safe, rather than the whole kernel.
- ``automountServiceAccountToken: false`` — the single most valuable thing in a
  pod is its service-account token, and a sandbox has no business holding one.

The scratch volume is an ``emptyDir`` with a ``sizeLimit`` and
``medium: Memory``: in RAM so it is gone with the pod, sized so the quota is
enforced by the kubelet rather than watched.

Content arrives as a ``ConfigMap`` projected read-only. The alternative — baking
skills into the image — makes every skill edit an image build, which is how a
platform ends up with skills nobody updates.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from config.constants.security import (
    SANDBOX_CONTAINER_NAME,
    SANDBOX_EGRESS_SIDECAR_NAME,
    SANDBOX_ENVOY_ADMIN_PORT,
    SANDBOX_ENVOY_LISTENER_PORT,
    SANDBOX_EXPIRES_AT_ANNOTATION,
    SANDBOX_INVESTIGATION_LABEL,
    SANDBOX_ORG_LABEL,
    SANDBOX_STATE_LABEL,
    SANDBOX_TEAM_LABEL,
)
from platform.sandbox.content import ContentBundle, ContentEntry
from platform.sandbox.port import SandboxState
from platform.sandbox.spec import SandboxSpec

#: The uid the sandbox container runs as. A high, fixed, non-root number rather
#: than whatever the image declares, because an image is somebody else's
#: decision and ``USER root`` is a common one.
SANDBOX_RUN_AS_USER = 65_534

#: Kubernetes wants CPU in millicores and memory in bytes. One core is the
#: ceiling; the CPU-seconds budget is the sampler's, and the two answer
#: different questions — how much at once, and how much in total.
_MILLICORES_PER_CORE = 1000


def config_map_name(sandbox_id: str) -> str:
    """Return the name of the ConfigMap carrying one sandbox's content."""
    return f"ninjasre-content-{sandbox_id}"


def pod_name(sandbox_id: str) -> str:
    """Return the name of one sandbox's pod."""
    return f"ninjasre-sandbox-{sandbox_id}"


def content_config_map(sandbox_id: str, spec: SandboxSpec, *, namespace: str) -> dict[str, Any]:
    """Return the ConfigMap delivering ``spec``'s capability content.

    ``binaryData`` for everything, so a skill body with a byte order mark or a
    capability's compiled resource survives the round trip. Kubernetes decides
    what is text; the digest check afterwards does not care what it decided.
    """
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": config_map_name(sandbox_id),
            "namespace": namespace,
            "labels": _labels(sandbox_id, spec),
        },
        "binaryData": {
            _config_map_key(entry.path): base64.b64encode(entry.data).decode()
            for entry in spec.content.entries
        },
    }


def bundle_from_config_map(manifest: Mapping[str, Any]) -> ContentBundle:
    """Return the bundle a content ConfigMap currently carries.

    The inverse of ``content_config_map``, and it exists so immutability can be
    checked through the *delivery mechanism* rather than through a file the
    agent's own host happens to hold. In this profile the ConfigMap is what the
    kubelet projects into the pod, so a ConfigMap whose digest has changed is a
    pod that would execute content nobody approved.
    """
    entries = tuple(
        ContentEntry(path=key.replace("__", "/"), data=base64.b64decode(value))
        for key, value in sorted((manifest.get("binaryData") or {}).items())
    )
    return ContentBundle(entries=entries)


def _config_map_key(path: str) -> str:
    """Return the ConfigMap key for a content path.

    Keys may not contain ``/``, so a nested path is flattened and the volume's
    ``items`` mapping puts it back. Doing it here rather than at the volume keeps
    the two halves of the transformation in one file.
    """
    return path.replace("/", "__")


def sandbox_pod(
    sandbox_id: str,
    spec: SandboxSpec,
    *,
    namespace: str,
    envoy_config_map: str,
    expires_at: str,
    state: SandboxState = SandboxState.CLAIMED,
) -> dict[str, Any]:
    """Return the pod manifest for one sandbox, sidecar included."""
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name(sandbox_id),
            "namespace": namespace,
            "labels": {**_labels(sandbox_id, spec), SANDBOX_STATE_LABEL: str(state)},
            "annotations": {SANDBOX_EXPIRES_AT_ANNOTATION: expires_at},
        },
        "spec": {
            "restartPolicy": "Never",
            # A sandbox holding a service-account token is a sandbox holding the
            # cluster's most useful credential. There is no configuration that
            # turns this back on.
            "automountServiceAccountToken": False,
            "enableServiceLinks": False,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": SANDBOX_RUN_AS_USER,
                "runAsGroup": SANDBOX_RUN_AS_USER,
                "fsGroup": SANDBOX_RUN_AS_USER,
                "seccompProfile": {"type": "RuntimeDefault"},
            },
            "containers": [
                _sandbox_container(spec),
                _envoy_container(),
            ],
            "volumes": [
                {
                    "name": "scratch",
                    "emptyDir": {"medium": "Memory", "sizeLimit": str(spec.limits.scratch_bytes)},
                },
                {
                    "name": "content",
                    "configMap": {
                        "name": config_map_name(sandbox_id),
                        "defaultMode": 0o444,
                        "items": [
                            {"key": _config_map_key(entry.path), "path": entry.path}
                            for entry in spec.content.entries
                        ],
                    },
                },
                {"name": "envoy-config", "configMap": {"name": envoy_config_map}},
            ],
        },
    }


def _sandbox_container(spec: SandboxSpec) -> dict[str, Any]:
    """Return the container the capability code actually runs in."""
    return {
        "name": SANDBOX_CONTAINER_NAME,
        "image": spec.image,
        # The pod outlives one command, so the container waits rather than
        # running the image's entrypoint. A sandbox is a place to execute
        # capability code, not a service.
        "command": ["/bin/sh", "-c", "sleep infinity"],
        "workingDir": spec.scratch_path,
        "securityContext": {
            "readOnlyRootFilesystem": True,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        },
        "resources": {
            "limits": {
                "cpu": f"{_MILLICORES_PER_CORE}m",
                "memory": str(spec.limits.memory_bytes),
                "ephemeral-storage": str(spec.limits.scratch_bytes),
            },
            "requests": {
                "cpu": f"{_MILLICORES_PER_CORE // 10}m",
                "memory": str(spec.limits.memory_bytes // 2),
            },
        },
        "volumeMounts": [
            {"name": "scratch", "mountPath": spec.scratch_path},
            {"name": "content", "mountPath": spec.content_path, "readOnly": True},
        ],
    }


def _envoy_container() -> dict[str, Any]:
    """Return the sidecar that every packet leaving this pod has to pass.

    It reads its configuration from the ``envoy-config`` volume, which the pod
    points at the generated ConfigMap. The container itself therefore names no
    ConfigMap: the indirection is what lets the allow-list be regenerated for a
    claimed pool member without rewriting the container.
    """
    return {
        "name": SANDBOX_EGRESS_SIDECAR_NAME,
        "image": "envoyproxy/envoy:distroless-v1.31-latest",
        "args": ["-c", "/etc/envoy/envoy.yaml"],
        "ports": [
            {"name": "egress", "containerPort": SANDBOX_ENVOY_LISTENER_PORT},
            {"name": "admin", "containerPort": SANDBOX_ENVOY_ADMIN_PORT},
        ],
        "securityContext": {
            "readOnlyRootFilesystem": True,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
        },
        "volumeMounts": [
            {"name": "envoy-config", "mountPath": "/etc/envoy", "readOnly": True},
        ],
    }


def network_policy(
    sandbox_id: str, spec: SandboxSpec, *, namespace: str, proxy_selector: Mapping[str, str]
) -> dict[str, Any]:
    """Return the policy that leaves the sidecar as the only way out.

    Without this the sidecar is a *suggestion*: a capability that opened its own
    socket would bypass it entirely, and the allow-list would be enforcing
    nothing against the only adversary that matters. The policy denies all
    egress from the pod and then permits exactly two things — DNS, because
    nothing resolves without it, and the credential proxy.

    Ingress is denied outright. Nothing should be connecting *to* a sandbox, and
    a pod that accepts connections is a pod another tenant's sandbox could
    reach.
    """
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": f"ninjasre-sandbox-{sandbox_id}",
            "namespace": namespace,
            "labels": _labels(sandbox_id, spec),
        },
        "spec": {
            "podSelector": {"matchLabels": {SANDBOX_INVESTIGATION_LABEL: spec.investigation_id}},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [],
            "egress": [
                {
                    "to": [{"namespaceSelector": {}, "podSelector": {"matchLabels": {}}}],
                    "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
                },
                {
                    "to": [{"podSelector": {"matchLabels": dict(proxy_selector)}}],
                    "ports": [{"protocol": "TCP", "port": spec.egress.proxy_port}],
                },
                {
                    "to": [
                        {
                            "podSelector": {
                                "matchLabels": {SANDBOX_INVESTIGATION_LABEL: spec.investigation_id}
                            }
                        }
                    ],
                    "ports": [{"protocol": "TCP", "port": SANDBOX_ENVOY_LISTENER_PORT}],
                },
            ],
        },
    }


def _labels(sandbox_id: str, spec: SandboxSpec) -> dict[str, str]:
    """Return the labels every object belonging to one sandbox carries.

    The cluster is this profile's source of truth — the pool, the claim, and the
    reaper all read these rather than a table somewhere — so they are the schema
    of that record and not decoration.
    """
    return {
        "app.kubernetes.io/name": "ninjasre-sandbox",
        "app.kubernetes.io/instance": sandbox_id,
        SANDBOX_ORG_LABEL: spec.org_id,
        SANDBOX_TEAM_LABEL: spec.team_id,
        SANDBOX_INVESTIGATION_LABEL: spec.investigation_id,
        **dict(spec.labels),
    }


__all__ = [
    "SANDBOX_RUN_AS_USER",
    "bundle_from_config_map",
    "config_map_name",
    "content_config_map",
    "network_policy",
    "pod_name",
    "sandbox_pod",
]
