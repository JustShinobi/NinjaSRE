"""The organisation-level constraints that decide what is gated and what is refused.

Two jobs, deliberately in one value.

**What needs approval.** ``require_approval_for`` and
``require_approval_for_side_effect_levels`` are what turn an ordinary write into
a queued change. Granularity is the point: an organisation that gated everything
would teach its reviewers to approve without reading, and approval fatigue is
the way this control fails in practice rather than in theory.

**What is refused outright.** Locked settings, maximum values, required
settings, and allowed value sets are not gated — they are walls. A queued change
that violates one could never be legally approved, so it is refused at the
queue rather than parked in somebody's review list.

**The constraints bind every role.** ``check_settings`` takes settings and
nothing else — no principal, no role, no permission set. That is not an
oversight, it is the requirement: an owner who can quietly exceed a ceiling the
policy sets means the ceiling is documentation. Raising it requires changing the
policy, which is itself audited and may itself be gated.

**A policy change never rewrites the past.** Already-approved changes stay
approved; already-queued changes stay queued and are re-checked against the new
policy when somebody decides them. ``effect_of`` states that explicitly rather
than leaving each surface to guess, because silent reinterpretation of pending
state is worse than asking for a re-review.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence, Sized
from dataclasses import dataclass, field
from typing import Any, Final

from config.constants.security import (
    ALLOW_SELF_APPROVAL_BY_DEFAULT,
    API_TOKEN_DEFAULT_LIFETIME_DAYS,
    PENDING_CHANGE_EXPIRY_HOURS,
    PENDING_CHANGE_MAX_EXPIRY_HOURS,
    SIDE_EFFECT_LEVELS,
    TOKEN_EXPIRY_WARNING_DAYS,
    TOKEN_INACTIVITY_REVOCATION_DAYS,
)
from platform.approvals.errors import PolicyLocked, PolicyViolation
from platform.approvals.models import ChangeType
from platform.config_service import paths


@dataclass(frozen=True, slots=True)
class TokenLifecycleDefaults:
    """What the organisation's policy says a token's life looks like.

    Read by the identity layer when a token is issued and when the inactivity
    sweep runs. Held here rather than there because it is a security decision an
    organisation makes once, and the place an operator changes it is the same
    screen they set every other constraint on.
    """

    expiry_days: int = API_TOKEN_DEFAULT_LIFETIME_DAYS
    warn_before_days: int = TOKEN_EXPIRY_WARNING_DAYS
    revoke_inactive_days: int = TOKEN_INACTIVITY_REVOCATION_DAYS

    def __post_init__(self) -> None:
        if self.warn_before_days >= self.expiry_days:
            raise ValueError(
                f"A warning {self.warn_before_days} days before a {self.expiry_days}-day "
                f"expiry arrives before the token exists. Warn sooner than the token lasts."
            )


@dataclass(frozen=True, slots=True)
class PolicyChangeEffect:
    """What changing the policy does, and — as much — what it does not.

    ``applied_automatically`` and ``discarded_automatically`` are always empty,
    and they are on this value precisely because they are. A caller rendering
    this to an operator can say "no queued change was applied or discarded" from
    the value itself, rather than from a paragraph in a document the operator
    has not read.
    """

    newly_gated: tuple[ChangeType, ...] = ()
    no_longer_gated: tuple[ChangeType, ...] = ()
    tightened_settings: tuple[str, ...] = ()
    relaxed_settings: tuple[str, ...] = ()
    applied_automatically: tuple[str, ...] = ()
    discarded_automatically: tuple[str, ...] = ()

    @property
    def is_noop(self) -> bool:
        """Return whether the policy change alters nothing about the queue."""
        return not (
            self.newly_gated
            or self.no_longer_gated
            or self.tightened_settings
            or self.relaxed_settings
        )

    def describe(self) -> str:
        """Return the sentence an operator is shown before they confirm."""
        if self.is_noop:
            return "This policy change affects nothing that is already queued."
        parts: list[str] = []
        if self.newly_gated:
            listed = ", ".join(sorted(kind.value for kind in self.newly_gated))
            parts.append(f"{listed} changes will need approval from now on")
        if self.no_longer_gated:
            listed = ", ".join(sorted(kind.value for kind in self.no_longer_gated))
            parts.append(f"{listed} changes will no longer be queued")
        if self.tightened_settings:
            parts.append(f"tighter limits on {', '.join(sorted(self.tightened_settings))}")
        if self.relaxed_settings:
            parts.append(f"looser limits on {', '.join(sorted(self.relaxed_settings))}")
        # Only the leading character is raised. ``str.capitalize`` would lower
        # the rest, and the rest holds names — a capability called ``PagerDuty``
        # must survive being the first thing in the sentence.
        sentence = "; ".join(parts)
        return (
            f"{sentence[:1].upper()}{sentence[1:]}. Changes already approved keep their "
            f"effect, and changes already queued stay queued — each is re-checked against "
            f"this policy when somebody decides it."
        )


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    """One organisation's security constraints, as a value.

    Everything defaults to the least surprising setting rather than the
    strictest one, with a single exception: ``allow_self_approval`` defaults to
    forbidden. A deployment with two people is where the control matters, and a
    single-operator deployment turns it off on purpose rather than by accident.
    """

    require_approval_for: frozenset[ChangeType] = field(default_factory=frozenset)
    require_approval_for_side_effect_levels: tuple[str, ...] = ()
    allow_self_approval: bool = ALLOW_SELF_APPROVAL_BY_DEFAULT
    locked_settings: tuple[str, ...] = ()
    max_values: Mapping[str, float] = field(default_factory=dict)
    required_settings: tuple[str, ...] = ()
    allowed_values: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    tokens: TokenLifecycleDefaults = field(default_factory=TokenLifecycleDefaults)
    change_expiry_hours: float = PENDING_CHANGE_EXPIRY_HOURS
    log_all_changes: bool = True

    def __post_init__(self) -> None:
        if not 0 < self.change_expiry_hours <= PENDING_CHANGE_MAX_EXPIRY_HOURS:
            raise ValueError(
                f"A queued change may wait between nothing and "
                f"{PENDING_CHANGE_MAX_EXPIRY_HOURS} hours; this policy says "
                f"{self.change_expiry_hours}. A change nobody answered in a month is one "
                f"whose reviewer has forgotten what the system looked like."
            )
        unknown = set(self.require_approval_for_side_effect_levels) - set(SIDE_EFFECT_LEVELS)
        if unknown:
            listed = ", ".join(sorted(unknown))
            raise ValueError(
                f"No side-effect level named {listed}. This deployment has: "
                f"{', '.join(SIDE_EFFECT_LEVELS)}."
            )

    # --- What needs approval -------------------------------------------------

    def requires_approval(self, change_type: ChangeType) -> bool:
        """Return whether ``change_type`` must be queued rather than applied."""
        return change_type in self.require_approval_for

    def requires_approval_for_level(self, side_effect_level: str) -> bool:
        """Return whether an action at ``side_effect_level`` must be approved.

        Feature 017's entry point into this policy. Levels are compared by name
        rather than by rank, because a policy that gated "everything above
        ``write_reversible``" would silently start gating a level added later,
        and a control that changes what it covers when somebody adds an enum
        member is not one an operator agreed to.
        """
        return side_effect_level in self.require_approval_for_side_effect_levels

    def permits_self_approval(self) -> bool:
        """Return whether the requester may also be the approver."""
        return self.allow_self_approval

    def token_defaults(self) -> TokenLifecycleDefaults:
        """Return the token lifecycle the identity layer should apply."""
        return self.tokens

    # --- What is refused outright --------------------------------------------

    def check_settings(self, settings: Mapping[str, Any]) -> None:
        """Raise unless ``settings`` satisfies every constraint.

        Takes settings and nothing else. There is no principal on this signature
        and there must not be one: a constraint that consulted the caller's role
        would have an exemption, and the exemption would be for exactly the
        person the constraint exists to bind.

        Locks are raised on their own rather than collected, because a locked
        path is somebody else's decision to argue with and the other violations
        are the operator's own document to fix.
        """
        self._check_locks(settings)
        violations = (
            *self._missing_required(settings),
            *self._exceeded_maximums(settings),
            *self._disallowed_values(settings),
        )
        if violations:
            raise PolicyViolation(violations)

    def _check_locks(self, settings: Mapping[str, Any]) -> None:
        """Raise ``PolicyLocked`` for the first path this policy pins."""
        for path, _ in paths.leaves(settings):
            for candidate in paths.prefixes(path):
                if candidate in self.locked_settings:
                    raise PolicyLocked(path)

    def _missing_required(self, settings: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the required paths ``settings`` supplies no usable value for.

        ``None`` and whitespace do not count. Clearing a required field is the
        same omission written differently. Zero and ``False`` do count: they are
        values somebody chose.
        """
        absent: list[str] = []
        for path in self.required_settings:
            if not _mentions(settings, path):
                continue
            value = paths.value_at(settings, path)
            if value is None or (isinstance(value, str) and not value.strip()):
                absent.append(f"{path} is required by this organisation and cannot be cleared")
        return tuple(absent)

    def _exceeded_maximums(self, settings: Mapping[str, Any]) -> tuple[str, ...]:
        """Return every ceiling ``settings`` crosses."""
        exceeded: list[str] = []
        for path, ceiling in sorted(self.max_values.items()):
            value = paths.value_at(settings, path)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                exceeded.append(f"{path} is capped at {ceiling} and is not a number")
            elif value > ceiling:
                exceeded.append(f"{path} must be at most {ceiling}; this asks for {value}")
        return tuple(exceeded)

    def _disallowed_values(self, settings: Mapping[str, Any]) -> tuple[str, ...]:
        """Return every closed set ``settings`` steps outside of."""
        refused: list[str] = []
        for path, allowed in sorted(self.allowed_values.items()):
            value = paths.value_at(settings, path)
            if value is None or value in allowed:
                continue
            listed = ", ".join(str(each) for each in allowed)
            refused.append(f"{path} must be one of {listed}")
        return tuple(refused)

    # --- Changing the policy -------------------------------------------------

    def effect_of(self, replacement: SecurityPolicy) -> PolicyChangeEffect:
        """Return what moving from this policy to ``replacement`` would do.

        Computed rather than asserted, and computed *before* the change is
        stored, so the operator confirming it is confirming something they were
        shown. The two "automatically" fields stay empty by construction: a
        policy change is not a decision on anybody's queued work.
        """
        return PolicyChangeEffect(
            newly_gated=_ordered(replacement.require_approval_for - self.require_approval_for),
            no_longer_gated=_ordered(self.require_approval_for - replacement.require_approval_for),
            tightened_settings=_tightened(self, replacement),
            relaxed_settings=_tightened(replacement, self),
        )

    # --- Storage -------------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Return the stored form of this policy, for the audit trail and the API."""
        return {
            "require_approval_for": sorted(kind.value for kind in self.require_approval_for),
            "require_approval_for_side_effect_levels": list(
                self.require_approval_for_side_effect_levels
            ),
            "allow_self_approval": self.allow_self_approval,
            "locked_settings": list(self.locked_settings),
            "max_values": dict(sorted(self.max_values.items())),
            "required_settings": list(self.required_settings),
            "allowed_values": {
                path: list(values) for path, values in sorted(self.allowed_values.items())
            },
            "token_expiry_days": self.tokens.expiry_days,
            "token_warn_before_days": self.tokens.warn_before_days,
            "token_revoke_inactive_days": self.tokens.revoke_inactive_days,
            "change_expiry_hours": self.change_expiry_hours,
            "log_all_changes": self.log_all_changes,
        }

    @classmethod
    def of_record(cls, record: Mapping[str, Any]) -> SecurityPolicy:
        """Return the policy a stored record describes."""
        return cls(
            require_approval_for=frozenset(
                ChangeType(str(name)) for name in _sequence(record.get("require_approval_for"))
            ),
            require_approval_for_side_effect_levels=tuple(
                str(level)
                for level in _sequence(record.get("require_approval_for_side_effect_levels"))
            ),
            allow_self_approval=bool(
                record.get("allow_self_approval", ALLOW_SELF_APPROVAL_BY_DEFAULT)
            ),
            locked_settings=tuple(str(path) for path in _sequence(record.get("locked_settings"))),
            max_values={
                str(path): float(value)
                for path, value in _mapping(record.get("max_values")).items()
                if isinstance(value, int | float)
            },
            required_settings=tuple(
                str(path) for path in _sequence(record.get("required_settings"))
            ),
            allowed_values={
                str(path): tuple(_sequence(values))
                for path, values in _mapping(record.get("allowed_values")).items()
            },
            tokens=TokenLifecycleDefaults(
                expiry_days=int(
                    record.get("token_expiry_days", API_TOKEN_DEFAULT_LIFETIME_DAYS) or 0
                ),
                warn_before_days=int(
                    record.get("token_warn_before_days", TOKEN_EXPIRY_WARNING_DAYS) or 0
                ),
                revoke_inactive_days=int(
                    record.get("token_revoke_inactive_days", TOKEN_INACTIVITY_REVOCATION_DAYS) or 0
                ),
            ),
            change_expiry_hours=float(
                record.get("change_expiry_hours", PENDING_CHANGE_EXPIRY_HOURS)
            ),
            log_all_changes=bool(record.get("log_all_changes", True)),
        )


#: What a deployment gets before anybody configures anything: nothing gated, no
#: ceilings, and self-approval forbidden. Gating by default would mean a fresh
#: deployment's first configuration change sat in a queue with no reviewer.
DEFAULT_POLICY: Final[SecurityPolicy] = SecurityPolicy()


def _mentions(settings: Mapping[str, Any], path: str) -> bool:
    """Return whether ``settings`` speaks about ``path`` at all.

    A patch that does not mention a required field is not clearing it; it is
    leaving it alone, and refusing that would make every partial write carry
    every required value.
    """
    return any(known == path or paths.covers(path, known) for known, _ in paths.leaves(settings))


def _ordered(kinds: Iterable[ChangeType]) -> tuple[ChangeType, ...]:
    """Return ``kinds`` in a stable order, so two effects compare equal."""
    return tuple(sorted(kinds, key=lambda kind: kind.value))


def _tightened(before: SecurityPolicy, after: SecurityPolicy) -> tuple[str, ...]:
    """Return the paths ``after`` constrains more tightly than ``before`` does."""
    changed: set[str] = set(after.locked_settings) - set(before.locked_settings)
    changed |= set(after.required_settings) - set(before.required_settings)
    for path, ceiling in after.max_values.items():
        previous = before.max_values.get(path)
        if previous is None or ceiling < previous:
            changed.add(path)
    for path, allowed in after.allowed_values.items():
        previous_allowed = before.allowed_values.get(path)
        if previous_allowed is None or set(allowed) < set(previous_allowed):
            changed.add(path)
    return tuple(sorted(changed))


def _sequence(value: Any) -> tuple[Any, ...]:
    """Return ``value`` as a tuple, or an empty one if it is not a sequence."""
    if isinstance(value, str) or not isinstance(value, Sequence | Sized):
        return ()
    return tuple(value) if isinstance(value, Sequence) else ()


def _mapping(value: Any) -> dict[str, Any]:
    """Return ``value`` as a plain dict, or an empty one if it is not a mapping."""
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "DEFAULT_POLICY",
    "PolicyChangeEffect",
    "SecurityPolicy",
    "TokenLifecycleDefaults",
]
