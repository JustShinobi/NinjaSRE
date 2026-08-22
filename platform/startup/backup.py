"""One artefact, one manifest, and the version check that happens before a write.

ADR 0004's single datastore is what makes a single backup artefact possible:
relational rows, ``pgvector`` embeddings, and the Apache AGE graph are one
database, so one dump covers all three and there is no second snapshot whose
consistency with the first somebody has to reason about.

What that leaves is a version problem, and it is the one this module owns. A
dump restored into a different release is either fine, fixable, or dangerous,
and the difference is knowable *before* anything is written — which is why the
manifest is a separate member of the artefact rather than a comment inside the
dump. It is read first.

Three answers, and the third is the point:

``restore``
    The backup's schema revision is the one this release expects. Restore it.

``migrate_forward``
    The backup is older, and this release ships every revision in between.
    Restore, then migrate — which is the ordinary case for an upgrade taken
    across a restore.

``refuse``
    The backup is from a newer release, or its extensions are not available
    here, or its credentials were encrypted under a key this deployment does not
    hold. Each of those is refused with the reason, because a partial restore is
    the failure mode that is discovered a week later.

The credential-key check is worth its own sentence. The dump carries ciphertext.
A restore into a deployment configured with a different key produces a database
that looks perfect and cannot authenticate anything, and the first discovery of
that is an incident. The manifest records the key's fingerprint — never the key
— so the mismatch is caught by reading a file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from config.constants.deployment import (
    BACKUP_MANIFEST_VERSION,
    RESTORE_ACTION_MIGRATE_FORWARD,
    RESTORE_ACTION_REFUSE,
    RESTORE_ACTION_RESTORE,
)
from platform.startup.errors import BackupIncompatible
from platform.startup.migrations import pending_revisions


class RestoreAction(StrEnum):
    """What a restore should do with a particular backup."""

    RESTORE = RESTORE_ACTION_RESTORE
    MIGRATE_FORWARD = RESTORE_ACTION_MIGRATE_FORWARD
    REFUSE = RESTORE_ACTION_REFUSE


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """What a backup knows about itself, read before its dump is touched.

    ``row_counts`` is what makes "integrity verified" a claim with a number
    behind it (FR-016): a restore compares the counts it finds against the ones
    the backup recorded, per data shape, and a dump truncated by a full disk
    stops being a dump that restores quietly.
    """

    schema_revision: str
    taken_at: datetime
    app_version: str = ""
    postgres_version: int | None = None
    extensions: dict[str, str] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)
    encryption_key_fingerprint: str = ""
    #: SHA-256 of the dump, hex. Empty on a manifest written before this
    #: existed, which is not a reason to refuse the archive.
    dump_sha256: str = ""
    manifest_version: int = BACKUP_MANIFEST_VERSION

    def to_record(self) -> dict[str, Any]:
        """Return the JSON document written beside the dump."""
        return {
            "manifest_version": self.manifest_version,
            "schema_revision": self.schema_revision,
            "taken_at": self.taken_at.isoformat(),
            "app_version": self.app_version,
            "postgres_version": self.postgres_version,
            "extensions": dict(self.extensions),
            "row_counts": dict(self.row_counts),
            "encryption_key_fingerprint": self.encryption_key_fingerprint,
            "dump_sha256": self.dump_sha256,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> BackupManifest:
        """Return the manifest ``record`` describes.

        Raises ``BackupIncompatible`` on a manifest this release cannot read.
        A manifest from the future is refused here rather than half-understood,
        because the fields it would be believed about are the ones the version
        check depends on.
        """
        version = int(record.get("manifest_version", 0))
        if version > BACKUP_MANIFEST_VERSION:
            raise BackupIncompatible(
                f"its manifest is version {version} and this release reads version "
                f"{BACKUP_MANIFEST_VERSION}. Restore it with the release that wrote it."
            )
        taken = record.get("taken_at")
        try:
            when = datetime.fromisoformat(str(taken)) if taken else datetime.now(UTC)
        except ValueError as error:
            raise BackupIncompatible("its manifest has no readable timestamp") from error
        revision = str(record.get("schema_revision", "")).strip()
        if not revision:
            raise BackupIncompatible(
                "its manifest names no schema revision, so there is no way to tell "
                "which release wrote it"
            )
        return cls(
            schema_revision=revision,
            taken_at=when,
            app_version=str(record.get("app_version", "")),
            postgres_version=(
                int(record["postgres_version"])
                if record.get("postgres_version") is not None
                else None
            ),
            extensions={str(k): str(v) for k, v in dict(record.get("extensions", {})).items()},
            row_counts={str(k): int(v) for k, v in dict(record.get("row_counts", {})).items()},
            encryption_key_fingerprint=str(record.get("encryption_key_fingerprint", "")),
            dump_sha256=str(record.get("dump_sha256", "")),
            manifest_version=version or BACKUP_MANIFEST_VERSION,
        )

    @classmethod
    def read(cls, path: Path) -> BackupManifest:
        """Return the manifest stored at ``path``."""
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BackupIncompatible(
                f"its manifest at {path} could not be read as JSON. A backup without "
                f"a manifest cannot be version-checked, and restoring one blind is "
                f"how a schema mismatch is discovered a week later."
            ) from error
        if not isinstance(record, dict):
            raise BackupIncompatible("its manifest is not a JSON object")
        return cls.from_record(record)

    def write(self, path: Path) -> Path:
        """Write this manifest beside a dump and return where it went."""
        path.write_text(json.dumps(self.to_record(), indent=2, sort_keys=True), encoding="utf-8")
        return path


@dataclass(frozen=True, slots=True)
class RestoreDecision:
    """What to do with a backup, and the reason, whichever way it went."""

    action: RestoreAction
    reason: str
    revisions_to_apply: tuple[str, ...] = ()

    @property
    def permitted(self) -> bool:
        """Return whether this backup may be restored at all."""
        return self.action is not RestoreAction.REFUSE

    def to_record(self) -> dict[str, object]:
        """Return the JSON-serialisable form the restore script prints."""
        return {
            "action": str(self.action),
            "reason": self.reason,
            "revisions_to_apply": list(self.revisions_to_apply),
        }

    def raise_if_refused(self) -> None:
        """Raise ``BackupIncompatible`` when this backup must not be restored."""
        if self.action is RestoreAction.REFUSE:
            raise BackupIncompatible(self.reason)


def decide_restore(
    manifest: BackupManifest,
    *,
    expected_revision: str,
    ordered_revisions: tuple[str, ...],
    available_extensions: tuple[str, ...] = (),
    encryption_key_fingerprint: str = "",
) -> RestoreDecision:
    """Return what this release should do with ``manifest``'s backup (FR-017).

    Every refusal names its reason. "Incompatible backup" is not a reason, and
    the person reading it is restoring during an outage.
    """
    if manifest.schema_revision == expected_revision:
        checked = _integrity_refusals(
            manifest,
            available_extensions=available_extensions,
            encryption_key_fingerprint=encryption_key_fingerprint,
        )
        if checked is not None:
            return checked
        return RestoreDecision(
            action=RestoreAction.RESTORE,
            reason=(
                f"the backup's schema revision {manifest.schema_revision} is the one "
                f"this release expects"
            ),
        )

    if manifest.schema_revision not in ordered_revisions:
        return RestoreDecision(
            action=RestoreAction.REFUSE,
            reason=(
                f"it was taken at schema revision {manifest.schema_revision}, which this "
                f"release does not ship. The backup is from a newer release — restore it "
                f"with that release, or upgrade this deployment first. Migrating a schema "
                f"forward from an unknown revision would leave one nobody can describe."
            ),
        )

    checked = _integrity_refusals(
        manifest,
        available_extensions=available_extensions,
        encryption_key_fingerprint=encryption_key_fingerprint,
    )
    if checked is not None:
        return checked

    pending = pending_revisions(applied=manifest.schema_revision, ordered=ordered_revisions)
    return RestoreDecision(
        action=RestoreAction.MIGRATE_FORWARD,
        reason=(
            f"it was taken at schema revision {manifest.schema_revision} and this release "
            f"expects {expected_revision}; {len(pending)} revision(s) apply after the restore"
        ),
        revisions_to_apply=pending,
    )


def _integrity_refusals(
    manifest: BackupManifest,
    *,
    available_extensions: tuple[str, ...],
    encryption_key_fingerprint: str,
) -> RestoreDecision | None:
    """Return a refusal for anything that would restore quietly and be wrong."""
    if available_extensions:
        missing = sorted(set(manifest.extensions) - set(available_extensions))
        if missing:
            return RestoreDecision(
                action=RestoreAction.REFUSE,
                reason=(
                    f"the backup uses PostgreSQL extension(s) this server does not have: "
                    f"{', '.join(missing)}. Install them before restoring; a dump that "
                    f"restores without them loses the data that needed them."
                ),
            )

    recorded = manifest.encryption_key_fingerprint
    if recorded and encryption_key_fingerprint and recorded != encryption_key_fingerprint:
        return RestoreDecision(
            action=RestoreAction.REFUSE,
            reason=(
                "its credentials were encrypted under a different key than this "
                "deployment holds. The restore would succeed and every stored "
                "credential would be unreadable. Restore the key that took the backup, "
                "or restore into a deployment configured with it."
            ),
        )
    return None


#: The marker a plain-format ``pg_dump`` puts before a table's rows, and the
#: one that ends them. Counting between the two is what makes a truncated
#: artefact detectable without a database — which matters, because truncation
#: happens while an archive is being copied between machines rather than while
#: it is being written.
COPY_PREFIX = "COPY "
COPY_TERMINATOR = "\\."


def dump_digest(dump: Path) -> str:
    """Return the SHA-256 of ``dump``, hex, read in chunks.

    The counts below answer "did rows go missing". This answers "is this the
    same file", which is a different question and the one a truncated copy
    fails. ``pg_dump`` writes the schema, then the data, then the indexes,
    constraints and foreign keys — so a transfer that stopped early usually
    loses the tail, and a tail holds no ``COPY`` rows. Every count matches, and
    what restores is a database with the right rows and none of the constraints
    that make them mean anything.
    """
    digest = hashlib.sha256()
    with dump.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_dump_digest(manifest: BackupManifest, dump: Path) -> str | None:
    """Return why ``dump`` is not the artefact the manifest describes, or ``None``.

    A manifest that records no digest was written before this existed, and is
    not refused for it: turning every backup taken so far into an unrestorable
    one would be a worse failure than the one this prevents.
    """
    if not manifest.dump_sha256:
        return None
    found = dump_digest(dump)
    if found == manifest.dump_sha256:
        return None
    return (
        f"the dump does not match the manifest: recorded {manifest.dump_sha256[:12]}…, "
        f"found {found[:12]}… ({dump.stat().st_size} bytes). The archive was truncated or "
        f"altered after it was written."
    )


def row_counts_in(dump: Path) -> dict[str, int]:
    """Return how many rows ``dump`` holds for each table, by table name.

    Read out of the artefact rather than out of a database, on purpose. The
    failure this exists to catch is a dump that was cut short after it was
    taken, and the database it came from is long since unavailable by the time
    anybody notices.
    """
    counts: dict[str, int] = {}
    table = ""
    with dump.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if table:
                if line.rstrip("\n") == COPY_TERMINATOR:
                    table = ""
                else:
                    counts[table] = counts.get(table, 0) + 1
                continue
            if line.startswith(COPY_PREFIX) and " FROM stdin" in line:
                table = line[len(COPY_PREFIX) :].split(" ")[0].strip('"')
                counts.setdefault(table, 0)
    return counts


def verify_row_counts(
    manifest: BackupManifest,
    observed: dict[str, int],
) -> tuple[str, ...]:
    """Return one sentence per data shape whose count does not match (FR-016, SC-004).

    Empty means the restore is intact by the only measure a script can take
    without knowing what the rows mean. A shape the backup recorded and the
    restore does not have at all is reported as zero rather than skipped —
    a missing table is the failure this check exists to catch.
    """
    problems: list[str] = []
    for shape, expected in sorted(manifest.row_counts.items()):
        found = observed.get(shape, 0)
        if found != expected:
            problems.append(
                f"{shape}: the backup recorded {expected} row(s) and the restore has {found}"
            )
    return tuple(problems)


__all__ = [
    "COPY_PREFIX",
    "COPY_TERMINATOR",
    "BackupManifest",
    "RestoreAction",
    "RestoreDecision",
    "decide_restore",
    "dump_digest",
    "row_counts_in",
    "verify_dump_digest",
    "verify_row_counts",
]
