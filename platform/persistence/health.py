"""Turning what a probe found into whether the deployment should take work.

The probing is a backend's job — it is the part that needs a connection. The
*judgement* is here, as a pure function over what came back, for two reasons.

It is the half that is worth testing, and it is testable with no database at
all. Every rule below is a decision about how a deployment behaves when
something is missing, and every one of them can be got wrong in a way that
takes a working platform out of rotation or leaves a broken one in it.

And it is one judgement rather than one per backend. A second implementation of
these ports gets the same answers to "is a missing AGE fatal" as the first,
because it does not answer that question — it reports what it found and calls
``summarise``.
"""

from __future__ import annotations

from config.constants.persistence import (
    DEGRADABLE_POSTGRES_EXTENSIONS,
    MINIMUM_POSTGRES_VERSION,
    REQUIRED_POSTGRES_EXTENSIONS,
)
from platform.persistence.ports.health import (
    ExtensionStatus,
    HealthState,
    MigrationStatus,
    StoreHealth,
)

#: Ordered worst-first, so the overall state is the first one anything reported.
_SEVERITY: tuple[HealthState, ...] = (
    HealthState.UNAVAILABLE,
    HealthState.DEGRADED,
    HealthState.HEALTHY,
)


def _worst(states: tuple[HealthState, ...]) -> HealthState:
    """Return the least healthy state present, or healthy when none were reported."""
    for candidate in _SEVERITY:
        if candidate in states:
            return candidate
    return HealthState.HEALTHY


def summarise(
    *,
    connected: bool,
    server_version: int | None = None,
    extensions: tuple[ExtensionStatus, ...] = (),
    migrations: MigrationStatus | None = None,
    undecryptable_credentials: tuple[str, ...] = (),
    failure: str | None = None,
) -> StoreHealth:
    """Return the store's overall health from what a probe observed (FR-023).

    Every finding is collected before a state is chosen, so an operator whose
    deployment is behind on migrations *and* missing an extension learns both
    from one probe rather than from two restarts.
    """
    findings: list[HealthState] = []
    reasons: list[str] = []

    if not connected:
        # Nothing else was observable, so nothing else is reported. A probe that
        # could not connect has no opinion on extensions it never queried.
        return StoreHealth(
            state=HealthState.UNAVAILABLE,
            connected=False,
            reasons=(failure or "The database could not be reached.",),
        )

    if server_version is not None and server_version < MINIMUM_POSTGRES_VERSION:
        findings.append(HealthState.UNAVAILABLE)
        reasons.append(
            f"PostgreSQL {server_version} is below the required "
            f"{MINIMUM_POSTGRES_VERSION}; pgvector's HNSW indexes and Apache AGE both assume it."
        )

    findings.extend(_extension_findings(extensions, reasons))

    if migrations is None:
        findings.append(HealthState.UNAVAILABLE)
        reasons.append("Migration status is unknown, so the schema cannot be trusted.")
    elif not migrations.is_current:
        findings.append(HealthState.UNAVAILABLE)
        applied = migrations.applied_revision or "an empty database"
        reasons.append(
            f"The schema is at {applied} and this release expects "
            f"{migrations.head_revision}. Migrations have not finished."
        )

    if undecryptable_credentials:
        findings.append(HealthState.DEGRADED)
        reasons.append(
            f"{len(undecryptable_credentials)} stored credential(s) cannot be decrypted "
            f"with the configured key: {', '.join(sorted(undecryptable_credentials))}."
        )

    if failure:
        findings.append(HealthState.DEGRADED)
        reasons.append(failure)

    return StoreHealth(
        state=_worst(tuple(findings)),
        connected=True,
        server_version=server_version,
        extensions=extensions,
        migrations=migrations,
        undecryptable_credentials=undecryptable_credentials,
        reasons=tuple(reasons),
    )


def _extension_findings(
    extensions: tuple[ExtensionStatus, ...],
    reasons: list[str],
) -> list[HealthState]:
    """Return one finding per required extension that is missing, appending reasons.

    A required extension nobody probed counts as missing. The alternative is a
    deployment reporting healthy because the probe forgot to look, which is the
    failure mode a health check exists to make impossible.
    """
    observed = {status.name: status for status in extensions}
    findings: list[HealthState] = []

    for name in REQUIRED_POSTGRES_EXTENSIONS:
        status = observed.get(name)
        if status is not None and status.available:
            continue
        if name in DEGRADABLE_POSTGRES_EXTENSIONS:
            findings.append(HealthState.DEGRADED)
            reasons.append(
                f"The {name!r} extension is unavailable. Service topology — blast "
                f"radius, dependency lookup, shortest path — cannot be answered until "
                f"it is installed. Everything else works."
            )
        else:
            findings.append(HealthState.UNAVAILABLE)
            reasons.append(
                f"The {name!r} extension is unavailable, so episodic recall and "
                f"knowledge retrieval cannot work."
            )

    return findings


__all__ = ["summarise"]
