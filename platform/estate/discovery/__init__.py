"""Finding out what is out there, on a schedule, without holding a credential.

Three modules. ``port`` is the contract a source implements and the records it
speaks in. ``reconcile`` turns what a source reported into what the estate
stores, which is where identity derivation, multi-source attribution and the
changed-parent case live. ``sweep`` runs one pass: it claims, reads, ingests,
concludes, and records — in that order, because the order is what makes a failed
read unable to conclude anything.
"""

from __future__ import annotations

from platform.estate.discovery.port import (
    DiscoveredResource,
    DiscoveryDeclaration,
    DiscoveryMode,
    DiscoveryPage,
    ResourceReader,
    SweepBudget,
)
from platform.estate.discovery.sweep import EstateSweeper, SweepReport

__all__ = [
    "DiscoveredResource",
    "DiscoveryDeclaration",
    "DiscoveryMode",
    "DiscoveryPage",
    "EstateSweeper",
    "ResourceReader",
    "SweepBudget",
    "SweepReport",
]
