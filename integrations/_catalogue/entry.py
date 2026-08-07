"""What the platform knows about one integration, beyond its credential.

The descriptor answers the credential questions — what a credential is made of,
which hosts it may reach, how the secret enters a request. This answers the
operational ones: what class of thing this vendor is, what it can be asked to
do, what permissions that needs, where it lives, whether it is currently working,
and whether it is complete.

Two objects, and the split is between what a vendor *declares* and what the
build *computes*.

``IntegrationProfile`` is declared, in the vendor's own package, beside the
descriptor. It is the second half of "adding an integration edits zero existing
files": a category enum that a vendor had to be added to would be a central file,
and a central file is the thing this whole design exists to avoid.

``CatalogueEntry`` is computed — profile plus descriptor plus the parity report
plus the health ledger — and is what the console renders and documentation
generation reads. Nothing constructs one by hand, because a hand-built entry is
one whose parity status is whatever the author believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from integrations._base.pagination import EndpointPagination
from integrations._base.regions import RegionMap
from integrations._catalogue.validation import ParityReport, ParityStatus
from integrations._verification.permissions import RequiredPermission
from platform.credentials.descriptor import IntegrationDescriptor


class IntegrationCategory(StrEnum):
    """What class of system a vendor is, which is what selects its methodology.

    The members are the domains the methodology templates cover, because those
    are the same eleven classes: a vendor's category is how the scaffold knows
    which investigative discipline its skill starts from. A twelfth kind of
    system is a twelfth template and a twelfth member, added together.
    """

    LOG_STORE = "logstore"
    METRICS_STORE = "metrics"
    TRACING = "tracing"
    CLOUD_CONTROL_PLANE = "cloud_control_plane"
    DATABASE = "database"
    VERSION_CONTROL = "vcs"
    CI_CD = "cicd"
    TICKETING = "ticketing"
    INCIDENT_MANAGEMENT = "incident"
    COMMUNICATION = "communication"
    DATA_PLATFORM = "data_platform"


class HealthStatus(StrEnum):
    """Whether an integration is currently working."""

    #: A live run succeeded.
    HEALTHY = "healthy"
    #: A live run failed. The integration stays installed and says what broke.
    DEGRADED = "degraded"
    #: Nothing has run against the live vendor. Not the same as healthy, and
    #: reporting it as healthy is the same failure as reporting a truncated
    #: answer as a complete one.
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class IntegrationProfile:
    """What one vendor package declares about itself.

    Exposed as ``PROFILE`` beside the package's ``DESCRIPTOR``, and found the
    same way — by walking, never by being listed.
    """

    integration: str
    category: IntegrationCategory
    summary: str
    regions: RegionMap
    permissions: tuple[RequiredPermission, ...] = ()
    pagination: tuple[EndpointPagination, ...] = ()

    def __post_init__(self) -> None:
        if self.regions.integration != self.integration:
            raise ValueError(
                f"the profile for {self.integration!r} carries a region map for "
                f"{self.regions.integration!r}"
            )
        if not self.summary.strip():
            raise ValueError(
                f"{self.integration}: a profile with no summary gives the console and the "
                f"generated documentation nothing to say about this vendor"
            )
        endpoints = [declared.endpoint for declared in self.pagination]
        duplicates = sorted({name for name in endpoints if endpoints.count(name) > 1})
        if duplicates:
            raise ValueError(
                f"{self.integration}: declares pagination for {duplicates} more than once"
            )


@dataclass(frozen=True, slots=True)
class CatalogueEntry:
    """One integration, as the console and documentation generation see it (FR-021)."""

    name: str
    profile: IntegrationProfile
    descriptor: IntegrationDescriptor
    parity: ParityReport
    capabilities: tuple[str, ...] = ()
    health: HealthStatus = HealthStatus.UNKNOWN
    health_detail: str = ""

    @property
    def category(self) -> IntegrationCategory:
        """Return what class of system this vendor is."""
        return self.profile.category

    @property
    def summary(self) -> str:
        """Return the one line describing what this integration is for."""
        return self.profile.summary

    @property
    def required_credentials(self) -> tuple[str, ...]:
        """Return the credential fields an operator has to supply."""
        return self.descriptor.schema.required_names

    @property
    def required_permissions(self) -> tuple[str, ...]:
        """Return the vendor permissions this integration's capabilities need."""
        return tuple(permission.name for permission in self.profile.permissions)

    @property
    def regions(self) -> tuple[str, ...]:
        """Return every region this vendor can be reached in."""
        return self.profile.regions.names()

    @property
    def usable(self) -> bool:
        """Return whether this integration is complete and not known to be broken."""
        return self.parity.status is ParityStatus.COMPLETE and self.health is not (
            HealthStatus.DEGRADED
        )

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the console and docs generation read."""
        return {
            "name": self.name,
            "category": self.category.value,
            "summary": self.summary,
            "capabilities": list(self.capabilities),
            "required_credentials": list(self.required_credentials),
            "required_permissions": list(self.required_permissions),
            "regions": list(self.regions),
            "health": self.health.value,
            "health_detail": self.health_detail,
            "parity": self.parity.status.value,
            "missing_artefacts": [artefact.value for artefact in self.parity.missing],
            "sdk_strategy": self.descriptor.sdk_strategy.value,
        }


__all__ = [
    "CatalogueEntry",
    "HealthStatus",
    "IntegrationCategory",
    "IntegrationProfile",
    "ParityStatus",
]
