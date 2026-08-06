"""The ``kubernetes`` profile: a pod per investigation, egress enforced outside it.

The profile a regulated deployment runs, and the only one whose isolation can be
defended in a security review without qualification. Every bound is enforced by
the kubelet, the filesystem boundary is the container runtime's, the network
boundary is a ``NetworkPolicy`` plus an Envoy sidecar, and none of it depends on
the capability's own process cooperating.

The provisioning order is the design, as it is in the container profile:

1. The Envoy ConfigMap, generated from the egress policy. The sidecar reads it
   at start, so it has to exist before the pod does.
2. The content ConfigMap, projected read-only.
3. The ``NetworkPolicy``, before the pod. A pod created first is a pod with a
   window of unrestricted egress, and a window is all a capability needs.
4. The pod, both containers, then a wait for both to be ready.

Release is that list backwards and it deletes the ConfigMaps too. A cluster
accumulating ConfigMaps is a slower, subtler leak than one accumulating pods,
which is why the reaper is not the only thing that cleans up.

**The cluster is the source of truth.** Claims, TTL, and reaper leases are pod
annotations rather than rows anywhere, so a replica that starts after another
one died can read the whole state, and two replicas cannot disagree about it.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from config.constants.security import (
    SANDBOX_CONTAINER_NAME,
    SANDBOX_EXPIRES_AT_ANNOTATION,
    SANDBOX_INVESTIGATION_LABEL,
    SANDBOX_LEASE_EXPIRES_AT_ANNOTATION,
    SANDBOX_LEASE_HOLDER_ANNOTATION,
    SANDBOX_ORG_LABEL,
    SANDBOX_REAPER_LEASE_SECONDS,
    SANDBOX_STATE_LABEL,
    SANDBOX_TEAM_LABEL,
    SANDBOX_WARM_POOL_SIZE,
)
from platform.sandbox.errors import (
    ContentTampered,
    SandboxExpired,
    SandboxNotFound,
    SandboxProvisioningFailed,
    SandboxRuntimeUnavailable,
)
from platform.sandbox.port import (
    ExecutionEvent,
    ExecutionRequest,
    ExecutionResult,
    SandboxInstance,
    SandboxState,
    collect,
)
from platform.sandbox.profiles.kubernetes import claims, envoy, pod_spec, ttl
from platform.sandbox.profiles.kubernetes.engine import KubernetesApi
from platform.sandbox.profiles.kubernetes.warm_pool import PoolStatus, WarmPool
from platform.sandbox.reaper import ReapableInstance
from platform.sandbox.spec import EgressPolicy, SandboxProfile, SandboxSpec
from platform.sandbox.trace import (
    NullSandboxEvents,
    SandboxEventKind,
    SandboxEventSink,
    event_from,
)

#: How long a pod is given to schedule, pull, and start both containers. Beyond
#: this the investigation fails rather than waiting: an incident response that
#: has already spent a minute waiting for a sandbox has spent it badly, and the
#: operator needs the failure to say the cluster is out of capacity.
POD_READY_TIMEOUT_SECONDS = 60.0

#: The selector that finds every sandbox this profile owns, pooled or claimed.
#: Used by the reaper, which has to see instances no process remembers creating.
OWNED_SELECTOR: Mapping[str, str] = {"app.kubernetes.io/name": "ninjasre-sandbox"}


@dataclass(frozen=True, slots=True)
class _Provisioned:
    """What the runner remembers about one live pod."""

    instance: SandboxInstance
    spec: SandboxSpec
    pod: str
    claim: claims.Claim | None


class KubernetesSandbox:
    """Runs capability code in a per-investigation pod behind an Envoy sidecar."""

    __slots__ = ("_api", "_events", "_holder", "_namespace", "_pool", "_proxy_selector", "_state")

    def __init__(
        self,
        *,
        api: KubernetesApi,
        namespace: str = "ninjasre",
        events: SandboxEventSink | None = None,
        pool_size: int = SANDBOX_WARM_POOL_SIZE,
        proxy_selector: Mapping[str, str] | None = None,
        holder: str = "",
    ) -> None:
        self._api = api
        self._namespace = namespace
        self._events = events if events is not None else NullSandboxEvents()
        self._holder = holder or f"agent-{uuid.uuid4()}"
        self._proxy_selector = dict(
            proxy_selector
            if proxy_selector is not None
            else {"app.kubernetes.io/name": "ninjasre-credential-proxy"}
        )
        self._state: dict[str, _Provisioned] = {}
        self._pool = WarmPool(
            api=api, provision=self._provision_idle, size=pool_size, holder=self._holder
        )

    @property
    def profile(self) -> SandboxProfile:
        """Return which profile this implementation is."""
        return SandboxProfile.KUBERNETES

    @property
    def pool(self) -> WarmPool:
        """Return the warm pool this runner claims from."""
        return self._pool

    async def pool_status(self, *, now: datetime | None = None) -> PoolStatus:
        """Return how much slack the pool has, for the health report."""
        return await self._pool.status(now=now)

    def egress_config(self, instance: SandboxInstance) -> dict[str, Any]:
        """Return the Envoy bootstrap ``instance``'s sidecar is enforcing.

        Exposed so a security test asserts what the sidecar would do rather than
        inferring it from a connection that happened to fail — the allow-list is
        the artefact, and reading it back is how it is checked.
        """
        provisioned = self._lookup(instance)
        return envoy.bootstrap(provisioned.spec.egress, sandbox_id=instance.sandbox_id)

    async def provision(self, spec: SandboxSpec) -> SandboxInstance:
        """Return a sandbox pod for ``spec``, claimed from the pool where possible."""
        started = time.monotonic()
        if not await self._api.available():
            raise SandboxRuntimeUnavailable(str(self.profile), "a Kubernetes API server")

        claim = await self._pool.claim(spec)
        if claim is not None:
            instance = await self._adopt(claim, spec)
        else:
            instance = await self._provision_on_demand(spec)

        await self._events.record(
            event_from(
                SandboxEventKind.PROVISIONED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
                content_digest=spec.content.digest,
                duration_seconds=time.monotonic() - started,
            )
        )
        return instance

    async def execute(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> ExecutionResult:
        """Run ``request`` to completion and return what it produced."""
        return await collect(self.stream(instance, request))

    async def stream(
        self, instance: SandboxInstance, request: ExecutionRequest
    ) -> AsyncIterator[ExecutionEvent]:
        """Yield output as it arrives, ending with one ``ExecutionCompleted``."""
        provisioned = self._lookup(instance)
        if provisioned.instance.is_expired():
            raise SandboxExpired(instance.sandbox_id)
        await self._verify_content(instance.sandbox_id, provisioned.spec)

        wall_clock = min(
            provisioned.spec.limits.wall_clock_seconds,
            request.timeout_seconds
            if request.timeout_seconds is not None
            else provisioned.spec.limits.wall_clock_seconds,
        )
        await self._events.record(
            event_from(
                SandboxEventKind.EXECUTION_STARTED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(provisioned.spec),
                capability=request.command[0],
            )
        )
        started = time.monotonic()
        try:
            async for event in self._api.exec_stream(
                provisioned.pod,
                request,
                container=SANDBOX_CONTAINER_NAME,
                limits=provisioned.spec.limits,
                wall_clock_seconds=wall_clock,
                sandbox_id=instance.sandbox_id,
            ):
                yield event
        finally:
            await self._events.record(
                event_from(
                    SandboxEventKind.EXECUTION_FINISHED,
                    sandbox_id=instance.sandbox_id,
                    profile=self.profile,
                    scope=_scope(provisioned.spec),
                    capability=request.command[0],
                    duration_seconds=time.monotonic() - started,
                )
            )

    async def interrupt(self, instance: SandboxInstance) -> None:
        """Stop what the pod is running, without deleting it."""
        provisioned = self._state.get(instance.sandbox_id)
        if provisioned is None:
            return
        await self._api.interrupt(provisioned.pod, container=SANDBOX_CONTAINER_NAME)
        await self._events.record(
            event_from(
                SandboxEventKind.INTERRUPTED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(provisioned.spec),
            )
        )

    async def release(self, instance: SandboxInstance) -> None:
        """Delete the pod, its policy, and both of its ConfigMaps. Idempotent."""
        provisioned = self._state.pop(instance.sandbox_id, None)
        if provisioned is None:
            return
        await self._destroy(instance.sandbox_id, provisioned.pod)
        await self._events.record(
            event_from(
                SandboxEventKind.RELEASED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(provisioned.spec),
            )
        )
        # Replenishment is after the delete rather than before, so a cluster at
        # capacity frees this pod's resources before being asked for another.
        await self._pool.replenish()

    async def refresh(self, instance: SandboxInstance) -> SandboxInstance:
        """Push the pod's expiry annotation out by its spec's TTL."""
        provisioned = self._lookup(instance)
        expires_at = provisioned.spec.expires_at(now=datetime.now(UTC))
        await self._api.compare_and_set_annotations(
            provisioned.pod,
            expected={},
            annotations={SANDBOX_EXPIRES_AT_ANNOTATION: ttl.render(expires_at)},
        )
        if provisioned.claim is not None:
            renewed = await claims.renew(
                self._api, provisioned.claim, lease_seconds=SANDBOX_REAPER_LEASE_SECONDS
            )
        else:
            renewed = None

        refreshed = replace(provisioned.instance, expires_at=expires_at)
        self._state[instance.sandbox_id] = replace(
            provisioned, instance=refreshed, claim=renewed or provisioned.claim
        )
        await self._events.record(
            event_from(
                SandboxEventKind.TTL_REFRESHED,
                sandbox_id=instance.sandbox_id,
                profile=self.profile,
                scope=_scope(provisioned.spec),
            )
        )
        return refreshed

    async def list_reapable(self) -> tuple[ReapableInstance, ...]:
        """Return every sandbox pod in the namespace, whoever created it.

        Read from the cluster rather than from this process's memory. That is
        the whole point of the profile's bookkeeping living in annotations: a
        replica that starts after the one that created a pod died still sees it,
        which is what makes collecting a killed agent's pods in one sweep possible
        at all.
        """
        pods = await self._api.list_pods(label_selector=dict(OWNED_SELECTOR))
        instances: list[ReapableInstance] = []
        for pod in pods:
            metadata = pod.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            labels = metadata.get("labels") or {}
            expires = ttl.expires_at_of(metadata)
            instances.append(
                ReapableInstance(
                    sandbox_id=str(labels.get("app.kubernetes.io/instance", "")),
                    org_id=str(labels.get(SANDBOX_ORG_LABEL, "")),
                    team_id=str(labels.get(SANDBOX_TEAM_LABEL, "")),
                    investigation_id=str(labels.get(SANDBOX_INVESTIGATION_LABEL, "")),
                    expires_at=expires if expires is not None else datetime.min.replace(tzinfo=UTC),
                    profile=self.profile,
                    pooled=labels.get(SANDBOX_STATE_LABEL) == str(SandboxState.IDLE),
                )
            )
        return tuple(instances)

    async def acquire_lease(
        self, sandbox_id: str, *, holder: str, lease_seconds: float, now: datetime
    ) -> bool:
        """Return whether ``holder`` won the right to destroy ``sandbox_id``.

        A compare-and-set against whatever lease is currently recorded, so two
        reapers sweeping the same namespace produce one delete and one skip.
        A live lease held by somebody else refuses.
        """
        pod = pod_spec.pod_name(sandbox_id)
        current = await self._api.get_pod(pod)
        if current is None:
            return False
        metadata = current.get("metadata", {})
        annotations = metadata.get("annotations", {}) if isinstance(metadata, dict) else {}
        existing = annotations.get(SANDBOX_LEASE_HOLDER_ANNOTATION)
        expires = annotations.get(SANDBOX_LEASE_EXPIRES_AT_ANNOTATION)
        if existing and existing != holder:
            parsed = ttl.parse(expires) if isinstance(expires, str) else None
            if parsed is not None and now < parsed:
                return False

        return await self._api.compare_and_set_annotations(
            pod,
            expected={SANDBOX_LEASE_HOLDER_ANNOTATION: existing},
            annotations={
                SANDBOX_LEASE_HOLDER_ANNOTATION: holder,
                SANDBOX_LEASE_EXPIRES_AT_ANNOTATION: ttl.render(
                    now + timedelta(seconds=lease_seconds)
                ),
            },
        )

    async def destroy(self, sandbox_id: str) -> None:
        """Remove ``sandbox_id`` on the reaper's behalf. Idempotent."""
        self._state.pop(sandbox_id, None)
        await self._destroy(sandbox_id, pod_spec.pod_name(sandbox_id))

    async def _provision_on_demand(self, spec: SandboxSpec) -> SandboxInstance:
        """Create a pod for ``spec`` directly, because the pool had nothing free."""
        sandbox_id = f"sbx-{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        expires_at = spec.expires_at(now=now)
        await self._create_objects(
            sandbox_id, spec, expires_at=expires_at, state=SandboxState.CLAIMED
        )

        pod = pod_spec.pod_name(sandbox_id)
        await self._api.await_ready(pod, timeout_seconds=POD_READY_TIMEOUT_SECONDS)

        instance = self._instance(sandbox_id, spec, now=now, expires_at=expires_at, pod=pod)
        self._state[sandbox_id] = _Provisioned(instance=instance, spec=spec, pod=pod, claim=None)
        return instance

    async def _adopt(self, claim: claims.Claim, spec: SandboxSpec) -> SandboxInstance:
        """Turn a claimed pool instance into this investigation's sandbox.

        The pooled pod was created with an empty egress policy and no content,
        because a pod created before an investigation exists cannot know either.
        Both are written now — the Envoy ConfigMap and the content ConfigMap —
        and the sidecar picks the first up on its next configuration reload.
        """
        sandbox_id = _sandbox_id_of(claim.pod)
        now = datetime.now(UTC)
        expires_at = spec.expires_at(now=now)
        await self._api.create_config_map(
            envoy.config_map(spec.egress, sandbox_id=sandbox_id, namespace=self._namespace)
        )
        await self._api.create_config_map(
            pod_spec.content_config_map(sandbox_id, spec, namespace=self._namespace)
        )
        await self._api.create_network_policy(
            pod_spec.network_policy(
                sandbox_id, spec, namespace=self._namespace, proxy_selector=self._proxy_selector
            )
        )
        await self._api.compare_and_set_annotations(
            claim.pod,
            expected={},
            annotations={SANDBOX_EXPIRES_AT_ANNOTATION: ttl.render(expires_at)},
            labels={SANDBOX_STATE_LABEL: str(SandboxState.CLAIMED)},
        )
        instance = self._instance(sandbox_id, spec, now=now, expires_at=expires_at, pod=claim.pod)
        self._state[sandbox_id] = _Provisioned(
            instance=instance, spec=spec, pod=claim.pod, claim=claim
        )
        await self._events.record(
            event_from(
                SandboxEventKind.CLAIMED,
                sandbox_id=sandbox_id,
                profile=self.profile,
                scope=_scope(spec),
            )
        )
        return instance

    async def _provision_idle(self) -> None:
        """Create one unclaimed pool member, belonging to no tenant.

        Its spec carries the deployment's limits, an empty allow-list, and no
        content — which is correct rather than incomplete. An idle pod that
        could already reach a vendor would be a pod whose egress was decided
        before anybody asked for it.
        """
        sandbox_id = f"pool-{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC)
        # A pool member is scoped to nobody. These placeholders satisfy the
        # spec's own validation and are replaced by real tenancy at claim; the
        # pod's *labels* carry no tenant, which is what the pool selects on.
        spec = SandboxSpec(
            org_id="-",
            team_id="-",
            investigation_id=sandbox_id,
            egress=EgressPolicy(proxy_url="http://127.0.0.1:1"),
        )
        expires_at = spec.expires_at(now=now)
        await self._create_objects(
            sandbox_id, spec, expires_at=expires_at, state=SandboxState.IDLE, tenant_labels=False
        )

    async def _create_objects(
        self,
        sandbox_id: str,
        spec: SandboxSpec,
        *,
        expires_at: datetime,
        state: SandboxState,
        tenant_labels: bool = True,
    ) -> None:
        """Create one sandbox's ConfigMaps, policy, and pod, in that order.

        The order is not incidental. The sidecar reads its ConfigMap at start,
        so it has to exist first; the ``NetworkPolicy`` has to exist before the
        pod, because a pod created first has a window of unrestricted egress and
        a window is all a capability needs.
        """
        try:
            await self._api.create_config_map(
                envoy.config_map(spec.egress, sandbox_id=sandbox_id, namespace=self._namespace)
            )
            await self._api.create_config_map(
                pod_spec.content_config_map(sandbox_id, spec, namespace=self._namespace)
            )
            await self._api.create_network_policy(
                pod_spec.network_policy(
                    sandbox_id,
                    spec,
                    namespace=self._namespace,
                    proxy_selector=self._proxy_selector,
                )
            )
            manifest = pod_spec.sandbox_pod(
                sandbox_id,
                spec,
                namespace=self._namespace,
                envoy_config_map=envoy.config_map_name(sandbox_id),
                expires_at=ttl.render(expires_at),
                state=state,
            )
            if not tenant_labels:
                labels = dict(manifest["metadata"]["labels"])
                for label in (SANDBOX_ORG_LABEL, SANDBOX_TEAM_LABEL, SANDBOX_INVESTIGATION_LABEL):
                    labels.pop(label, None)
                manifest["metadata"]["labels"] = labels
            await self._api.create_pod(manifest)
        except SandboxProvisioningFailed:
            await self._destroy(sandbox_id, pod_spec.pod_name(sandbox_id))
            await self._events.record(
                event_from(
                    SandboxEventKind.PROVISIONING_FAILED,
                    sandbox_id=sandbox_id,
                    profile=self.profile,
                    scope=_scope(spec),
                )
            )
            raise

    async def _verify_content(self, sandbox_id: str, spec: SandboxSpec) -> None:
        """Raise ``ContentTampered`` unless the ConfigMap still holds what was delivered.

        Checked on the way *in* to every execution. The pod's own mount is
        read-only, so a capability cannot rewrite it from inside — but the
        ConfigMap it is projected from is an API object, and anything holding
        write access to the namespace could edit it between two executions.
        Verifying the source is what makes "a sandbox cannot modify what it will
        execute next" a statement about this profile's actual delivery path.
        """
        if not spec.content.entries:
            return
        stored = await self._api.get_config_map(pod_spec.config_map_name(sandbox_id))
        if stored is None:
            raise ContentTampered(pod_spec.config_map_name(sandbox_id))
        if pod_spec.bundle_from_config_map(stored).digest != spec.content.digest:
            raise ContentTampered(pod_spec.config_map_name(sandbox_id))

    async def _destroy(self, sandbox_id: str, pod: str) -> None:
        """Delete everything belonging to one sandbox, ignoring what is already gone."""
        await self._api.delete_pod(pod)
        await self._api.delete_network_policy(f"ninjasre-sandbox-{sandbox_id}")
        await self._api.delete_config_map(pod_spec.config_map_name(sandbox_id))
        await self._api.delete_config_map(envoy.config_map_name(sandbox_id))

    def _instance(
        self,
        sandbox_id: str,
        spec: SandboxSpec,
        *,
        now: datetime,
        expires_at: datetime,
        pod: str,
    ) -> SandboxInstance:
        """Return the handle a caller holds for one provisioned pod."""
        return SandboxInstance(
            sandbox_id=sandbox_id,
            profile=self.profile,
            org_id=spec.org_id,
            team_id=spec.team_id,
            investigation_id=spec.investigation_id,
            state=SandboxState.CLAIMED,
            created_at=now,
            expires_at=expires_at,
            scratch_path=spec.scratch_path,
            content_path=spec.content_path,
            content_digest=spec.content.digest,
            handle=pod,
        )

    def _lookup(self, instance: SandboxInstance) -> _Provisioned:
        """Return this runner's record of ``instance``, or raise ``SandboxNotFound``."""
        provisioned = self._state.get(instance.sandbox_id)
        if provisioned is None:
            raise SandboxNotFound(instance.sandbox_id)
        return provisioned


def _sandbox_id_of(pod: str) -> str:
    """Return the sandbox identifier a pod name carries."""
    prefix = "ninjasre-sandbox-"
    return pod[len(prefix) :] if pod.startswith(prefix) else pod


def _scope(spec: SandboxSpec) -> dict[str, str]:
    """Return the tenancy an event carries, taken from one place."""
    return {
        "org_id": spec.org_id,
        "team_id": spec.team_id,
        "investigation_id": spec.investigation_id,
    }


__all__ = [
    "OWNED_SELECTOR",
    "POD_READY_TIMEOUT_SECONDS",
    "KubernetesSandbox",
]
