"""Proves a Kubernetes token works, by reading the API server version.

``/version`` is the right probe because it requires authentication and requires
no RBAC permission beyond it. A probe that listed pods would fail for a token
that is correct but scoped to one namespace, and would tell the operator their
credential was broken when it was their role binding.

That separation is exactly why the permission probes exist alongside it.
Kubernetes is the vendor where "the credential works" and "the credential may do
what we need" come apart most often, because the token and the role binding are
different objects created by different people at different times. Connectivity
reads ``/version``; each verb the capabilities need gets its own read, and a
denial names the resource and the verb rather than reporting that Kubernetes
failed (FR-009, FR-010).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from integrations._base.errors import IntegrationError, IntegrationErrorReason
from integrations._base.transport import ProxyTransport, RequestContext
from integrations._verification.framework import Connectivity
from integrations._verification.permissions import (
    PermissionProbe,
    RequiredPermission,
    client_probe,
)
from integrations.kubernetes.client import KubernetesClient
from integrations.kubernetes.schema import IN_CLUSTER_HOST, INTEGRATION
from platform.credentials.verification import VerificationResult

_ADVICE: dict[IntegrationErrorReason, str] = {
    IntegrationErrorReason.UNAUTHENTICATED: (
        "The API server rejected the token. Service account tokens expire; mint a fresh "
        "one and rotate it in the vault."
    ),
    IntegrationErrorReason.FORBIDDEN: (
        "The token authenticated but RBAC denied the read. The credential is fine — the "
        "service account needs a role binding."
    ),
    IntegrationErrorReason.CREDENTIAL_UNAVAILABLE: (
        "No Kubernetes token is configured for this team."
    ),
    IntegrationErrorReason.REFUSED: (
        "The proxy refused the call: this API server host is not in the integration's "
        "declared allow-list. Add it with rule_for()."
    ),
    IntegrationErrorReason.PROXY_UNAVAILABLE: (
        "The credential proxy did not answer. Authenticated calls have no path around it."
    ),
}


#: Where an operator changes what this token may do.
_BINDING: Final = (
    "a Role or ClusterRole bound to this service account — the token itself is correct"
)

LIST_EVENTS: Final = RequiredPermission(
    name="list events",
    grants="read events in the namespaces this deployment investigates",
    capabilities=("kubernetes_workload_events",),
    where=_BINDING,
)

GET_DEPLOYMENTS: Final = RequiredPermission(
    name="get deployments.apps",
    grants="read a deployment and its rollout history",
    capabilities=("kubernetes_rollout_history",),
    where=_BINDING,
)

LIST_REPLICA_SETS: Final = RequiredPermission(
    name="list replicasets.apps",
    grants="read the replica sets behind a deployment, which is the rollout history",
    capabilities=("kubernetes_rollout_history",),
    where=_BINDING,
)

PERMISSIONS: Final[tuple[RequiredPermission, ...]] = (
    LIST_EVENTS,
    GET_DEPLOYMENTS,
    LIST_REPLICA_SETS,
)

#: FR-011. Kubernetes *can* introspect — ``SelfSubjectAccessReview`` answers
#: "may I" exactly — but it is a create against an API the token may itself not
#: be allowed to reach, and a probe whose own failure is ambiguous is worse than
#: no probe. Reading is unambiguous: 200 means permitted, 403 means not.
_READ_RATHER_THAN_ASK: Final = (
    "checked by performing the read rather than by SelfSubjectAccessReview, which is "
    "itself a create the token may not be permitted to make"
)

#: The deployment a probe asks for. It does not exist, which is the point: RBAC
#: is evaluated before the object is looked up, so a permitted read of an absent
#: object answers 404 and an unpermitted one answers 403.
_ABSENT_DEPLOYMENT: Final = "ninjasre-permission-probe"


@dataclass(frozen=True, slots=True)
class KubernetesVerifier:
    """Checks a stored Kubernetes token end to end, and what RBAC lets it read."""

    integration: str = INTEGRATION
    api_server: str = IN_CLUSTER_HOST

    @property
    def probe_description(self) -> str:
        """Return what call proves connectivity, and why that call."""
        return (
            "reads the API server version — it requires authentication and no RBAC "
            "permission beyond it, so a failure here is the token and never the role "
            "binding"
        )

    def probes(self) -> tuple[PermissionProbe, ...]:
        """Return one probe per verb this integration's capabilities need."""
        return (
            client_probe(
                LIST_EVENTS,
                build=self._client,
                call=lambda client: client.list_events(max_pages=1, max_items=1),
                fallback_note=_READ_RATHER_THAN_ASK,
            ),
            client_probe(
                GET_DEPLOYMENTS,
                build=self._client,
                call=lambda client: client.deployment(_ABSENT_DEPLOYMENT),
                fallback_note=_READ_RATHER_THAN_ASK,
            ),
            client_probe(
                LIST_REPLICA_SETS,
                build=self._client,
                call=lambda client: client.replica_sets(),
                fallback_note=_READ_RATHER_THAN_ASK,
            ),
        )

    async def connect(self, transport: object, context: object) -> Connectivity:
        """Return whether the API server accepted this team's token."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            return Connectivity(
                reachable=False,
                detail="the verifier needs a proxy transport and a request context",
            )
        try:
            response = await self._client(transport, context).ping()
        except IntegrationError as error:
            return Connectivity(
                reachable=False,
                detail=_ADVICE.get(error.reason, str(error)),
                status_code=error.status_code,
            )
        return Connectivity(
            reachable=True,
            detail="The API server accepted the token.",
            status_code=response.status_code,
        )

    async def probe(self, transport: object, context: object) -> VerificationResult:
        """Return what the API server said when this team's token was used."""
        connectivity = await self.connect(transport, context)
        return VerificationResult(
            integration=self.integration,
            ok=connectivity.reachable,
            detail=connectivity.detail,
            status_code=connectivity.status_code,
        )

    def _client(self, transport: object, context: object) -> KubernetesClient:
        """Return a client for one probe. It holds no token; the proxy injects one."""
        if not isinstance(transport, ProxyTransport) or not isinstance(context, RequestContext):
            raise TypeError("a Kubernetes probe needs a proxy transport and a request context")
        return KubernetesClient(transport=transport, context=context, api_server=self.api_server)


__all__ = [
    "GET_DEPLOYMENTS",
    "LIST_EVENTS",
    "LIST_REPLICA_SETS",
    "PERMISSIONS",
    "KubernetesVerifier",
]
