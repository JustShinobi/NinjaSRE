"""What storage raises, named so a caller can tell the cases apart.

Every failure here is one a caller might reasonably handle differently, which is
the only justification for a distinct type. A pool that is exhausted is retried;
a tenant-scope violation is a bug and must never be; a topology that is
unavailable is degraded operation the platform is designed to survive
(FR-002).

Two rules hold across all of them.

**No message carries secret material.** FR-019 is not satisfied by scrubbing
logs, because an exception string reaches places logs do not — a traceback in a
console, an error field in an API response. ``CredentialError`` and its
subclasses therefore identify a credential by handle and never by value, and
there is no code path that puts a decrypted value into an exception.

**No message carries another tenant's data.** A cross-tenant read that failed
must not report what it would have returned, or the error becomes the leak the
check prevented.
"""

from __future__ import annotations


class PersistenceError(Exception):
    """Base for every failure raised by the persistence layer."""


# --- Availability ------------------------------------------------------------


class StoreUnavailable(PersistenceError):
    """The datastore could not be reached."""


class PoolExhausted(StoreUnavailable):
    """No connection became free within the pool timeout (FR-020).

    The message names the limit and the wait, because the two together are the
    actionable part: "raise ``DATABASE_POOL_MAX_SIZE``" is advice a reader can
    act on, "connection error" is not.
    """

    def __init__(self, *, pool_size: int, timeout_seconds: float) -> None:
        super().__init__(
            f"No database connection became free within {timeout_seconds:g}s "
            f"and the pool is at its limit of {pool_size}. Either the deployment "
            f"is running more concurrent investigations than the pool is sized "
            f"for, or a caller is holding a unit of work open across an await "
            f"that does not need one."
        )
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds


class ExtensionUnavailable(StoreUnavailable):
    """A required PostgreSQL extension is not installed."""

    def __init__(self, extension: str) -> None:
        super().__init__(f"The PostgreSQL extension {extension!r} is not available.")
        self.extension = extension


class TopologyUnavailable(PersistenceError):
    """Graph storage is not usable, so topology answers cannot be given (FR-002).

    Raised rather than returned empty. An empty blast radius and an unknown
    blast radius lead to opposite decisions, and a caller that cannot tell them
    apart will eventually act on the wrong one.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Service topology is unavailable: {reason}")
        self.reason = reason


class MigrationsPending(PersistenceError):
    """The schema is behind the code that is trying to use it."""

    def __init__(self, *, applied: str | None, head: str) -> None:
        at = applied or "an empty database"
        super().__init__(f"The schema is at {at} and the code expects {head}.")
        self.applied = applied
        self.head = head


# --- Records -----------------------------------------------------------------


class RecordNotFound(PersistenceError):
    """No record exists with the given identity."""

    def __init__(self, *, kind: str, identifier: str) -> None:
        super().__init__(f"No {kind} with id {identifier!r}.")
        self.kind = kind
        self.identifier = identifier


class DuplicateRecord(PersistenceError):
    """A record already exists under an identity that must be unique."""

    def __init__(self, *, kind: str, identifier: str) -> None:
        super().__init__(f"A {kind} already exists with id {identifier!r}.")
        self.kind = kind
        self.identifier = identifier


class ConcurrentModification(PersistenceError):
    """The record changed between the read and the write.

    Optimistic concurrency, surfaced rather than resolved. Two investigations
    writing the same config node is not a case the store can merge, and picking
    a winner silently is how the losing write becomes a mystery.
    """

    def __init__(self, *, kind: str, identifier: str, expected: int, found: int) -> None:
        super().__init__(
            f"{kind} {identifier!r} was at version {expected} when it was read "
            f"and is at version {found} now."
        )
        self.kind = kind
        self.identifier = identifier
        self.expected = expected
        self.found = found


class ReferencedRecord(PersistenceError):
    """A record cannot be removed because something still points at it.

    Refused rather than cascaded. Deleting a team node would take the
    configuration of every service beneath it, and an operator who meant to
    rename something should find out before that happens rather than after.
    Where a cascade *is* right — a knowledge document and its chunks — the port
    says so and does it.
    """

    def __init__(self, *, kind: str, identifier: str, referenced_by: str) -> None:
        super().__init__(
            f"{kind} {identifier!r} cannot be removed while {referenced_by} still refers to it."
        )
        self.kind = kind
        self.identifier = identifier
        self.referenced_by = referenced_by


class PayloadTooLarge(PersistenceError):
    """A JSONB payload exceeds the row-size bound."""

    def __init__(self, *, kind: str, size_bytes: int, limit_bytes: int) -> None:
        super().__init__(
            f"A {kind} payload of {size_bytes} bytes exceeds the {limit_bytes}-byte limit. "
            f"Store the body through the evidence path and keep the reference here."
        )
        self.kind = kind
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes


# --- Tenancy -----------------------------------------------------------------


class TenantScopeViolation(PersistenceError):
    """A unit of work touched a record belonging to another tenant (FR-010).

    Reaching this exception means a defect, not a permissions decision: the
    ports take no organisation argument, so there is no legitimate way for a
    caller to name a tenant other than its own. The message says which
    organisations disagreed and nothing whatsoever about the record, because
    reporting the record here would be the leak the scoping exists to prevent.
    """

    def __init__(self, *, scope_org_id: str, record_org_id: str, kind: str) -> None:
        super().__init__(
            f"A unit of work scoped to organisation {scope_org_id!r} reached a "
            f"{kind} belonging to organisation {record_org_id!r}."
        )
        self.scope_org_id = scope_org_id
        self.record_org_id = record_org_id
        self.kind = kind


# --- Append-only and retention ------------------------------------------------


class AppendOnlyViolation(PersistenceError):
    """Something tried to change or remove an immutable record."""

    def __init__(self, *, kind: str, identifier: str) -> None:
        super().__init__(f"{kind} {identifier!r} is append-only and cannot be changed.")
        self.kind = kind
        self.identifier = identifier


class RetentionExempt(PersistenceError):
    """A retention pass tried to delete a data class that is never deleted (FR-022)."""

    def __init__(self, data_class: str) -> None:
        super().__init__(
            f"The {data_class!r} data class is exempt from retention deletion. "
            f"An audit trail with a deletion path is not an audit trail."
        )
        self.data_class = data_class


# --- Vector ------------------------------------------------------------------


class VectorNamespaceUnknown(PersistenceError):
    """A vector operation named an index that was never declared."""

    def __init__(self, namespace: str) -> None:
        super().__init__(
            f"No vector index named {namespace!r} has been declared. "
            f"Call ensure() with the embedding model and dimension first."
        )
        self.namespace = namespace


class EmbeddingDimensionMismatch(PersistenceError):
    """A vector's width is not the width its index was built for (FR-012).

    Loud on write, deliberately. A mismatched embedding that is accepted and
    truncated, or accepted into a differently-shaped index, does not fail — it
    returns neighbours that are merely wrong, which is the failure mode nobody
    notices until the retrieval quality has been bad for a month.
    """

    def __init__(self, *, namespace: str, expected: int, found: int) -> None:
        super().__init__(
            f"Vector index {namespace!r} holds {expected}-dimensional embeddings "
            f"and was given a {found}-dimensional one. An embedding model change "
            f"needs a re-embedding generation, not a write."
        )
        self.namespace = namespace
        self.expected = expected
        self.found = found


class EmbeddingModelMismatch(PersistenceError):
    """A vector was produced by a different model than the index records."""

    def __init__(self, *, namespace: str, expected: str, found: str) -> None:
        super().__init__(
            f"Vector index {namespace!r} holds embeddings from {expected!r} "
            f"and was given one from {found!r}."
        )
        self.namespace = namespace
        self.expected = expected
        self.found = found


class GenerationNotFound(PersistenceError):
    """A re-embedding generation was named that does not exist."""

    def __init__(self, *, namespace: str, generation: int) -> None:
        super().__init__(f"Vector index {namespace!r} has no generation {generation}.")
        self.namespace = namespace
        self.generation = generation


# --- Bounds ------------------------------------------------------------------


class BoundExceeded(PersistenceError):
    """A caller asked for more than a named constant permits.

    Rejected rather than clamped. A traversal that silently came back at depth
    5 when the caller asked for 40 reports a blast radius that looks complete
    and is not, and the caller has no way to tell.
    """

    def __init__(self, *, parameter: str, requested: int, limit: int, constant: str) -> None:
        super().__init__(
            f"{parameter} was {requested}, above the limit of {limit} set by {constant}."
        )
        self.parameter = parameter
        self.requested = requested
        self.limit = limit
        self.constant = constant


# --- Credentials -------------------------------------------------------------


class CredentialError(PersistenceError):
    """Base for credential storage failures. Never carries a secret value."""


class CredentialUndecryptable(CredentialError):
    """A stored credential could not be decrypted with the configured key.

    Almost always a key that changed or was never carried across a restore.
    The health check reports it at start, because the alternative is finding
    out during an incident, from the one integration that mattered.
    """

    def __init__(self, handle: str) -> None:
        super().__init__(
            f"The credential {handle!r} cannot be decrypted with the configured key. "
            f"The encryption key differs from the one that wrote it."
        )
        self.handle = handle


__all__ = [
    "AppendOnlyViolation",
    "BoundExceeded",
    "ConcurrentModification",
    "CredentialError",
    "CredentialUndecryptable",
    "DuplicateRecord",
    "EmbeddingDimensionMismatch",
    "EmbeddingModelMismatch",
    "ExtensionUnavailable",
    "GenerationNotFound",
    "MigrationsPending",
    "PayloadTooLarge",
    "PersistenceError",
    "PoolExhausted",
    "RecordNotFound",
    "ReferencedRecord",
    "RetentionExempt",
    "StoreUnavailable",
    "TenantScopeViolation",
    "TopologyUnavailable",
    "VectorNamespaceUnknown",
]
