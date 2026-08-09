"""Proxmox's own words for a state, translated into the estate's closed set.

Only the words that differ from the shared vocabulary. Proxmox agrees with
everybody about ``running``, ``stopped`` and ``available``, so those are not here;
what is here are the four it says differently, and one of them is the reason this
module exists rather than being a dictionary literal in the discovery source.

``template`` is a guest that is not running **by design**. It is the base image
other guests are cloned from and it will never start. Mapped to ``unhealthy`` it
would add a permanent fault to every estate that uses templates, and the fastest
way to make an operator ignore a problem count is to put a number in it that
never goes down.

``unknown`` is Proxmox's answer for a datastore whose mount is down and for a
guest on a node that is not answering. It maps to ``unknown``, which is the
honest verdict: we looked, and we cannot say. The alternative — treating an
unreadable datastore as healthy — is precisely the failure this wave exists to
prevent.
"""

from __future__ import annotations

from typing import Final

from integrations._base.discovery import status_mapping
from integrations.proxmox.schema import INTEGRATION
from platform.persistence.ports.estate_repository import ResourceHealth

#: Proxmox's own vocabulary, where it differs from the shared table.
PROXMOX_STATUS_MAPPING: Final = status_mapping(
    INTEGRATION,
    {
        # A node the cluster cannot currently reach. The shared table already
        # says offline is unhealthy; declared here because on a node it means
        # something specific — the guests on it are unreadable, not gone.
        "offline": ResourceHealth.UNHEALTHY,
        # A guest that exists to be cloned. Never runs, and is not a fault.
        "template": ResourceHealth.MAINTENANCE,
        # What Proxmox says about a datastore whose mount is down, and about a
        # guest whose node is not answering.
        "unknown": ResourceHealth.UNKNOWN,
        # The state a guest is in while a backup, a migration or a snapshot
        # holds its lock. Transient by definition, and reporting it as a fault
        # would make every backup window look like an outage.
        "prelaunch": ResourceHealth.MAINTENANCE,
    },
)

__all__ = ["PROXMOX_STATUS_MAPPING"]
