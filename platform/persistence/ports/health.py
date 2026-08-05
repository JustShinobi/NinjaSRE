"""What "the store is fine" decomposes into, so a failing deployment says which part.

FR-023 asks for connectivity, extension availability, and migration status. They
are reported separately rather than as one boolean because they fail for
different reasons and are fixed by different people: connectivity is the
network, extensions are the image, migrations are the release.

The distinction that earns its keep is ``DEGRADED``. A deployment without Apache
AGE cannot answer topology questions and is otherwise entirely functional
(FR-002), so reporting it as unavailable would take a working platform out of
rotation. Reporting it as healthy would hide the reason blast-radius queries
started failing. It is degraded, the reason says which capability is missing,
and readiness still passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class HealthState(StrEnum):
    """How usable the store is.

    ``DEGRADED`` is a deployment that works with a named capability missing.
    ``UNAVAILABLE`` is one that cannot serve investigations at all.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ExtensionStatus:
    """Whether one PostgreSQL extension is present, and at what version."""

    name: str
    available: bool
    version: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    """Where the schema is, against where the running code expects it to be."""

    head_revision: str
    applied_revision: str | None = None

    @property
    def is_current(self) -> bool:
        """Return whether the applied schema matches the code's head revision."""
        return self.applied_revision == self.head_revision


@dataclass(frozen=True, slots=True)
class StoreHealth:
    """The whole picture, as one value a health endpoint can render.

    ``reasons`` accumulates every finding rather than stopping at the first.
    An operator whose deployment is missing an extension *and* behind on
    migrations should learn both from one probe, not from two restarts.
    """

    state: HealthState
    connected: bool = False
    server_version: int | None = None
    extensions: tuple[ExtensionStatus, ...] = ()
    migrations: MigrationStatus | None = None
    undecryptable_credentials: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_ready(self) -> bool:
        """Return whether the deployment should accept work.

        Degraded counts as ready. A platform that cannot draw a blast radius
        can still investigate, and taking it out of rotation for that would
        turn a missing feature into an outage.
        """
        return self.state is not HealthState.UNAVAILABLE

    @property
    def is_live(self) -> bool:
        """Return whether the process should stay running.

        Only connectivity. A restart fixes a missing extension in no deployment
        that has ever existed, and restarting on an unmigrated schema turns a
        stalled release into a crash loop.
        """
        return self.connected

    def extension(self, name: str) -> ExtensionStatus | None:
        """Return the status of one extension by name, or ``None`` if unprobed."""
        for status in self.extensions:
            if status.name == name:
                return status
        return None


__all__ = [
    "ExtensionStatus",
    "HealthState",
    "MigrationStatus",
    "StoreHealth",
]
