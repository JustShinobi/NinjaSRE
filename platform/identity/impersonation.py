"""An admin acting in a team's context, for a while, with both names on record.

Support work needs it. An admin who cannot see what the payments team sees
cannot reproduce what the payments team reported, and the alternative operators
actually reach for — asking somebody to share a session — is worse in every way.

Three things bound the risk, and all three are here rather than in a policy
document:

**It ends by itself.** An impersonation carries an expiry and is refused after
it, so a forgotten context switch is not a standing privilege.

**It requires a reason.** Recorded, at least a sentence, and shown in the audit
trail beside the actions it covers. "Erin acted as payments" is not reviewable;
"Erin acted as payments to reproduce the report they filed" is.

**Both principals are recorded, always.** Not by convention — by
``AuditContext`` refusing to build a record that carries one without the other
(see ``audit.recorder``). The security suite asserts it across every audited
action type, because a dual-principal trail with one gap is a trail an admin can
act through.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config.constants.security import (
    IMPERSONATION_AUDIT_ACTION_END,
    IMPERSONATION_AUDIT_ACTION_START,
    IMPERSONATION_MAX_DURATION_SECONDS,
)
from platform.identity.authorisation import PermissionSet
from platform.identity.errors import ImpersonationRejected
from platform.identity.models import Principal
from platform.identity.permissions import Permission

#: The ceiling, as a duration. A caller may ask for less and never for more.
MAX_IMPERSONATION = timedelta(seconds=IMPERSONATION_MAX_DURATION_SECONDS)


def _utc_now() -> datetime:
    """Return the current instant in UTC."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Impersonation:
    """One admin's time-limited context switch into a team.

    ``subject_principal_id`` is optional because the common case is acting as a
    *team* rather than as a named person — an admin reproducing a team-wide
    configuration problem is not pretending to be anybody in particular, and
    recording a person they did not choose would make the audit trail say
    something untrue.
    """

    real_principal_id: str
    node_id: str | None
    started_at: datetime
    expires_at: datetime
    reason: str
    subject_principal_id: str | None = None

    def __post_init__(self) -> None:
        if self.expires_at <= self.started_at:
            raise ImpersonationRejected(
                "it would expire before it began", expires_at=self.expires_at
            )
        if self.expires_at - self.started_at > MAX_IMPERSONATION:
            raise ImpersonationRejected(
                f"impersonation may last at most {MAX_IMPERSONATION}",
                expires_at=self.expires_at,
            )
        if not self.reason.strip():
            raise ImpersonationRejected("an impersonation has to say why")

    def is_live(self, now: datetime) -> bool:
        """Return whether this impersonation may still be used."""
        return self.started_at <= now < self.expires_at

    def require_live(self, now: datetime) -> None:
        """Raise ``ImpersonationRejected`` unless this impersonation is still live."""
        if not self.is_live(now):
            raise ImpersonationRejected("it has expired", expires_at=self.expires_at)

    def remaining(self, now: datetime) -> timedelta:
        """Return how long is left, never negative."""
        return max(self.expires_at - now, timedelta())


def begin(
    admin: Principal,
    permissions: PermissionSet,
    *,
    node_id: str | None,
    reason: str,
    subject_principal_id: str | None = None,
    duration: timedelta = MAX_IMPERSONATION,
    clock: Callable[[], datetime] = _utc_now,
) -> Impersonation:
    """Return a live impersonation, or raise saying why the admin may not have one.

    The permission is checked at the node being impersonated rather than
    organisation-wide, so an admin scoped to one division cannot support a team
    in another. That is the same rule every other permission follows, which is
    the point of having one rule.
    """
    permissions.require(Permission.IMPERSONATION_USE, node_id=node_id)
    if duration > MAX_IMPERSONATION:
        raise ImpersonationRejected(f"impersonation may last at most {MAX_IMPERSONATION}")

    started_at = clock()
    return Impersonation(
        real_principal_id=admin.principal_id,
        node_id=node_id,
        started_at=started_at,
        expires_at=started_at + duration,
        reason=reason,
        subject_principal_id=subject_principal_id,
    )


#: What the start and the end of an impersonation are called in the audit trail.
#: Separate from the actions performed *during* one: a reviewer asking
#: "when did Erin have this access" should not have to infer it from the first
#: and last thing they did with it.
START_ACTION = IMPERSONATION_AUDIT_ACTION_START
END_ACTION = IMPERSONATION_AUDIT_ACTION_END


__all__ = [
    "END_ACTION",
    "MAX_IMPERSONATION",
    "START_ACTION",
    "Impersonation",
    "begin",
]
