"""One action that stops every automated write, above everything else.

The control this exists to provide is not "disable autonomy". It is "stop, now,
without me having to work out what is currently permitted". During a bad
incident an operator has neither the time nor the confidence to unwind
allow-lists entry by entry and cancel pending approvals one at a time, and an
emergency stop that requires an inventory first is not one.

So this sits above every other check, and it overrides an approval that has
already been granted. An action approved thirty seconds ago is exactly the kind
this has to catch: the human who approved it did so before whatever made the
operator reach for the switch.

**State is read at the moment of the check and never cached.** A cached kill
switch is a kill switch that does not stop the next write, and the window is
measured in exactly the seconds that matter. That is why this is a small
in-process value with no store behind it: the deployment holds one, every gate
reads it directly, and there is no replication delay between engaging it and it
taking effect.

**Scopes nest and the wider one wins.** A switch engaged for the organisation
stops a team's writes whether or not that team has one of its own, because an
org-wide stop that a team could be outside of is not an org-wide stop.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from platform.observability.logging import get_logger
from platform.remediation.errors import KillSwitchEngaged
from platform.remediation.models import utc_now

_LOG = get_logger(__name__)

#: The scope key an organisation-wide switch is held under. Not an org
#: identifier, because one ``KillSwitch`` belongs to one deployment tenant
#: already and a second spelling of "everything" is a switch somebody engages
#: and another code path does not see.
ORGANISATION_SCOPE: Final = "*"


@dataclass(frozen=True, slots=True)
class KillSwitchState:
    """One engaged switch: what it covers, who engaged it, and why."""

    scope: str
    engaged_by: str
    engaged_at: datetime
    reason: str = ""

    def describe(self) -> str:
        """Return the sentence a surface shows while this is on."""
        where = "this organisation" if self.scope == ORGANISATION_SCOPE else self.scope
        why = f" — {self.reason}" if self.reason else ""
        return (
            f"Automated writes are stopped for {where}, engaged by {self.engaged_by} at "
            f"{self.engaged_at.isoformat()}{why}"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form, for the audit trail and a health report."""
        return {
            "scope": self.scope,
            "engaged_by": self.engaged_by,
            "engaged_at": self.engaged_at.isoformat(),
            "reason": self.reason,
        }


@dataclass(slots=True)
class KillSwitch:
    """Team- and org-scoped immediate refusal of every write.

    Deliberately not a policy setting. A policy change goes through the approval
    mechanism, which needs a reviewer, which is the thing an operator does not
    have during the ten seconds in which this matters.
    """

    engaged: dict[str, KillSwitchState] = field(default_factory=dict)

    def engage(
        self,
        *,
        engaged_by: str,
        scope: str = ORGANISATION_SCOPE,
        reason: str = "",
        at: datetime | None = None,
    ) -> KillSwitchState:
        """Engage the switch for ``scope`` and return the state it is now in.

        Idempotent in effect and not in record: re-engaging replaces the state,
        so the reason and the principal are the most recent ones. An operator
        engaging a switch that is already on is usually correcting the reason,
        and keeping the first would leave the audit trail explaining the wrong
        incident.
        """
        state = KillSwitchState(
            scope=scope,
            engaged_by=engaged_by,
            engaged_at=at if at is not None else utc_now(),
            reason=reason,
        )
        self.engaged[scope] = state
        _LOG.warning(
            "remediation.kill_switch_engaged",
            scope=scope,
            engaged_by=engaged_by,
            reason=reason,
        )
        return state

    def release(self, *, released_by: str, scope: str = ORGANISATION_SCOPE) -> bool:
        """Release ``scope``'s switch and return whether one was engaged.

        Releasing an organisation switch does not release a team's. Each was
        engaged by somebody for a reason, and a release that quietly cleared
        scopes it was not asked about would be the failure mode of this control
        rather than a convenience.
        """
        previous = self.engaged.pop(scope, None)
        if previous is None:
            return False
        _LOG.warning("remediation.kill_switch_released", scope=scope, released_by=released_by)
        return True

    def state_for(self, *, team_node_id: str | None = None) -> KillSwitchState | None:
        """Return the switch stopping this team's writes, or ``None``.

        The organisation's switch is checked first, so a team asking "am I
        stopped" gets the widest reason rather than discovering the narrow one
        and concluding the rest of the estate is running.
        """
        organisation = self.engaged.get(ORGANISATION_SCOPE)
        if organisation is not None:
            return organisation
        if team_node_id is None:
            return None
        return self.engaged.get(team_node_id)

    def is_engaged(self, *, team_node_id: str | None = None) -> bool:
        """Return whether any switch currently stops this team's writes."""
        return self.state_for(team_node_id=team_node_id) is not None

    def describe_for(self, *, team_node_id: str | None = None) -> str:
        """Return why this team's writes are stopped, empty when they are not.

        The non-raising companion to ``check``. The policy engine evaluates this
        alongside three other bounds and reports which one refused, so it needs
        the sentence rather than an exception — and it depends on this switch by
        shape rather than by import, which is what keeps that dependency
        pointing the way the tier table says it must.
        """
        state = self.state_for(team_node_id=team_node_id)
        return state.describe() if state is not None else ""

    def check(self, *, team_node_id: str | None = None) -> None:
        """Raise ``KillSwitchEngaged`` if any switch stops this team's writes.

        The raising form exists because the gate has to refuse rather than
        decide, and a boolean at that call site would be one ``if`` away from a
        write that ran while the switch was on.
        """
        state = self.state_for(team_node_id=team_node_id)
        if state is None:
            return
        raise KillSwitchEngaged(
            state.scope,
            engaged_by=state.engaged_by,
            reason=state.reason,
        )

    def report(self) -> Mapping[str, Any]:
        """Return every engaged scope, for a health endpoint and the console."""
        return {scope: state.to_record() for scope, state in sorted(self.engaged.items())}


__all__ = [
    "ORGANISATION_SCOPE",
    "KillSwitch",
    "KillSwitchState",
]
