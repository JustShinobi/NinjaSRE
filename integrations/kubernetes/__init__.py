"""Kubernetes: pods, events, and rollouts, with the token at the network edge.

The reference integration for two cases the simple one does not cover: a bearer
token rather than vendor-specific headers, and an egress allow-list the operator
declares because NinjaSRE cannot know where a cluster's API server is.

``DESCRIPTOR`` carries the in-cluster rule, which is the case that needs no
configuration. A deployment reaching an external endpoint replaces the rule with
``config.rule_for(...)`` at composition, and the proxy enforces whichever it was
given.
"""

from __future__ import annotations

from typing import Final

from integrations.kubernetes.client import KubernetesClient
from integrations.kubernetes.config import (
    DEFAULT_RULE,
    IN_CLUSTER_HOST,
    INTEGRATION,
    SCHEMA,
    base_url,
    rule_for,
)
from integrations.kubernetes.verifier import KubernetesVerifier
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy

KUBERNETES: Final = IntegrationDescriptor(
    name=INTEGRATION,
    schema=SCHEMA,
    rule=DEFAULT_RULE,
    verifier=KubernetesVerifier(),
    client_class=KubernetesClient,
    sdk_strategy=SdkStrategy.DIRECT_CLIENT,
    strategy_note=(
        "The official client's transport can be replaced, but its credential loading "
        "cannot: it reads a kubeconfig or an in-cluster service account token itself, "
        "which is the behaviour Article IV forbids and the one thing about it that is "
        "not configurable. The reads an investigation needs are four REST paths, so a "
        "direct client costs less than the adaptation would."
    ),
)

DESCRIPTOR: Final = KUBERNETES

__all__ = [
    "DEFAULT_RULE",
    "INTEGRATION",
    "IN_CLUSTER_HOST",
    "KUBERNETES",
    "DESCRIPTOR",
    "SCHEMA",
    "KubernetesClient",
    "KubernetesVerifier",
    "base_url",
    "rule_for",
]
