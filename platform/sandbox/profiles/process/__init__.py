"""The ``process`` profile: a confined subprocess of the agent's own host.

Development-grade isolation, honestly labelled. Read ``runner.py`` for what it
does and does not provide, and ``network.py`` for the one case where it reaches
kernel-enforced egress rather than cooperative routing.
"""

from __future__ import annotations

from platform.sandbox.profiles.process.monitor import ResourceMonitor, ResourceSample
from platform.sandbox.profiles.process.network import EgressPlan, plan_egress
from platform.sandbox.profiles.process.runner import ProcessSandbox

__all__ = [
    "EgressPlan",
    "ProcessSandbox",
    "ResourceMonitor",
    "ResourceSample",
    "plan_egress",
]
