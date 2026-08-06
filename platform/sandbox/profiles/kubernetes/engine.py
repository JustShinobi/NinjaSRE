"""The seam between the Kubernetes profile and a cluster.

Everything above this — the pod spec, the Envoy configuration, the pool, the
claim, the TTL, the reaper — is profile code that runs unchanged against any
implementation. That is what lets the contract suite drive the real
``KubernetesSandbox`` without a cluster, and what lets a deployment behind an
unusual API gateway substitute one class.

Two operations here are not the obvious ones and are worth naming.

``compare_and_set_annotations`` is the atomic primitive the claim and the reaper
are both built on. Kubernetes gives it for free — a write carrying a
``resourceVersion`` fails if anything changed since the read — and having it as
one method rather than a read-then-write at two call sites is what makes "two
replicas cannot claim the same pod" a property of one function.

``exec_stream`` is the pod ``exec`` subresource, which is a SPDY or WebSocket
upgrade rather than a plain request. ``HttpKubernetesApi`` therefore shells out
to ``kubectl exec`` for this one operation and speaks HTTP for the rest: writing
a SPDY client with the standard library alone would be several hundred lines
whose failure modes nobody here would be able to debug at three in the morning.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from config.constants.security import (
    KUBERNETES_SERVICE_HOST_ENV,
    KUBERNETES_SERVICE_PORT_ENV,
)
from platform.sandbox.errors import SandboxLimitExceeded, SandboxProvisioningFailed
from platform.sandbox.port import (
    ExecutionCompleted,
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    OutputChunk,
    OutputStream,
)
from platform.sandbox.spec import LimitKind, ResourceLimits

#: Where a pod finds its own service account, mounted by the kubelet. Read at
#: call time rather than cached: a projected token is rotated under a running
#: pod, and a client that read it once authenticates for an hour and then stops.
_SERVICE_ACCOUNT_DIRECTORY = Path("/var/run/secrets/kubernetes.io/serviceaccount")

#: What a container runtime reports for an OOM kill: 128 plus ``SIGKILL``.
_OOM_KILLED_EXIT_CODE = 137


@runtime_checkable
class KubernetesApi(Protocol):
    """The cluster operations this profile needs, and no more."""

    async def available(self) -> bool:
        """Return whether the cluster answers right now."""

    async def create_config_map(self, manifest: Mapping[str, Any]) -> None:
        """Create the ConfigMap ``manifest`` describes."""

    async def get_config_map(self, name: str) -> Mapping[str, Any] | None:
        """Return the ConfigMap called ``name``, or ``None`` if it is gone."""

    async def delete_config_map(self, name: str) -> None:
        """Delete the ConfigMap called ``name``. Idempotent."""

    async def create_network_policy(self, manifest: Mapping[str, Any]) -> None:
        """Create the NetworkPolicy ``manifest`` describes."""

    async def delete_network_policy(self, name: str) -> None:
        """Delete the NetworkPolicy called ``name``. Idempotent."""

    async def create_pod(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create the pod ``manifest`` describes and return it as the cluster stored it."""

    async def get_pod(self, name: str) -> Mapping[str, Any] | None:
        """Return the pod called ``name``, or ``None`` if it is gone."""

    async def list_pods(
        self, *, label_selector: Mapping[str, str] | None = None
    ) -> tuple[Mapping[str, Any], ...]:
        """Return every pod matching ``label_selector`` in this profile's namespace."""

    async def await_ready(self, name: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        """Return the pod once every container in it is running.

        Raises ``SandboxProvisioningFailed`` on timeout. A pod that is scheduled
        but not ready is a pod that cannot execute anything, and returning it
        would move the failure to the first capability call.
        """

    async def compare_and_set_annotations(
        self,
        name: str,
        *,
        expected: Mapping[str, str | None],
        annotations: Mapping[str, str],
        labels: Mapping[str, str] | None = None,
    ) -> bool:
        """Return whether the write landed, atomically against other replicas.

        Fails and returns ``False`` when any annotation in ``expected`` does not
        currently hold that value — ``None`` meaning "must be absent". This is
        what makes a claim and a reaper lease safe across replicas; a read
        followed by a write would not be.
        """

    def exec_stream(
        self,
        name: str,
        request: ExecutionRequest,
        *,
        container: str,
        limits: ResourceLimits,
        wall_clock_seconds: float,
        sandbox_id: str,
    ) -> AsyncIterator[ExecutionEvent]:
        """Run ``request`` in ``name``'s ``container``, yielding output then a completion."""

    async def interrupt(self, name: str, *, container: str) -> None:
        """Stop what ``container`` is running inside ``name``, without deleting the pod."""

    async def delete_pod(self, name: str) -> None:
        """Delete the pod called ``name``. Idempotent."""


class HttpKubernetesApi:
    """Speaks to a cluster's API server over the standard library.

    ``urllib`` in a worker thread, for the reason the credential proxy's HTTP
    transport gives: NinjaSRE's runtime dependency list is six packages an
    operator has to audit, and the official client would be a seventh plus its
    own transitive tree. The concurrency this costs is bounded by the same
    semaphore the loop already puts on parallel tool calls.
    """

    __slots__ = ("_base_url", "_kubectl", "_namespace", "_token_path", "_verify")

    def __init__(
        self,
        *,
        base_url: str,
        namespace: str,
        token_path: Path | None = None,
        verify: str | None = None,
        kubectl: str = "kubectl",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._namespace = namespace
        self._token_path = (
            token_path if token_path is not None else _SERVICE_ACCOUNT_DIRECTORY / "token"
        )
        self._verify = verify
        self._kubectl = kubectl

    @property
    def namespace(self) -> str:
        """Return the namespace this client works in."""
        return self._namespace

    async def available(self) -> bool:
        """Return whether the API server answers."""
        try:
            await self._request("GET", "/version")
        except (OSError, SandboxProvisioningFailed):
            return False
        return True

    async def create_config_map(self, manifest: Mapping[str, Any]) -> None:
        """Create the ConfigMap ``manifest`` describes."""
        await self._request("POST", self._path("configmaps"), body=manifest)

    async def get_config_map(self, name: str) -> Mapping[str, Any] | None:
        """Return the ConfigMap called ``name``, or ``None``."""
        try:
            return await self._request("GET", self._path("configmaps", name))
        except SandboxProvisioningFailed:
            return None

    async def delete_config_map(self, name: str) -> None:
        """Delete the ConfigMap called ``name``, ignoring one already gone."""
        await self._delete(self._path("configmaps", name))

    async def create_network_policy(self, manifest: Mapping[str, Any]) -> None:
        """Create the NetworkPolicy ``manifest`` describes."""
        await self._request(
            "POST", self._path("networkpolicies", group="/apis/networking.k8s.io/v1"), body=manifest
        )

    async def delete_network_policy(self, name: str) -> None:
        """Delete the NetworkPolicy called ``name``, ignoring one already gone."""
        await self._delete(self._path("networkpolicies", name, group="/apis/networking.k8s.io/v1"))

    async def create_pod(self, manifest: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create the pod ``manifest`` describes and return the stored object."""
        return await self._request("POST", self._path("pods"), body=manifest)

    async def get_pod(self, name: str) -> Mapping[str, Any] | None:
        """Return the pod called ``name``, or ``None``."""
        try:
            return await self._request("GET", self._path("pods", name))
        except SandboxProvisioningFailed:
            return None

    async def list_pods(
        self, *, label_selector: Mapping[str, str] | None = None
    ) -> tuple[Mapping[str, Any], ...]:
        """Return every pod matching ``label_selector``."""
        path = self._path("pods")
        if label_selector:
            from urllib.parse import quote

            selector = ",".join(f"{key}={value}" for key, value in sorted(label_selector.items()))
            path = f"{path}?labelSelector={quote(selector)}"
        listing = await self._request("GET", path)
        items = listing.get("items", [])
        return tuple(items) if isinstance(items, list) else ()

    async def await_ready(self, name: str, *, timeout_seconds: float) -> Mapping[str, Any]:
        """Return the pod once every container is running, or fail provisioning."""
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            pod = await self.get_pod(name)
            if pod is not None and _pod_is_ready(pod):
                return pod
            await asyncio.sleep(0.2)
        raise SandboxProvisioningFailed(
            "kubernetes", f"pod {name} did not become ready within {timeout_seconds:g}s"
        )

    async def compare_and_set_annotations(
        self,
        name: str,
        *,
        expected: Mapping[str, str | None],
        annotations: Mapping[str, str],
        labels: Mapping[str, str] | None = None,
    ) -> bool:
        """Return whether the write landed, using the stored ``resourceVersion``."""
        pod = await self.get_pod(name)
        if pod is None:
            return False
        metadata = pod.get("metadata", {})
        current = metadata.get("annotations", {}) or {}
        for key, value in expected.items():
            if current.get(key) != value:
                return False

        patch: dict[str, Any] = {
            "metadata": {
                "resourceVersion": metadata.get("resourceVersion"),
                "annotations": dict(annotations),
            }
        }
        if labels:
            patch["metadata"]["labels"] = dict(labels)
        try:
            await self._request(
                "PATCH",
                self._path("pods", name),
                body=patch,
                content_type="application/merge-patch+json",
            )
        except SandboxProvisioningFailed:
            return False
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
        """Run ``request`` in the pod's ``container`` through ``kubectl exec``."""
        arguments = [
            "exec",
            "--namespace",
            self._namespace,
            name,
            "--container",
            container,
            "--stdin",
            "--",
            *request.command,
        ]
        process = await asyncio.create_subprocess_exec(
            self._kubectl,
            *arguments,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        if process.stdin is not None:
            if request.stdin:
                process.stdin.write(request.stdin)
            process.stdin.close()

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=wall_clock_seconds
            )
        except TimeoutError:
            process.kill()
            await self.interrupt(name, container=container)
            raise SandboxLimitExceeded(
                LimitKind.WALL_CLOCK_SECONDS, sandbox_id=sandbox_id, allowed=wall_clock_seconds
            ) from None

        if stdout:
            yield OutputChunk(stream=OutputStream.STDOUT, data=stdout)
        if stderr:
            yield OutputChunk(stream=OutputStream.STDERR, data=stderr)

        exit_code = process.returncode or 0
        if exit_code == _OOM_KILLED_EXIT_CODE:
            raise SandboxLimitExceeded(
                LimitKind.MEMORY_BYTES,
                sandbox_id=sandbox_id,
                allowed=float(limits.memory_bytes),
                stdout=stdout,
                stderr=stderr,
            )
        yield ExecutionCompleted(result=ExecutionResult(exit_code=exit_code))

    async def interrupt(self, name: str, *, container: str) -> None:
        """Kill everything running in the pod's ``container``."""
        process = await asyncio.create_subprocess_exec(
            self._kubectl,
            "exec",
            "--namespace",
            self._namespace,
            name,
            "--container",
            container,
            "--",
            "/bin/sh",
            "-c",
            "kill -9 -1 || true",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.wait()

    async def delete_pod(self, name: str) -> None:
        """Delete the pod called ``name``, ignoring one already gone."""
        await self._delete(self._path("pods", name))

    def _path(self, kind: str, name: str = "", *, group: str = "/api/v1") -> str:
        """Return the API path for one kind of object in this namespace."""
        path = f"{group}/namespaces/{self._namespace}/{kind}"
        return f"{path}/{name}" if name else path

    async def _delete(self, path: str) -> None:
        """Delete one object, treating an absent one as success."""
        try:
            await self._request("DELETE", path)
        except SandboxProvisioningFailed:
            return

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        content_type: str = "application/json",
    ) -> dict[str, Any]:
        """Send one request to the API server, off the event loop."""
        return await asyncio.to_thread(self._request_blocking, method, path, body, content_type)

    def _request_blocking(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None,
        content_type: str,
    ) -> dict[str, Any]:
        """Send one request with ``urllib``, in a worker thread."""
        headers = {"Accept": "application/json"}
        token = self._read_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = content_type

        request = urllib.request.Request(  # noqa: S310 — the URL is the operator's own cluster
            f"{self._base_url}{path}", data=payload, headers=headers, method=method
        )
        context = ssl.create_default_context(cafile=self._verify) if self._verify else None
        try:
            with urllib.request.urlopen(  # noqa: S310 — same
                request, timeout=30, context=context
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise SandboxProvisioningFailed(
                "kubernetes", f"{method} {path} returned {error.code}"
            ) from error
        decoded = json.loads(raw) if raw else {}
        return decoded if isinstance(decoded, dict) else {}

    def _read_token(self) -> str:
        """Return this pod's service-account token, or the empty string.

        Read on every request. A projected token is rotated under a running pod,
        and a client that cached it authenticates for an hour and then starts
        failing in a way that looks like an RBAC change.
        """
        try:
            return self._token_path.read_text().strip()
        except OSError:
            return ""


def in_cluster(namespace: str | None = None) -> HttpKubernetesApi:
    """Return a client configured from the service account this pod was given.

    Raises ``SandboxProvisioningFailed`` outside a cluster rather than falling
    back to a kubeconfig. A deployment that thinks it is in a cluster and is not
    should find out at start, and picking up whatever kubeconfig happens to be
    on the host is how a test run reaches production.
    """
    host = os.environ.get(KUBERNETES_SERVICE_HOST_ENV)
    port = os.environ.get(KUBERNETES_SERVICE_PORT_ENV)
    if not host or not port:
        raise SandboxProvisioningFailed(
            "kubernetes",
            "this process is not running in a cluster, so there is no in-cluster "
            "configuration to read",
        )
    resolved = namespace
    if resolved is None:
        try:
            resolved = (_SERVICE_ACCOUNT_DIRECTORY / "namespace").read_text().strip()
        except OSError as error:
            raise SandboxProvisioningFailed(
                "kubernetes", f"cannot read this pod's namespace: {error}"
            ) from error
    return HttpKubernetesApi(
        base_url=f"https://{host}:{port}",
        namespace=resolved,
        verify=str(_SERVICE_ACCOUNT_DIRECTORY / "ca.crt"),
    )


def _pod_is_ready(pod: Mapping[str, Any]) -> bool:
    """Return whether every container in ``pod`` is running."""
    status = pod.get("status", {})
    if status.get("phase") != "Running":
        return False
    statuses = status.get("containerStatuses", [])
    if not isinstance(statuses, list) or not statuses:
        return False
    return all(entry.get("ready") for entry in statuses)


__all__ = [
    "HttpKubernetesApi",
    "KubernetesApi",
    "in_cluster",
]
