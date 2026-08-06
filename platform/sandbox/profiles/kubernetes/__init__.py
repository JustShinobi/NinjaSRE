"""The ``kubernetes`` profile: a pod per investigation, egress enforced outside it.

The strongest of the three, and the only one whose isolation holds against a
capability that ignores every convention. Read ``runner.py`` for the provisioning
order, ``envoy.py`` for why the allow-list lives in a separate process, and
``warm_pool.py`` for why a claimed instance is destroyed rather than returned.
"""

from __future__ import annotations

from platform.sandbox.profiles.kubernetes.claims import Claim
from platform.sandbox.profiles.kubernetes.engine import (
    HttpKubernetesApi,
    KubernetesApi,
    in_cluster,
)
from platform.sandbox.profiles.kubernetes.runner import KubernetesSandbox
from platform.sandbox.profiles.kubernetes.warm_pool import PoolStatus, WarmPool

__all__ = [
    "Claim",
    "HttpKubernetesApi",
    "KubernetesApi",
    "KubernetesSandbox",
    "PoolStatus",
    "WarmPool",
    "in_cluster",
]
