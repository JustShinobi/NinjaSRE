"""Kubernetes' agent-callable capabilities.

Two, and the pair is the control-plane methodology: what changed, then what the
resource is doing. Events answer the second and the rollout history answers the
first, and an investigation that reads them in the other order spends its time
explaining a symptom whose cause shipped four minutes earlier.

Discovery walks this package, so adding a capability here is one module and no
edit anywhere else. Nothing here writes: restarting a workload is a remediation,
which needs an approval and a rollback plan, and it lives in the remediation
capabilities rather than one typo away from a read.
"""

from __future__ import annotations

from integrations.kubernetes.tools.rollout_history import kubernetes_rollout_history
from integrations.kubernetes.tools.workload_events import kubernetes_workload_events

__all__ = [
    "kubernetes_rollout_history",
    "kubernetes_workload_events",
]
