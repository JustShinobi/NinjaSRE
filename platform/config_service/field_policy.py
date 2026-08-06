"""What a node declares about a field, beyond what its value is.

Five statements, all about one path:

``locked``
    No descendant may override it. The platform team's masking policy, the
    security team's guardrail ruleset.
``required``
    Effective configuration missing it fails validation. Not "has a default" —
    a field with a default is never missing. Required is for the values only the
    operator knows, and the point is that resolution fails loudly at the node
    that forgot rather than quietly at the incident that needed it.
``approval_gated``
    Changing it enters the approval queue rather than taking effect. Prompts and
    capability enablement change how production incidents are investigated, and
    that is not a change one person makes alone.
``allowed_values``
    A closed set. The model list an organisation has approved, the masking
    levels a regulator accepts.
``max_value`` / ``max_items``
    A ceiling on a number and on a collection's length. Iteration budgets and
    tool budgets are cost, and cost caps belong with the field rather than in a
    document describing what people ought to type.

Policies accumulate down the tree and never weaken. A descendant may add a lock
its ancestors did not declare; it may not remove one they did. ``PolicySet.
inherited_by`` is where that is enforced, and it is the reason a lock is
worth declaring at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence, Sized
from dataclasses import dataclass, field, replace
from typing import Any

from config.constants.config_service import MAX_FIELD_POLICIES
from platform.config_service import paths
from platform.config_service.errors import FieldError, FieldLocked, LockConflict


@dataclass(frozen=True, slots=True)
class FieldPolicy:
    """Everything one node declares about one path."""

    path: str
    locked: bool = False
    required: bool = False
    approval_gated: bool = False
    allowed_values: tuple[Any, ...] | None = None
    max_value: float | None = None
    max_items: int | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("A field policy needs the path it governs.")

    @property
    def is_empty(self) -> bool:
        """Return whether this policy says nothing, which makes it storage noise."""
        return not (
            self.locked
            or self.required
            or self.approval_gated
            or self.allowed_values is not None
            or self.max_value is not None
            or self.max_items is not None
        )

    def strengthened_by(self, other: FieldPolicy) -> FieldPolicy:
        """Return this policy with ``other``'s constraints added, never removed.

        A descendant tightening a ceiling wins; a descendant raising one is
        ignored, which is what makes a ceiling a ceiling. Allowed values
        intersect for the same reason.
        """
        return FieldPolicy(
            path=self.path,
            locked=self.locked or other.locked,
            required=self.required or other.required,
            approval_gated=self.approval_gated or other.approval_gated,
            allowed_values=_narrowest(self.allowed_values, other.allowed_values),
            max_value=_lowest(self.max_value, other.max_value),
            max_items=_lowest_int(self.max_items, other.max_items),
        )

    def to_record(self) -> dict[str, Any]:
        """Return the JSON-shaped record stored on the node.

        Only what was set. A record of six keys per path, five of them false,
        is a stored document nobody can read in a database console.
        """
        record: dict[str, Any] = {"path": self.path}
        if self.locked:
            record["locked"] = True
        if self.required:
            record["required"] = True
        if self.approval_gated:
            record["approval_gated"] = True
        if self.allowed_values is not None:
            record["allowed_values"] = list(self.allowed_values)
        if self.max_value is not None:
            record["max_value"] = self.max_value
        if self.max_items is not None:
            record["max_items"] = self.max_items
        return record

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> FieldPolicy:
        """Return the policy a stored record describes."""
        allowed = record.get("allowed_values")
        max_value = record.get("max_value")
        max_items = record.get("max_items")
        return cls(
            path=str(record.get("path", "")),
            locked=bool(record.get("locked", False)),
            required=bool(record.get("required", False)),
            approval_gated=bool(record.get("approval_gated", False)),
            allowed_values=tuple(allowed) if isinstance(allowed, Sequence) else None,
            max_value=float(max_value) if isinstance(max_value, int | float) else None,
            max_items=int(max_items) if isinstance(max_items, int) else None,
        )


@dataclass(frozen=True, slots=True)
class PolicySet:
    """Every policy declared at one node, at most one per path."""

    policies: Mapping[str, FieldPolicy] = field(default_factory=dict)

    @classmethod
    def of(cls, policies: Iterable[FieldPolicy]) -> PolicySet:
        """Return a set from ``policies``, merging repeats of the same path.

        Repeats are merged rather than refused because the shorthand in
        ``NodeDocument.of`` produces them: locking and requiring the same field
        is two arguments and one policy.
        """
        merged: dict[str, FieldPolicy] = {}
        for policy in policies:
            existing = merged.get(policy.path)
            merged[policy.path] = policy if existing is None else existing.strengthened_by(policy)
        kept = {path: policy for path, policy in merged.items() if not policy.is_empty}
        if len(kept) > MAX_FIELD_POLICIES:
            raise ValueError(
                f"A node may declare at most {MAX_FIELD_POLICIES} field policies; "
                f"this one declares {len(kept)}."
            )
        return cls(policies=kept)

    @classmethod
    def of_records(cls, records: Iterable[Any]) -> PolicySet:
        """Return the set stored in a node's payload, skipping malformed records."""
        return cls.of(
            FieldPolicy.of_record(record)
            for record in records
            if isinstance(record, Mapping) and record.get("path")
        )

    def to_records(self) -> list[dict[str, Any]]:
        """Return the storable records, ordered by path so a diff is readable."""
        return [self.policies[path].to_record() for path in sorted(self.policies)]

    def for_path(self, path: str) -> FieldPolicy | None:
        """Return the policy declared exactly at ``path``, or ``None``."""
        return self.policies.get(path)

    def governing(self, path: str) -> tuple[FieldPolicy, ...]:
        """Return every policy covering ``path``, outermost first."""
        return tuple(
            self.policies[candidate]
            for candidate in paths.prefixes(path)
            if candidate in self.policies
        )

    def locked_paths(self) -> tuple[str, ...]:
        """Return the paths this node locks, in path order."""
        return self._paths_where("locked")

    def required_paths(self) -> tuple[str, ...]:
        """Return the paths this node requires a value for, in path order."""
        return self._paths_where("required")

    def approval_gated_paths(self) -> tuple[str, ...]:
        """Return the paths whose changes need approval, in path order."""
        return self._paths_where("approval_gated")

    def inherited_by(self, other: PolicySet) -> PolicySet:
        """Return ``other``'s policies with this set's constraints still applied.

        The direction is deliberate: this set is the ancestor's. A descendant
        may add and may tighten; the result never says less than the ancestor
        did.
        """
        combined: dict[str, FieldPolicy] = dict(self.policies)
        for path, policy in other.policies.items():
            existing = combined.get(path)
            combined[path] = policy if existing is None else existing.strengthened_by(policy)
        return PolicySet(policies=combined)

    def without(self, path: str) -> PolicySet:
        """Return this set with the policy at ``path`` removed."""
        return PolicySet(
            policies={known: policy for known, policy in self.policies.items() if known != path}
        )

    def with_policy(self, policy: FieldPolicy) -> PolicySet:
        """Return this set with ``policy`` replacing whatever was at its path."""
        return PolicySet.of([*self.without(policy.path).policies.values(), policy])

    def __bool__(self) -> bool:
        """Return whether this node declares anything at all."""
        return bool(self.policies)

    def __len__(self) -> int:
        """Return how many paths this node declares a policy for."""
        return len(self.policies)

    def _paths_where(self, flag: str) -> tuple[str, ...]:
        return tuple(path for path in sorted(self.policies) if getattr(self.policies[path], flag))


def _narrowest(
    left: tuple[Any, ...] | None, right: tuple[Any, ...] | None
) -> tuple[Any, ...] | None:
    """Return the intersection of two allowed-value sets, order preserved."""
    if left is None:
        return right
    if right is None:
        return left
    return tuple(value for value in left if value in right)


def _lowest(left: float | None, right: float | None) -> float | None:
    """Return the tighter of two ceilings."""
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _lowest_int(left: int | None, right: int | None) -> int | None:
    """Return the tighter of two integer ceilings."""
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def merged_along(chain: Iterable[PolicySet]) -> PolicySet:
    """Return the policies in force at the end of ``chain``, root-first.

    Every ancestor's declaration still applies at the leaf. That is what makes
    a lock declared at the organisation mean something twelve levels down.
    """
    accumulated = PolicySet()
    for policies in chain:
        accumulated = accumulated.inherited_by(policies)
    return accumulated


def relaxed(policy: FieldPolicy, **changes: Any) -> FieldPolicy:
    """Return ``policy`` with ``changes`` applied, bypassing strengthening.

    The one way to weaken a declaration, and it exists because lifting a lock is
    a legitimate operation. It is not reachable from a merge — a caller has to
    ask for it by name, which is what keeps "policies only tighten" true of
    everything else in this module.
    """
    return replace(policy, **changes)


# --- Enforcement -------------------------------------------------------------


def check_locks(
    node_id: str,
    settings: Mapping[str, Any],
    inherited_locks: Mapping[str, str],
    own: PolicySet | None = None,
) -> None:
    """Raise ``FieldLocked`` if ``settings`` overrides anything an ancestor locked.

    ``own`` is the node's own policy set and is exempt: a node that could not
    set the field it locks could not pin a value at all. Everything in
    ``inherited_locks`` came from strictly above it.
    """
    exempt = own.locked_paths() if own is not None else ()
    for path, _ in paths.leaves(settings):
        for candidate in paths.prefixes(path):
            if candidate in exempt:
                break
            locking = inherited_locks.get(candidate)
            if locking is not None:
                raise FieldLocked(path=path, locking_node_id=locking, node_id=node_id)


def check_lock_addition(
    path: str, node_id: str, descendant_settings: Mapping[str, Mapping[str, Any]]
) -> None:
    """Raise ``LockConflict`` if any descendant already overrides ``path`` (FR-009).

    Refused rather than applied. Applying it would change what those
    descendants resolve to, and the operator adding the lock is the one person
    who cannot see that happen.
    """
    overriding = [
        descendant
        for descendant, settings in descendant_settings.items()
        if any(paths.covers(path, known) for known, _ in paths.leaves(settings))
    ]
    if overriding:
        raise LockConflict(path=path, node_id=node_id, overriding=overriding)


def missing_required(values: Mapping[str, Any], policies: PolicySet) -> tuple[str, ...]:
    """Return the required paths ``values`` supplies no usable value for (FR-006).

    ``None`` and the empty string do not count. Clearing a required field is
    the same omission written differently, and a team that resolved to an empty
    system prompt would investigate with no framing at all. Zero and ``False``
    do count: they are values somebody chose.
    """
    absent: list[str] = []
    for path in policies.required_paths():
        value = paths.value_at(values, path)
        if value is None or (isinstance(value, str) and not value.strip()):
            absent.append(path)
    return tuple(absent)


def constraint_errors(values: Mapping[str, Any], policies: PolicySet) -> tuple[FieldError, ...]:
    """Return what ``values`` violates of the allowed-value and ceiling policies."""
    found: list[FieldError] = []
    for path in sorted(policies.policies):
        policy = policies.policies[path]
        value = paths.value_at(values, path)
        if value is None:
            continue
        found.extend(_violations(policy, path, value))
    return tuple(found)


def changed_paths(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every leaf path whose value differs between ``before`` and ``after``.

    Removals and additions are changes. A gated prompt that could be *deleted*
    without approval is a gated prompt in name only.
    """
    old = dict(paths.leaves(before))
    new = dict(paths.leaves(after))
    return tuple(sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path)))


def gated_paths(changed: Sequence[str], policies: PolicySet) -> tuple[str, ...]:
    """Return the changed paths a policy puts behind an approval (FR-007)."""
    gated = policies.approval_gated_paths()
    return tuple(path for path in changed if any(paths.covers(pattern, path) for pattern in gated))


def _violations(policy: FieldPolicy, path: str, value: Any) -> Iterable[FieldError]:
    """Yield what ``value`` violates of ``policy``."""
    if policy.allowed_values is not None and value not in policy.allowed_values:
        allowed = ", ".join(str(each) for each in policy.allowed_values)
        yield FieldError(path=path, message=f"must be one of {allowed}; found {value!r}")

    if policy.max_value is not None:
        if isinstance(value, bool) or not isinstance(value, int | float):
            yield FieldError(
                path=path, message=f"is capped at {policy.max_value} and is not a number"
            )
        elif value > policy.max_value:
            yield FieldError(
                path=path, message=f"must be at most {policy.max_value}; found {value}"
            )

    if policy.max_items is not None:
        if isinstance(value, str) or not isinstance(value, Sized):
            yield FieldError(
                path=path, message=f"is capped at {policy.max_items} entries and is not a list"
            )
        elif len(value) > policy.max_items:
            yield FieldError(
                path=path,
                message=f"must have at most {policy.max_items} entries; found {len(value)}",
            )


__all__ = [
    "FieldPolicy",
    "PolicySet",
    "changed_paths",
    "check_lock_addition",
    "check_locks",
    "constraint_errors",
    "gated_paths",
    "merged_along",
    "missing_required",
    "relaxed",
]
