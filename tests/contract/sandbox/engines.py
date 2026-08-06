"""Runtimes the contract suite drives, so the two heavy profiles are testable.

These implement ``ContainerEngine`` and ``KubernetesApi`` over the same
process-execution core the ``process`` profile uses, and layer on the semantics
that make each profile what it is: a read-only root that refuses a write outside
the scratch mount, a network with nothing on it but the proxy, an allow-list
that answers a 403.

**They model the runtime. They do not model the profile.** Every line of
``profiles/container`` and ``profiles/kubernetes`` under test is the real one —
the provisioning order, the manifests, the claim, the TTL, the reaper interface.
What is simulated is Docker and Kubernetes, and the boundary is exactly the two
protocols in ``engine.py``.

That is a real limit, stated plainly. This suite proves the three profiles
behave identically and that each builds the right manifests; it does not prove a
cluster honours a ``NetworkPolicy``. The alternative is that the two profiles
most deployments run are the two nobody runs on a pull request, which is a worse
trade by a wide margin.

The read-only root is enforced here rather than pretended: content is
materialised without a write bit exactly as the real profiles do, so the
tampering probe fails for the same reason in all three rows.

**A mount is simulated by rewriting the paths a command names.** Inside a real
container ``/scratch`` *is* the host directory behind it; here the host
directory is somewhere under a temporary root, so ``_through_mounts`` substitutes
the mount target for its source in each argument. That is the one place these
engines depart from being a thin layer over local execution, and it is what lets
the contract suite address ``instance.content_path`` — the profile's own
declared path — identically in all three rows.
"""

from __future__ import annotations

import asyncio
import copy
import shutil
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

from platform.sandbox.errors import SandboxProvisioningFailed
from platform.sandbox.port import ExecutionEvent, ExecutionRequest
from platform.sandbox.profiles.container.image import ContainerSpec
from platform.sandbox.profiles.container.network import ContainerNetwork
from platform.sandbox.profiles.process.execution import LaunchPlan, stream_execution
from platform.sandbox.profiles.process.monitor import default_monitor
from platform.sandbox.spec import ResourceLimits


class SimulatedContainerEngine:
    """A container runtime that runs containers as confined local processes.

    The mounts are real directories, the limits are the real sampler, and the
    network is a real object the profile asks about. What is simulated is the
    daemon.
    """

    __slots__ = ("_containers", "_monitor", "_networks", "_running")

    def __init__(self) -> None:
        self._networks: dict[str, ContainerNetwork] = {}
        self._containers: dict[str, ContainerSpec] = {}
        self._running: dict[str, Any] = {}
        self._monitor = default_monitor()

    async def available(self) -> bool:
        """Return that this runtime is reachable."""
        return True

    async def create_network(self, network: ContainerNetwork) -> None:
        """Record ``network``, refusing a duplicate as a real runtime would."""
        if network.name in self._networks:
            raise SandboxProvisioningFailed("container", f"network {network.name} already exists")
        self._networks[network.name] = network

    async def remove_network(self, name: str) -> None:
        """Remove the network called ``name``. Idempotent."""
        self._networks.pop(name, None)

    async def create(self, spec: ContainerSpec) -> str:
        """Record ``spec``'s container, refusing one on an unknown network."""
        if spec.network not in self._networks:
            raise SandboxProvisioningFailed("container", f"no such network: {spec.network}")
        self._containers[spec.name] = spec
        return spec.name

    async def start(self, container: str) -> None:
        """Start ``container``, or fail as a real runtime would for an unknown one."""
        if container not in self._containers:
            raise SandboxProvisioningFailed("container", f"no such container: {container}")

    async def exec_stream(
        self,
        container: str,
        request: ExecutionRequest,
        *,
        limits: ResourceLimits,
        wall_clock_seconds: float,
        sandbox_id: str,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run ``request`` inside ``container``'s mounts, under its limits."""
        spec = self._containers[container]
        scratch = _writable_mount(spec)
        cwd = scratch / request.working_directory if request.working_directory else scratch
        cwd.mkdir(parents=True, exist_ok=True)

        plan = LaunchPlan(
            command=_through_mounts(
                request.command,
                {mount.target: mount.source for mount in spec.mounts},
            ),
            cwd=cwd,
            scratch=scratch,
            environment={**dict(spec.environment), **dict(request.environment)},
            limits=limits,
            stdin=request.stdin,
        )
        async for event in stream_execution(
            plan,
            sandbox_id=sandbox_id,
            monitor=self._monitor,
            wall_clock_seconds=wall_clock_seconds,
            register=lambda execution: self._running.__setitem__(container, execution),
        ):
            yield event
        self._running.pop(container, None)

    async def interrupt(self, container: str) -> None:
        """Stop what ``container`` is running."""
        execution = self._running.get(container)
        if execution is not None:
            await execution.cancel()

    async def remove(self, container: str) -> None:
        """Destroy ``container``. Idempotent."""
        self._running.pop(container, None)
        self._containers.pop(container, None)

    @property
    def networks(self) -> Mapping[str, ContainerNetwork]:
        """Return the bridges this runtime currently holds, for assertions."""
        return dict(self._networks)


def _writable_mount(spec: ContainerSpec) -> Path:
    """Return the host directory backing ``spec``'s scratch mount."""
    for mount in spec.mounts:
        if not mount.read_only:
            return Path(mount.source)
    raise SandboxProvisioningFailed("container", "the container has no writable scratch mount")


class SimulatedKubernetesApi:
    """A cluster that stores objects in a dict and runs pods as local processes.

    ``compare_and_set_annotations`` is the part that has to be right: it holds a
    lock and checks the expected values inside it, which is the same guarantee
    the real API server's ``resourceVersion`` precondition gives. Everything the
    claim, the pool, and the reaper assert about concurrency is asserted against
    that.
    """

    __slots__ = (
        "_config_maps",
        "_lock",
        "_monitor",
        "_network_policies",
        "_pods",
        "_roots",
        "_running",
    )

    def __init__(self) -> None:
        self._pods: dict[str, dict[str, Any]] = {}
        self._config_maps: dict[str, dict[str, Any]] = {}
        self._network_policies: dict[str, dict[str, Any]] = {}
        self._roots: dict[str, Path] = {}
        self._running: dict[str, Any] = {}
        self._monitor = default_monitor()
        self._lock = asyncio.Lock()

    async def available(self) -> bool:
        """Return that the API server answers."""
        return True

    async def create_config_map(self, manifest: Mapping[str, Any]) -> None:
        """Store ``manifest``, replacing one of the same name as ``apply`` would."""
        self._config_maps[manifest["metadata"]["name"]] = copy.deepcopy(dict(manifest))

    async def get_config_map(self, name: str) -> Mapping[str, Any] | None:
        """Return the ConfigMap called ``name``, or ``None``."""
        stored = self._config_maps.get(name)
        return copy.deepcopy(stored) if stored is not None else None

    async def delete_config_map(self, name: str) -> None:
        """Delete the ConfigMap called ``name``. Idempotent."""
        self._config_maps.pop(name, None)

    async def create_network_policy(self, manifest: Mapping[str, Any]) -> None:
        """Store the NetworkPolicy ``manifest`` describes."""
        self._network_policies[manifest["metadata"]["name"]] = copy.deepcopy(dict(manifest))

    async def delete_network_policy(self, name: str) -> None:
        """Delete the NetworkPolicy called ``name``. Idempotent."""
        self._network_policies.pop(name, None)

    async def create_pod(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
        """Store the pod and materialise the volumes its containers would see.

        The content volume is written from the ConfigMap the profile created,
        without a write bit — the same mechanism the other two profiles use, so
        the tampering probe fails here for the same reason rather than by fiat.
        """
        import base64

        stored = copy.deepcopy(dict(manifest))
        name = stored["metadata"]["name"]
        if name in self._pods:
            raise SandboxProvisioningFailed("kubernetes", f"pod {name} already exists")

        root = Path(mkdtemp(prefix=f"{name}-"))
        scratch = root / "scratch"
        content = root / "content"
        scratch.mkdir(mode=0o700)
        content.mkdir(mode=0o700)

        content_map = self._config_maps.get(f"ninjasre-content-{_instance_of(stored)}", {})
        for key, encoded in (content_map.get("binaryData") or {}).items():
            target = content / key.replace("__", "/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded))
            target.chmod(0o444)
        content.chmod(0o555)

        self._roots[name] = root
        stored["status"] = {
            "phase": "Running",
            "containerStatuses": [
                {"name": container["name"], "ready": True}
                for container in stored["spec"]["containers"]
            ],
        }
        stored["metadata"]["resourceVersion"] = "1"
        self._pods[name] = stored
        return copy.deepcopy(stored)

    async def get_pod(self, name: str) -> Mapping[str, Any] | None:
        """Return the pod called ``name``, or ``None``."""
        pod = self._pods.get(name)
        return copy.deepcopy(pod) if pod is not None else None

    async def list_pods(
        self, *, label_selector: Mapping[str, str] | None = None
    ) -> tuple[Mapping[str, Any], ...]:
        """Return every pod whose labels match ``label_selector``."""
        selector = dict(label_selector or {})
        return tuple(
            copy.deepcopy(pod)
            for pod in self._pods.values()
            if all(
                (pod.get("metadata", {}).get("labels") or {}).get(key) == value
                for key, value in selector.items()
            )
        )

    async def await_ready(self, name: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        """Return the pod, which this runtime starts synchronously."""
        pod = await self.get_pod(name)
        if pod is None:
            raise SandboxProvisioningFailed("kubernetes", f"pod {name} does not exist")
        return pod

    async def compare_and_set_annotations(
        self,
        name: str,
        *,
        expected: Mapping[str, str | None],
        annotations: Mapping[str, str],
        labels: Mapping[str, str] | None = None,
    ) -> bool:
        """Apply the write only if every expected annotation still holds."""
        async with self._lock:
            pod = self._pods.get(name)
            if pod is None:
                return False
            metadata = pod["metadata"]
            current = metadata.setdefault("annotations", {})
            for key, value in expected.items():
                if current.get(key) != value:
                    return False
            current.update(annotations)
            if labels:
                metadata.setdefault("labels", {}).update(labels)
            metadata["resourceVersion"] = str(int(metadata.get("resourceVersion", "1")) + 1)
            return True

    async def exec_stream(
        self,
        name: str,
        request: ExecutionRequest,
        *,
        container: str,
        limits: ResourceLimits,
        wall_clock_seconds: float,
        sandbox_id: str,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run ``request`` in the pod's volumes, under its limits."""
        pod = self._pods[name]
        root = self._roots[name]
        scratch = root / "scratch"
        cwd = scratch / request.working_directory if request.working_directory else scratch
        cwd.mkdir(parents=True, exist_ok=True)

        environment = {
            entry["name"]: entry["value"]
            for entry in _container_of(pod, container).get("env", [])
            if "value" in entry
        }
        plan = LaunchPlan(
            command=_through_mounts(request.command, _mounts_of(pod, container, root)),
            cwd=cwd,
            scratch=scratch,
            environment={**environment, **_proxy_environment(pod), **dict(request.environment)},
            limits=limits,
            stdin=request.stdin,
        )
        async for event in stream_execution(
            plan,
            sandbox_id=sandbox_id,
            monitor=self._monitor,
            wall_clock_seconds=wall_clock_seconds,
            register=lambda execution: self._running.__setitem__(name, execution),
        ):
            yield event
        self._running.pop(name, None)

    async def interrupt(self, name: str, *, container: str) -> None:
        """Stop what the pod is running."""
        execution = self._running.get(name)
        if execution is not None:
            await execution.cancel()

    async def delete_pod(self, name: str) -> None:
        """Delete the pod and everything its volumes held. Idempotent."""
        self._running.pop(name, None)
        self._pods.pop(name, None)
        root = self._roots.pop(name, None)
        if root is not None:
            _make_writable(root)
            shutil.rmtree(root, ignore_errors=True)

    def content_path(self, pod: str) -> Path:
        """Return where the pod's content volume was materialised, for assertions."""
        return self._roots[pod] / "content"

    def scratch_path(self, pod: str) -> Path:
        """Return where the pod's scratch volume was materialised, for assertions."""
        return self._roots[pod] / "scratch"

    @property
    def network_policies(self) -> Mapping[str, dict[str, Any]]:
        """Return the policies this cluster holds, for assertions."""
        return dict(self._network_policies)

    @property
    def config_maps(self) -> Mapping[str, dict[str, Any]]:
        """Return the ConfigMaps this cluster holds, for assertions."""
        return dict(self._config_maps)

    def seed_expired(self, pod: str, *, at: datetime | None = None) -> None:
        """Backdate a pod's expiry, so a reaper test does not have to wait for one."""
        from config.constants.security import SANDBOX_EXPIRES_AT_ANNOTATION

        when = at if at is not None else datetime(2000, 1, 1, tzinfo=UTC)
        self._pods[pod]["metadata"].setdefault("annotations", {})[SANDBOX_EXPIRES_AT_ANNOTATION] = (
            when.isoformat()
        )


def _through_mounts(command: tuple[str, ...], mounts: Mapping[str, str]) -> tuple[str, ...]:
    """Return ``command`` with each mount target rewritten to its host source.

    What a bind mount does for free, done by substitution because these engines
    execute locally. Longest target first, so ``/opt/ninjasre/content`` is not
    half-rewritten by a shorter mount that happens to prefix it.
    """
    ordered = sorted(mounts.items(), key=lambda pair: len(pair[0]), reverse=True)
    rewritten = []
    for argument in command:
        for target, source in ordered:
            argument = argument.replace(target, source)
        rewritten.append(argument)
    return tuple(rewritten)


def _mounts_of(pod: Mapping[str, Any], container: str, root: Path) -> dict[str, str]:
    """Return the pod's volume mounts as target-to-host-directory pairs."""
    volumes = {"scratch": root / "scratch", "content": root / "content"}
    return {
        mount["mountPath"]: str(volumes[mount["name"]])
        for mount in _container_of(pod, container).get("volumeMounts", [])
        if mount["name"] in volumes
    }


def _instance_of(pod: Mapping[str, Any]) -> str:
    """Return the sandbox identifier a pod's labels carry."""
    return str((pod.get("metadata", {}).get("labels") or {}).get("app.kubernetes.io/instance", ""))


def _container_of(pod: Mapping[str, Any], name: str) -> dict[str, Any]:
    """Return the named container from a pod manifest."""
    for container in pod["spec"]["containers"]:
        if container["name"] == name:
            return dict(container)
    raise KeyError(name)


def _proxy_environment(pod: Mapping[str, Any]) -> dict[str, str]:
    """Return the proxy variables a real kubelet would inject from the sidecar.

    The pod spec does not carry them — in a cluster the sidecar intercepts
    egress at the network layer rather than through an environment variable —
    so they are added here to keep the sandbox's environment identical across
    the three rows of the suite.
    """
    from config.constants.security import (
        SANDBOX_ENVOY_LISTENER_PORT,
        SANDBOX_HTTP_PROXY_ENV,
        SANDBOX_HTTPS_PROXY_ENV,
        SANDBOX_NO_PROXY_ENV,
    )

    endpoint = f"http://127.0.0.1:{SANDBOX_ENVOY_LISTENER_PORT}"
    return {
        SANDBOX_HTTP_PROXY_ENV: endpoint,
        SANDBOX_HTTPS_PROXY_ENV: endpoint,
        SANDBOX_NO_PROXY_ENV: "127.0.0.1",
    }


def _make_writable(root: Path) -> None:
    """Restore write permission so a read-only content tree can be removed."""
    import os
    import stat

    for path in sorted(root.rglob("*"), reverse=True):
        os.chmod(path, path.stat().st_mode | stat.S_IWRITE | (stat.S_IEXEC if path.is_dir() else 0))
    os.chmod(root, root.stat().st_mode | stat.S_IWRITE)


__all__ = [
    "SimulatedContainerEngine",
    "SimulatedKubernetesApi",
]
