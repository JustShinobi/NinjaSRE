"""The outbound half of transit: what leaves, to whom, and in how much detail.

The symmetric of ``platform/ingress``. A destination declares which events it
wants, which channel carries them, and how much of the result goes in the
message; the dispatcher decides what to send, sends it, and writes the attempt
into the same ledger the arrivals are in — so "where did this go" and "where did
this come from" are one query against one table.

**No new channel integrations.** A destination binds a channel this deployment
has already configured. A deployment with none renders its destinations as
unconfigurable with the reason, which is the 054 known-gap posture and is
honest: inventing an outbound integration to make a screen look finished would
be building the wrong thing.
"""

from __future__ import annotations

from platform.delivery.destinations import (
    DeclaredDestination,
    declared_destinations,
    delivery_channels,
)
from platform.delivery.dispatch import (
    DeliveryDispatcher,
    OutboundMessage,
    resend,
)

__all__ = [
    "DeclaredDestination",
    "DeliveryDispatcher",
    "OutboundMessage",
    "declared_destinations",
    "delivery_channels",
    "resend",
]
