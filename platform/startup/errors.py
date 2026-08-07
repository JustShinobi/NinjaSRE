"""What a deployment refuses to start over, and the rule every message obeys.

**A message names the setting and says what to do.** "Configuration error" is
not an error message, it is a prompt to read source code, and the person reading
it is usually the one who has just cloned the repository and has fifteen minutes
of patience. Every exception here carries the environment variable at fault and
a remedy phrased as an instruction.

**Nothing here carries a value.** A startup failure ends up in a container log,
a CI transcript, and a support ticket. Naming ``NINJASRE_DATABASE_URL`` is
actionable; printing it publishes a password.
"""

from __future__ import annotations

from collections.abc import Sequence


class StartupError(Exception):
    """Base for every refusal to start. Never carries a configured value."""


class UnknownDeploymentProfile(StartupError, ValueError):
    """The deployment named a profile that does not exist.

    Deliberately not a fallback to the default. A typo in a production
    deployment's profile would otherwise start the development shape — the
    in-process proxy, the process sandbox, single-host concurrency — and the
    only signal would be a log line nobody read.
    """

    def __init__(self, name: str, known: Sequence[str]) -> None:
        listed = ", ".join(known)
        super().__init__(
            f"{name!r} is not a deployment profile. Known profiles: {listed}. "
            f"Set the profile to one of those, or leave it unset for the default."
        )
        self.name = name
        self.known = tuple(known)


class ConfigurationInvalid(StartupError):
    """Startup validation found at least one fatal problem (FR-006).

    Carries every finding rather than the first. One restart per problem is how
    a ten-minute setup becomes an hour, and the operator already has all the
    information in front of them.
    """

    def __init__(self, summary: str, *, settings: Sequence[str]) -> None:
        super().__init__(summary)
        self.settings = tuple(settings)


class EncryptionKeyMissing(StartupError):
    """No encryption key was supplied, and one is never generated (FR-019).

    A silently-generated key ends up in a container layer or a compose file, and
    the operator does not learn it exists until they try to restore a backup on
    another host and find the credentials unreadable. Requiring it makes key
    management a decision somebody made on purpose.
    """

    def __init__(self, setting: str, *, generator_hint: str) -> None:
        super().__init__(
            f"{setting} is not set, and NinjaSRE does not generate an encryption "
            f"key for you. A key generated behind your back lives in a container "
            f"layer and is discovered missing during a restore. Generate one with "
            f"{generator_hint}, store it where your other secrets live, and set "
            f"{setting} to it."
        )
        self.setting = setting


class EncryptionKeyInvalid(StartupError):
    """The supplied key is not a key. Says which way, never what it was."""

    def __init__(self, setting: str, *, problem: str) -> None:
        super().__init__(f"{setting} is not usable: {problem}.")
        self.setting = setting
        self.problem = problem


class SchemaIncompatible(StartupError):
    """This release refuses to run against the schema it found (FR-014).

    Both directions are refused and they are different problems. A schema behind
    the code means migrations have not finished — which is recoverable by
    waiting or by running them. A schema *ahead* of the code means a rollback
    put an older release in front of a newer database, and continuing would have
    the old code write rows the new schema's constraints do not describe.
    """

    def __init__(self, *, applied: str | None, expected: str, ahead: bool) -> None:
        at = applied or "an empty database"
        if ahead:
            detail = (
                "The database has been migrated by a newer release than this one. "
                "Roll the application forward again, or restore the database from "
                "the backup taken before the upgrade."
            )
        else:
            detail = (
                "Migrations have not been applied. Start the deployment with "
                "migrations enabled, or run them out of band before serving traffic."
            )
        super().__init__(f"The schema is at {at} and this release expects {expected}. {detail}")
        self.applied = applied
        self.expected = expected
        self.ahead = ahead


class MigrationFailed(StartupError):
    """A revision raised part-way through, and the message says where it stopped.

    FR-012 asks that a failed migration leave the database in its pre-migration
    state or in a documented recoverable one, never an ambiguous one. Each
    revision commits on its own, so the schema is at the last one that
    succeeded — which is recoverable, and is only *documented* if something
    reads it back and reports it. This is that something.
    """

    def __init__(self, *, attempted: str, landed: str | None, reason: str) -> None:
        where = (
            f"the schema is at {landed}"
            if landed is not None
            else "the schema's revision could not be read back, so the database is not answering"
        )
        super().__init__(
            f"Migrating to {attempted} failed: {reason}. Every revision before the "
            f"failure committed, so {where}. Restore the pre-upgrade backup, or fix "
            f"the cause and start again — the run resumes from where it stopped."
        )
        self.attempted = attempted
        self.landed = landed
        self.reason = reason


class MigrationLockUnavailable(StartupError):
    """Another replica has held the migration lock longer than the wait allows.

    The realistic cause is not contention — the loser of a start-up race
    normally waits a second and finds nothing to do — but a process that died
    with its database session still open. Failing here rather than hanging is
    what makes that visible to whatever restarted the container.
    """

    def __init__(self, *, waited_seconds: float) -> None:
        super().__init__(
            f"The migration lock was still held after {waited_seconds:g}s. Another "
            f"replica is migrating, or a process died holding it. Check for a "
            f"running migration before clearing the lock."
        )
        self.waited_seconds = waited_seconds


class BackupIncompatible(StartupError):
    """A backup cannot be restored into this release, and the reason is named (FR-017)."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"This backup cannot be restored: {reason}")
        self.reason = reason


class EgressNotPermitted(StartupError):
    """Configuration implies an outbound connection the operator did not permit.

    Raised by the air-gapped check (FR-023, FR-024) before anything opens a
    socket. An air-gapped deployment that discovers its egress problem at the
    first investigation has discovered it during an incident.
    """

    def __init__(self, destinations: Sequence[str]) -> None:
        listed = ", ".join(sorted(destinations))
        super().__init__(
            f"This deployment is configured as air-gapped, and its configuration "
            f"still implies outbound connections to: {listed}. Point them at "
            f"on-host services, or remove the air-gapped setting."
        )
        self.destinations = tuple(sorted(destinations))


__all__ = [
    "BackupIncompatible",
    "ConfigurationInvalid",
    "EgressNotPermitted",
    "EncryptionKeyInvalid",
    "EncryptionKeyMissing",
    "MigrationFailed",
    "MigrationLockUnavailable",
    "SchemaIncompatible",
    "StartupError",
    "UnknownDeploymentProfile",
]
