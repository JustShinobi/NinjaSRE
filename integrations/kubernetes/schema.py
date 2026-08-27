"""Kubernetes credentials, and the case where the host is not knowable in advance.

Kubernetes is the reference for a problem the other two do not have: **there is
no vendor host list**. Every deployment's API server is somewhere else — an EKS
endpoint, an in-cluster service address, a bastion — so the egress allow-list
cannot be written by whoever writes this file.

The answer is that the allow-list is still a declaration, it is just made by the
operator rather than by NinjaSRE. ``rule_for`` builds the injection rule from the
API server hosts a deployment actually configured, and the proxy enforces
exactly those. The property FR-009 wants — an integration cannot reach a host it
did not declare — holds either way; what changes is who declares.

``DEFAULT_RULE`` covers the in-cluster case, which is the one where the address
genuinely is fixed: a pod reaches the API server at ``kubernetes.default.svc``,
and a deployment running that way needs no configuration at all.

The credential is a bearer token — a service account's, in practice — because
client certificates would put a private key in the same place the token is, and
the token is the credential Kubernetes RBAC is actually expressed against.
"""

from __future__ import annotations

from typing import Final

from integrations._base.regions import Region, RegionMap
from platform.credentials.proxy.injection import BearerTokenInjection, InjectionRule
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind

INTEGRATION: Final = "kubernetes"

#: Where the API server is from inside the cluster. The one address that is the
#: same in every deployment, and the reason an in-cluster install needs no host
#: configuration.
IN_CLUSTER_HOST: Final = "kubernetes.default.svc"

#: Kubernetes has no vendor regions, and the "region" an operator selects is
#: which cluster they mean. The default map holds the one address that is always
#: right; ``regions_for`` builds the rest from the endpoints a deployment
#: actually configured — the same declaration ``rule_for`` reads, so the
#: catalogue and the egress allow-list cannot disagree.
REGIONS: Final = RegionMap.single(INTEGRATION, host=IN_CLUSTER_HOST, name="in-cluster")

SCHEMA: Final = CredentialSchema(
    integration=INTEGRATION,
    fields=(
        CredentialField(
            name="endpoint",
            description=(
                "Where the API server answers — https://k8s.example.com:6443. "
                "Leave empty when NinjaSRE runs inside the cluster it is "
                "watching: the in-cluster address is the one thing that is the "
                "same everywhere, and it is always permitted."
            ),
            kind=FieldKind.ENDPOINT,
            required=False,
            label="API server address",
            guide_url="https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/",
        ),
        CredentialField(
            name="token",
            description="Service account token with the read roles the capabilities need.",
            min_length=16,
            label="Service account token",
            min_scope="get/list on events, deployments.apps and replicasets.apps",
            guide_url="https://kubernetes.io/docs/reference/access-authn-authz/rbac/",
        ),
        CredentialField(
            name="cluster",
            description="Name of the cluster this token authenticates against.",
            kind=FieldKind.PUBLIC,
            required=False,
            label="Cluster name",
            guide_url="https://kubernetes.io/docs/tasks/access-application-cluster/access-cluster/",
        ),
        CredentialField(
            name="namespace",
            description="Default namespace for namespaced reads.",
            kind=FieldKind.PUBLIC,
            required=False,
            label="Default namespace",
            guide_url="https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/",
        ),
    ),
)

DEFAULT_RULE: Final = InjectionRule(
    integration=INTEGRATION,
    hosts=(IN_CLUSTER_HOST,),
    injections=(BearerTokenInjection(field="token"),),
)


def rule_for(*api_server_hosts: str) -> InjectionRule:
    """Return the injection rule permitting ``api_server_hosts``.

    The in-cluster address is always included, because a deployment that
    configured an external endpoint may still have workers running inside the
    cluster, and discovering that at 03:00 is not the moment to find out the
    allow-list is one entry short.
    """
    declared = {IN_CLUSTER_HOST, *api_server_hosts}
    return InjectionRule(
        integration=INTEGRATION,
        hosts=tuple(sorted(declared)),
        injections=(BearerTokenInjection(field="token"),),
    )


def regions_for(**clusters: str) -> RegionMap:
    """Return the cluster map for the API servers a deployment configured.

    Keyword arguments are cluster name to API server host, because that is how
    an operator thinks about it: ``regions_for(prod="k8s.acme.example")``. The
    in-cluster address is always present, for the same reason ``rule_for``
    always permits it.
    """
    named = {"in-cluster": IN_CLUSTER_HOST, **clusters}
    return RegionMap(
        integration=INTEGRATION,
        regions=tuple(Region(name=name, host=host) for name, host in named.items()),
        default="in-cluster",
    )


def base_url(host: str = IN_CLUSTER_HOST) -> str:
    """Return the API base URL for a Kubernetes API server host."""
    return f"https://{host}"


__all__ = [
    "DEFAULT_RULE",
    "INTEGRATION",
    "IN_CLUSTER_HOST",
    "REGIONS",
    "SCHEMA",
    "base_url",
    "regions_for",
    "rule_for",
]
