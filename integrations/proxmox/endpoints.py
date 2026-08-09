"""Several addresses for one cluster, and moving on from the one that is down.

A Proxmox cluster is reachable through any of its nodes: every node proxies the
cluster-wide endpoints to whichever node owns them. A configuration that names
one node therefore has a single point of failure that is not the cluster's — and
the moment it matters is the moment that node is the one that died, which is
also the moment an operator most needs to be told what happened.

So the configuration is a list and this is the ring that walks it. Three things
about it are deliberate.

**Only reachability fails over.** A refused connection, a timeout, a proxy that
could not get there — those are facts about one address. A 403 is a fact about
the credential and is identical from every node; retrying it against each in turn
would spend three calls to learn the same thing and would bury the one answer the
operator needed under a failover story.

**An endpoint that comes back is usable again.** A node that was rebooting is not
a node that is gone. Marking it permanently dead would leave a two-node cluster
pinned to one address after the first maintenance window.

**Exhausting the ring raises, naming every address and what each said.** The
alternative — returning nothing, or raising on the last failure alone — produces
the report "connection refused" for a cluster with two addresses, one of which
was refused and the other of which timed out. Those are different problems.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from integrations._base.errors import IntegrationError, IntegrationErrorReason

#: The failures that say something about *this address* rather than about the
#: credential or the request. Anything else is the same from every node, so
#: trying the next one learns nothing and hides the answer.
REACHABILITY_REASONS: frozenset[IntegrationErrorReason] = frozenset(
    {
        IntegrationErrorReason.PROXY_UNAVAILABLE,
        IntegrationErrorReason.TIMEOUT,
    }
)


class NoEndpointReachable(IntegrationError):
    """Every configured address was tried and none of them answered.

    Carries what each one said, because "the cluster is unreachable" is a
    conclusion an operator can only act on once they know whether one node
    refused the connection and the other timed out, or whether both did the same
    thing — the first is a node that is up and not serving, the second is a
    network.
    """

    def __init__(self, integration: str, attempts: tuple[tuple[str, str], ...]) -> None:
        self.attempts = attempts
        detail = "; ".join(f"{host}: {said}" for host, said in attempts)
        super().__init__(
            f"none of the {len(attempts)} configured {integration} endpoints answered — {detail}",
            integration=integration,
            reason=IntegrationErrorReason.PROXY_UNAVAILABLE,
        )


@dataclass(slots=True)
class EndpointRing:
    """The addresses one cluster is configured with, and which to try next.

    Mutable on purpose: reachability is state that changes during a run, and a
    frozen value would mean either rebuilding the ring on every failure or
    carrying the state somewhere else, where it would drift from the list it
    describes.
    """

    integration: str
    hosts: tuple[str, ...]
    _failed: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.hosts:
            raise ValueError(
                f"{self.integration}: a cluster needs at least one address. A ring with none "
                f"would report every call as unreachable and name nothing that could be fixed."
            )
        duplicates = sorted({host for host in self.hosts if self.hosts.count(host) > 1})
        if duplicates:
            raise ValueError(f"{self.integration}: {duplicates} is configured more than once")

    @classmethod
    def of(cls, *hosts: str, integration: str = "proxmox") -> EndpointRing:
        """Return a ring over ``hosts``, in the order they were configured."""
        return cls(integration=integration, hosts=tuple(hosts))

    @property
    def current(self) -> str:
        """Return the address the next call should use.

        The first that is not currently marked unreachable, and the first
        outright when every one of them is — because a ring that refused to name
        an address after a total outage could never recover from one.
        """
        return next((host for host in self.hosts if host not in self._failed), self.hosts[0])

    @property
    def unreachable(self) -> tuple[str, ...]:
        """Return the addresses currently known not to answer, in configured order."""
        return tuple(host for host in self.hosts if host in self._failed)

    @property
    def reachable(self) -> tuple[str, ...]:
        """Return the addresses that are not currently marked unreachable."""
        return tuple(host for host in self.hosts if host not in self._failed)

    def mark_unreachable(self, host: str, *, detail: str) -> None:
        """Record that ``host`` did not answer, and raise when none is left.

        Raises:
            NoEndpointReachable: this was the last address still standing.
        """
        self._failed[host] = detail
        if len(self._failed) >= len(self.hosts):
            raise NoEndpointReachable(
                self.integration,
                tuple((name, self._failed.get(name, "not tried")) for name in self.hosts),
            )

    def mark_reachable(self, host: str) -> None:
        """Record that ``host`` answered, clearing any earlier failure."""
        self._failed.pop(host, None)

    async def attempt[T](self, call: Callable[[str], Awaitable[T]]) -> T:
        """Return what ``call`` produced against the first address that answered.

        ``call`` takes the host and makes one request against it. A reachability
        failure moves to the next address; anything else is raised as it arrived,
        because it would be identical from every node.

        Raises:
            NoEndpointReachable: every configured address failed to answer.
            IntegrationError: the vendor refused for a reason failover cannot fix.
        """
        attempts: list[tuple[str, str]] = []
        for host in (*self.reachable, *self.unreachable):
            try:
                answer = await call(host)
            except IntegrationError as error:
                if error.reason not in REACHABILITY_REASONS:
                    raise
                attempts.append((host, str(error)))
                self._failed[host] = str(error)
                continue
            self.mark_reachable(host)
            return answer

        raise NoEndpointReachable(self.integration, tuple(attempts))


__all__ = ["REACHABILITY_REASONS", "EndpointRing", "NoEndpointReachable"]
