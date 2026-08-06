"""A network per sandbox, with nowhere to go but the proxy.

The container profile's egress control is a *topology* rather than a filter, and
that is what makes it strong. The sandbox joins a bridge created with
``--internal``, which has no default route and no NAT to the host's network; from
inside it there is no path off the bridge at all. The credential proxy is then
attached to that same bridge, which makes it the only reachable thing.

A capability cannot route around this because there is no route to find. It does
not depend on the capability honouring ``HTTPS_PROXY``, on DNS, or on anything
the capability chooses — which is the difference between this and the ``process``
profile's cooperative version.

**A network per sandbox, not one shared bridge.** Two investigations on one
bridge can reach each other, which concurrent isolation forbids, and "they are both ours" is
not an argument that survives multi-tenancy. The cost is a bridge create and
delete per sandbox, which is milliseconds.

The vendor allow-list still exists, and it is enforced one hop later by the
proxy itself: everything leaving the sandbox arrives at the proxy, and the proxy
refuses a host no integration declared. Two enforcement points, one list.
"""

from __future__ import annotations

from dataclasses import dataclass

from platform.sandbox.spec import EgressPolicy


@dataclass(frozen=True, slots=True)
class ContainerNetwork:
    """One sandbox's private bridge and what is attached to it."""

    name: str
    #: ``--internal``: no default route, no NAT, no path off the bridge.
    internal: bool = True
    proxy_host: str = ""
    proxy_port: int = 0
    allowed_hosts: tuple[str, ...] = ()

    def create_arguments(self) -> tuple[str, ...]:
        """Return the runtime arguments that create this network.

        Docker and Podman take the same flags for everything asked of them here,
        which is why the profile has one adapter rather than two.
        """
        arguments = ["network", "create"]
        if self.internal:
            arguments.append("--internal")
        arguments.append(self.name)
        return tuple(arguments)

    def remove_arguments(self) -> tuple[str, ...]:
        """Return the runtime arguments that remove this network."""
        return ("network", "rm", "--force", self.name)

    def permits(self, host: str) -> bool:
        """Return whether ``host`` is reachable from inside this network."""
        candidate = host.lower()
        return candidate == self.proxy_host.lower() or candidate in {
            allowed.lower() for allowed in self.allowed_hosts
        }


def network_for(sandbox_id: str, policy: EgressPolicy) -> ContainerNetwork:
    """Return the private, routeless bridge one sandbox will live on."""
    return ContainerNetwork(
        name=f"ninjasre-{sandbox_id}",
        internal=True,
        proxy_host=policy.proxy_host,
        proxy_port=policy.proxy_port,
        allowed_hosts=policy.hosts,
    )


__all__ = [
    "ContainerNetwork",
    "network_for",
]
