"""Every installed integration, what it is, and whether it is complete.

Four modules. ``validation`` checks the seven artefacts, ``entry`` holds what a
vendor declares and what the build computes, ``health`` records what the live
runs found, and ``discovery`` assembles the three by walking the package tree.

Nothing here is a list of integrations, and that absence is the design. A
catalogue module naming its members is a module every new vendor has to edit,
and the edit somebody forgets is the one that makes an integration invisible
while everything reports healthy.
"""

from __future__ import annotations

from integrations._catalogue.discovery import (
    catalogue,
    entry,
    parity_reports,
    profiles,
    validate,
    vendor_packages,
)
from integrations._catalogue.entry import (
    CatalogueEntry,
    HealthStatus,
    IntegrationCategory,
    IntegrationProfile,
)
from integrations._catalogue.health import HealthLedger, HealthRecord
from integrations._catalogue.validation import (
    Artefact,
    ParityError,
    ParityReport,
    ParityStatus,
    artefacts,
    cost_of,
    parity_of,
    validate_parity,
)

__all__ = [
    "Artefact",
    "CatalogueEntry",
    "HealthLedger",
    "HealthRecord",
    "HealthStatus",
    "IntegrationCategory",
    "IntegrationProfile",
    "ParityError",
    "ParityReport",
    "ParityStatus",
    "artefacts",
    "catalogue",
    "cost_of",
    "entry",
    "parity_of",
    "parity_reports",
    "profiles",
    "validate",
    "validate_parity",
    "vendor_packages",
]
