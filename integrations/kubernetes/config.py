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

from platform.credentials.proxy.injection import BearerTokenInjection, InjectionRule
from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind

INTEGRATION: Final = "kubernetes"

#: Where the API server is from inside the cluster. The one address that is the
#: same in every deployment, and the reason an in-cluster install needs no host
#: configuration.
IN_CLUSTER_HOST: Final = "kubernetes.default.svc"

SCHEMA: Final = CredentialSchema(
    integration=INTEGRATION,
    fields=(
        CredentialField(
            name="token",
            description="Service account token with the read roles the capabilities need.",
            min_length=16,
        ),
        CredentialField(
            name="cluster",
            description="Name of the cluster this token authenticates against.",
            kind=FieldKind.PUBLIC,
            required=False,
        ),
        CredentialField(
            name="namespace",
            description="Default namespace for namespaced reads.",
            kind=FieldKind.PUBLIC,
            required=False,
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


def base_url(host: str = IN_CLUSTER_HOST) -> str:
    """Return the API base URL for a Kubernetes API server host."""
    return f"https://{host}"


__all__ = [
    "DEFAULT_RULE",
    "INTEGRATION",
    "IN_CLUSTER_HOST",
    "SCHEMA",
    "base_url",
    "rule_for",
]
