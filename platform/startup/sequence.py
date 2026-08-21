"""The boot sequence, in the order it has to happen, with the reason for the order.

```
resolve profile → validate configuration → install the key → verify the key
    → migrate under a lock → check schema compatibility → report readiness
```

Three positions in that list are load-bearing rather than tidy.

**Installing the key comes before verifying it.** They were once one step in
name and neither in fact: verification asks the vault whether *stored*
credentials open, which is vacuously true on a deployment that has stored none,
so a ring nobody had loaded passed the check and refused the first credential
anybody wrote. Loading is its own step because a step that can be satisfied by
doing nothing is not a step.

**Key verification comes before migrations.** A deployment booting with the
wrong encryption key works perfectly until the first credential is needed, and
the first credential is needed during an incident. Checking first means a key
that did not survive a restore fails in seconds — before a schema change, so the
fix is "put the right key back" rather than "put the right key back and work out
what the half-migrated database now is".

**Validation comes before both.** Every check after it needs a database URL, and
a connection failure caused by an unset variable reports as a connection failure.

Nothing here opens a socket itself. The steps that need one take a collaborator:
``verify_credentials`` is the vault's startup check, ``migrator`` is the schema
port. That is what lets the whole sequence be driven in a unit test, which is
the only way the ordering above is actually protected against a future edit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from platform.startup.migrations import MigrationOutcome, SchemaMigrator, apply_at_startup
from platform.startup.profiles import DeploymentProfile, ProfileTopology, resolve_topology
from platform.startup.readiness import ReadinessReport
from platform.startup.validation import ValidationReport, validate

#: What the sequence calls to prove the configured key opens what is stored.
#: Raises on a mismatch — ``platform.credentials.health.verify_startup`` is the
#: implementation, and it raises ``VaultKeyMismatch`` naming the handles.
CredentialCheck = Callable[[], Awaitable[None]]

#: What the sequence calls to load the operator's key into the process.
#:
#: Returns whether there was one to load. An absent key is not fatal — a
#: deployment that stores no credential should not fail to start over a key it
#: will never use — but the result records the answer, so "no key" is a fact the
#: boot report carries rather than a silence discovered at the first write.
KeyInstaller = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class StartupResult:
    """What the boot sequence established, for the log line and the health endpoint."""

    topology: ProfileTopology
    validation: ValidationReport
    migration: MigrationOutcome | None = None
    readiness: ReadinessReport | None = None
    credentials_verified: bool = False
    key_installed: bool = False

    @property
    def profile(self) -> DeploymentProfile:
        """Return the profile this deployment resolved to."""
        return self.topology.profile

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form a health endpoint serves."""
        return {
            "topology": self.topology.to_record(),
            "validation": self.validation.to_record(),
            "migration": None if self.migration is None else self.migration.to_record(),
            "readiness": None if self.readiness is None else self.readiness.to_record(),
            "credentials_verified": self.credentials_verified,
            "key_installed": self.key_installed,
        }

    def summary(self) -> str:
        """Return the block a deployment prints once it is up."""
        lines = [self.topology.summary()]
        if self.validation.warnings:
            lines.extend(f"  [advisory] {finding}" for finding in self.validation.warnings)
        if self.key_installed:
            lines.append("the encryption key is loaded")
        if self.credentials_verified:
            lines.append("stored credentials open with the configured key")
        if self.migration is not None:
            lines.append(self.migration.summary())
        if self.readiness is not None:
            lines.append(self.readiness.summary())
        return "\n".join(lines)


async def run_startup(
    *,
    environ: Mapping[str, str] | None = None,
    migrator: SchemaMigrator | None = None,
    install_key: KeyInstaller | None = None,
    verify_credentials: CredentialCheck | None = None,
    readiness: ReadinessReport | None = None,
    apply_migrations: bool = True,
) -> StartupResult:
    """Run the boot sequence and return what it established.

    Every collaborator is optional so a deployment can run the part it owns: a
    Helm release migrates in a job and passes ``apply_migrations=False``, and an
    operator's preflight passes neither collaborator and gets validation alone.

    Raises:
        UnknownDeploymentProfile: the profile setting names no known profile.
        ConfigurationInvalid: validation found something fatal.
        VaultKeyMismatch: stored credentials do not open with the configured key.
        SchemaIncompatible: the schema is not one this release can run against.
        MigrationFailed: a revision raised, and the message says where it stopped.
    """
    topology = resolve_topology(environ)

    report = validate(environ)
    report.raise_if_invalid()

    installed = False
    if install_key is not None:
        # Before the check below, which cannot verify what has not been loaded.
        installed = install_key()

    verified = False
    if verify_credentials is not None:
        # Before migrations, on purpose. See the module docstring.
        await verify_credentials()
        verified = True

    outcome: MigrationOutcome | None = None
    if migrator is not None:
        outcome = await apply_at_startup(migrator, apply=apply_migrations)

    return StartupResult(
        topology=topology,
        validation=report,
        migration=outcome,
        readiness=readiness,
        credentials_verified=verified,
        key_installed=installed,
    )


__all__ = ["CredentialCheck", "KeyInstaller", "StartupResult", "run_startup"]
