"""The discovery capability an integration declares, and the contract behind it.

An integration that can enumerate what it sees implements ``ResourceDiscovery``
and declares it exactly like any other capability: with the kinds it emits, how
often it may be swept, how many provider calls one sweep may make, the rate
limit the provider will tolerate, and a side-effect level — which is always
``read``, and which ``DiscoveryDeclaration`` refuses to let be anything else.

**The definitions live in ``platform/estate/discovery/port.py``.** Tier 3 cannot
import tier 2, and the sweep is tier 3, so the protocol has to be declared there
or a composition root could never hand one over. This module is the doorway: it
re-exports every name so that an integration author reads the contract beside
the rest of the integration framework, and it adds the one thing that only makes
sense on this side — ``declare``, which fills the bounds in from the vendor's
own rate limiting rather than from a number somebody typed twice.

**Nothing here can hold a credential.** ``discover`` takes a mode, a cursor and
a budget; there is no parameter a token fits in. An implementation reaches its
provider through ``integrations/_base/client.py``, which carries a
tenant-and-team-scoped handle and lets the proxy inject the secret at the network
edge — the same path every other authenticated call in this package takes.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.capability.metadata import SideEffectLevel
from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    ResourceReader,
    SweepBudget,
)
from platform.estate.health.mapping import StatusMapping
from platform.persistence.ports.estate_repository import ResourceHealth

#: The integration-facing name for the protocol. Aliased rather than subclassed:
#: a second Protocol would be a second thing to keep in step, and structural
#: typing means an implementation satisfies both under either name anyway.
ResourceDiscovery = ResourceReader


def declare(
    integration: str,
    *,
    kinds: tuple[str, ...],
    interval_seconds: int,
    rate_limit_per_minute: int,
    max_provider_calls: int,
    supports_incremental: bool = False,
) -> DiscoveryDeclaration:
    """Return the declaration for one integration's discovery capability.

    A function rather than a bare constructor call so that the side-effect level
    is supplied here, once, instead of at eighty call sites where one of them
    would eventually be wrong. Discovery reads; a discovery that wrote would
    change the estate it is describing, and there is no deployment in which that
    is what somebody wanted.
    """
    return DiscoveryDeclaration(
        integration=integration,
        kinds=kinds,
        supports_incremental=supports_incremental,
        interval_seconds=interval_seconds,
        max_provider_calls=max_provider_calls,
        rate_limit_per_minute=rate_limit_per_minute,
        side_effect_level=SideEffectLevel.READ,
    )


def status_mapping(
    integration: str,
    overrides: Mapping[str, ResourceHealth],
) -> StatusMapping:
    """Return this integration's translation from its own status words.

    Only the words that differ from the shared vocabulary. A provider whose
    ``running`` means running declares nothing, and a provider for which
    ``active`` means "provisioning, not yet serving" says so here rather than in
    a comment nobody reads.
    """
    return StatusMapping(source=integration, overrides=overrides)


__all__ = [
    "DiscoveredResource",
    "DiscoveryDeclaration",
    "DiscoveryMode",
    "DiscoveryPage",
    "ResourceDiscovery",
    "SweepBudget",
    "declare",
    "status_mapping",
]
