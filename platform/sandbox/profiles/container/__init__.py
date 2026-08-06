"""The ``container`` profile: a routeless bridge and a read-only root per sandbox.

The profile most deployments should run. Read ``runner.py`` for the provisioning
sequence, ``network.py`` for why egress here is a topology rather than a filter,
and ``engine.py`` for the seam a deployment substitutes when its runtime is not
reached through a CLI.
"""

from __future__ import annotations

from platform.sandbox.profiles.container.engine import CliContainerEngine, ContainerEngine
from platform.sandbox.profiles.container.image import ContainerSpec, Mount, container_spec
from platform.sandbox.profiles.container.network import ContainerNetwork, network_for
from platform.sandbox.profiles.container.runner import ContainerSandbox

__all__ = [
    "CliContainerEngine",
    "ContainerEngine",
    "ContainerNetwork",
    "ContainerSandbox",
    "ContainerSpec",
    "Mount",
    "container_spec",
    "network_for",
]
