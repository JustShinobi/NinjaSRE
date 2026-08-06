"""What this package raises, named so a caller can tell the cases apart.

Every type here is one an operator meets in a different situation and fixes in
a different way. A locked field is somebody else's decision they have to argue
with; a missing required field is their own document being incomplete; a
secret in configuration is a mistake they must fix at the source and never
retry unchanged.

**No message quotes a matched secret.** ``SecretInConfiguration`` names the
path and the rule and points at the vault, and never the value — a refusal that
echoed the secret would put it in the log, the trace, and the console, which is
where the refusal was keeping it out of.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from config.constants.config_service import MAX_REPORTED_FIELD_ERRORS


class ConfigServiceError(Exception):
    """Base for every failure raised by the configuration service."""


# --- The hierarchy -----------------------------------------------------------


class UnknownNode(ConfigServiceError):
    """Something named a node that does not exist in this tenant's tree."""

    def __init__(self, node_id: str) -> None:
        super().__init__(f"No configuration node {node_id!r} exists in this organisation.")
        self.node_id = node_id


class NodeHasDescendants(ConfigServiceError):
    """A deletion would have orphaned the configuration beneath it (FR-004).

    Names the descendants rather than counting them. An operator deleting a
    division needs to know which teams are about to lose their inheritance, and
    "3 descendants" does not tell them.
    """

    def __init__(self, node_id: str, descendants: Sequence[str]) -> None:
        listed = ", ".join(sorted(descendants))
        super().__init__(
            f"{node_id!r} still has descendants ({listed}) that inherit from it. Reparent "
            f"them explicitly, or delete them first."
        )
        self.node_id = node_id
        self.descendants = tuple(sorted(descendants))


class HierarchyCycle(ConfigServiceError):
    """A hierarchy has no single root, or a reparent would have made one."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class HierarchyTooDeep(ConfigServiceError):
    """The tree is deeper than every resolution beneath it can afford."""

    def __init__(self, depth: int, limit: int) -> None:
        super().__init__(
            f"This hierarchy is {depth} levels deep and the limit is {limit}. Every "
            f"investigation pays for the depth at resolution time."
        )
        self.depth = depth
        self.limit = limit


class ConfigTooDeep(ConfigServiceError):
    """One configuration document nests further than the merge will recurse."""

    def __init__(self, path: str, limit: int) -> None:
        super().__init__(
            f"The configuration at {path!r} nests beyond {limit} levels. Configuration is a "
            f"declared schema, not a tree of arbitrary depth."
        )
        self.path = path
        self.limit = limit


# --- Field policies ----------------------------------------------------------


class FieldLocked(ConfigServiceError):
    """A write tried to override a field an ancestor locked (FR-005).

    Names the locking node. A constraint whose origin is not visible is the one
    an operator routes around instead of arguing with.
    """

    def __init__(self, path: str, locking_node_id: str, node_id: str) -> None:
        super().__init__(
            f"{node_id!r} may not set {path!r}: it is locked at {locking_node_id!r}. "
            f"Change it there, or ask for the lock to be lifted."
        )
        self.path = path
        self.locking_node_id = locking_node_id
        self.node_id = node_id


class LockConflict(ConfigServiceError):
    """A lock was added where a descendant already overrides the field (FR-009).

    Refused rather than applied. Applying it would silently change what those
    descendants resolve to, and the operator adding the lock is the one person
    who cannot see that happen.
    """

    def __init__(self, path: str, node_id: str, overriding: Sequence[str]) -> None:
        listed = ", ".join(sorted(overriding))
        super().__init__(
            f"Cannot lock {path!r} at {node_id!r}: {listed} already override it. Resolve "
            f"those overrides explicitly — locking now would change what they resolve to "
            f"without anybody deciding to."
        )
        self.path = path
        self.node_id = node_id
        self.overriding = tuple(sorted(overriding))


# --- Validation --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldError:
    """One thing wrong with one field, at the path the operator wrote it at."""

    path: str
    message: str

    def __str__(self) -> str:
        """Return the path and the problem, as one line."""
        return f"{self.path}: {self.message}"


class ConfigInvalid(ConfigServiceError):
    """A configuration document was refused before it reached storage (FR-011).

    Carries every error rather than the first, up to a bound. An operator
    fixing a document one field per submission stops using the document.
    """

    def __init__(self, errors: Sequence[FieldError]) -> None:
        reported = tuple(errors[:MAX_REPORTED_FIELD_ERRORS])
        listed = "\n  - ".join(str(error) for error in reported)
        omitted = len(errors) - len(reported)
        suffix = f"\n  … and {omitted} more" if omitted > 0 else ""
        super().__init__(f"This configuration cannot be applied:\n  - {listed}{suffix}")
        self.errors = tuple(errors)

    def paths(self) -> tuple[str, ...]:
        """Return the paths that failed, in the order they were reported."""
        return tuple(error.path for error in self.errors)


class SecretInConfiguration(ConfigServiceError):
    """A configuration value looks like a credential (FR-013).

    The message names the path and the rule that fired and never the value.
    """

    def __init__(self, path: str, rule: str) -> None:
        super().__init__(
            f"The value at {path!r} matches the {rule!r} secret shape. Configuration holds "
            f"references, never secrets: store the credential in the vault and put its "
            f"reference here."
        )
        self.path = path
        self.rule = rule


# --- Approvals and templates -------------------------------------------------


class ChangeRequiresApproval(ConfigServiceError):
    """The write touched approval-gated fields and was queued instead (FR-007).

    Raised rather than returned, because the caller's next line would otherwise
    read as though the change had taken effect.
    """

    def __init__(self, node_id: str, paths: Sequence[str], approval_id: str) -> None:
        listed = ", ".join(sorted(paths))
        super().__init__(
            f"The change to {node_id!r} touches approval-gated fields ({listed}) and is "
            f"queued as {approval_id!r}. It takes effect when a human approves it."
        )
        self.node_id = node_id
        self.paths = tuple(sorted(paths))
        self.approval_id = approval_id


class UnknownTemplate(ConfigServiceError):
    """Something asked for a configuration template that is not installed."""

    def __init__(self, name: str, available: Sequence[str]) -> None:
        listed = ", ".join(sorted(available))
        super().__init__(f"No configuration template named {name!r}. Installed: {listed}.")
        self.name = name
        self.available = tuple(sorted(available))


__all__ = [
    "ChangeRequiresApproval",
    "ConfigInvalid",
    "ConfigServiceError",
    "ConfigTooDeep",
    "FieldError",
    "FieldLocked",
    "HierarchyCycle",
    "HierarchyTooDeep",
    "LockConflict",
    "NodeHasDescendants",
    "SecretInConfiguration",
    "UnknownNode",
    "UnknownTemplate",
]
