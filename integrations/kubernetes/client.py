"""The Kubernetes API, over the proxy, holding no token.

The reference for FR-018's ``DIRECT_CLIENT`` row taken for a different reason
than Datadog's. The official client is not thin — it is very large — but it
loads credentials itself from a kubeconfig file or an in-cluster service account
token, which is exactly the behaviour Article IV forbids and exactly the
behaviour that cannot be configured away. Its transport can be replaced; its
credential loading cannot, and a client that loads a token has a token.

What an investigation asks Kubernetes is narrow and stable: what happened to
this pod, what is in its events, what does its deployment history look like, is
it healthy. Those are four REST paths, and they are below.

Every method here is read-only. A capability that restarts a deployment is a
different kind of thing — it needs an approval and a rollback plan under Article
III — and it does not belong in the same class as the reads, where it would be
one typo away from being called by something that thought it was reading.
"""

from __future__ import annotations

from typing import Any, Final

from integrations._base.client import ClientResponse, IntegrationClient
from integrations._base.retry import RetryPolicy
from integrations._base.transport import ProxyTransport, RequestContext
from integrations.kubernetes.config import IN_CLUSTER_HOST, INTEGRATION, base_url

CORE_API: Final = "/api/v1"
APPS_API: Final = "/apis/apps/v1"
VERSION_PATH: Final = "/version"

#: Cap on events returned for one object. An object in a crash loop generates
#: events faster than anything can read them, and the recent ones are the ones
#: that explain the incident.
MAX_EVENTS: Final = 100


class KubernetesClient(IntegrationClient):
    """Kubernetes reads, reached through the credential proxy."""

    integration = INTEGRATION

    __slots__ = ("_namespace",)

    def __init__(
        self,
        *,
        transport: ProxyTransport,
        context: RequestContext,
        api_server: str = IN_CLUSTER_HOST,
        namespace: str = "default",
        retry: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            transport=transport,
            context=context,
            base_url=base_url(api_server),
            retry=retry,
        )
        self._namespace = namespace

    @property
    def namespace(self) -> str:
        """Return the namespace this client reads from unless told otherwise."""
        return self._namespace

    async def pod(self, name: str, *, namespace: str | None = None) -> dict[str, Any]:
        """Return one pod's full object, status included."""
        space = namespace or self._namespace
        response = await self.get(f"{CORE_API}/namespaces/{space}/pods/{name}")
        return dict(response.json())

    async def pods(
        self,
        *,
        namespace: str | None = None,
        label_selector: str = "",
    ) -> tuple[dict[str, Any], ...]:
        """Return the pods in a namespace, optionally narrowed by label."""
        space = namespace or self._namespace
        params = {"labelSelector": label_selector} if label_selector else None
        response = await self.get(f"{CORE_API}/namespaces/{space}/pods", params=params)
        return tuple(response.json().get("items", ()))

    async def events(
        self,
        *,
        namespace: str | None = None,
        object_name: str = "",
        limit: int = MAX_EVENTS,
    ) -> tuple[dict[str, Any], ...]:
        """Return recent events, optionally for one object.

        The events are what turn "the pod restarted" into "the kernel killed it
        for exceeding its memory limit", which is the difference between an
        observation and a root cause.
        """
        space = namespace or self._namespace
        params = {"limit": str(min(limit, MAX_EVENTS))}
        if object_name:
            params["fieldSelector"] = f"involvedObject.name={object_name}"
        response = await self.get(f"{CORE_API}/namespaces/{space}/events", params=params)
        return tuple(response.json().get("items", ()))

    async def deployment(self, name: str, *, namespace: str | None = None) -> dict[str, Any]:
        """Return one deployment, including the revision annotations."""
        space = namespace or self._namespace
        response = await self.get(f"{APPS_API}/namespaces/{space}/deployments/{name}")
        return dict(response.json())

    async def replica_sets(
        self,
        *,
        namespace: str | None = None,
        label_selector: str = "",
    ) -> tuple[dict[str, Any], ...]:
        """Return the replica sets in a namespace — the rollout history in practice."""
        space = namespace or self._namespace
        params = {"labelSelector": label_selector} if label_selector else None
        response = await self.get(f"{APPS_API}/namespaces/{space}/replicasets", params=params)
        return tuple(response.json().get("items", ()))

    async def ping(self) -> ClientResponse:
        """Read the API server version — the cheapest authenticated call there is."""
        return await self.get(VERSION_PATH)


__all__ = [
    "APPS_API",
    "CORE_API",
    "MAX_EVENTS",
    "VERSION_PATH",
    "KubernetesClient",
]
