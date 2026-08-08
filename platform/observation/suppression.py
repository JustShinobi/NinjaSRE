"""Deciding not to raise something, and writing down that you decided.

The one rule this module exists to enforce is that **suppression is never
silent**. An operator asking "why did nothing happen last night" must get an
answer, and a suppression rule that is too broad has to be countable — otherwise
it is a rule that quietly stops the deployment watching and nobody finds out
until the thing it covered actually breaks.

So nothing here *drops* a finding. It returns a ``Suppression`` naming the rule,
the reason, and what it covered, and the incident lifecycle records that as an
incident in the suppressed state. The finding is in the incident list, marked,
countable, and searchable.

Three sources of suppression, in the order they are checked.

**The global pause** stops everything without unconfiguring anything. It exists
because the alternative — an operator deleting their detectors before a
migration and remembering to put them back — is a deployment that stops watching
permanently one time in five.

**A maintenance window on the resource**, which the estate already holds. A
machine somebody deliberately took down is not an incident, and the estate is
where that fact lives; re-declaring it here would give a deployment two places
to look and two answers.

**A scoped rule**, by resource, kind, detector, team, and time. Scoped rather
than global because "silence this detector" and "silence this rack" are
different requests and a deployment that only offered one would get the other
by having somebody disable a detector for everybody.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from platform.observation.detectors.model import DetectorDeclaration
from platform.persistence.ports.estate_repository import Resource

#: What a suppression names when the global pause is what covered it.
GLOBAL_PAUSE_RULE = "global-pause"

#: And when the estate's own maintenance window did.
MAINTENANCE_RULE = "maintenance-window"


@dataclass(frozen=True, slots=True)
class Suppression:
    """One finding that was not raised, and exactly why.

    Carries the rule as well as the reason. "Suppressed by maintenance" is a
    sentence; "suppressed by rack-4-migration until Tuesday" is one somebody can
    act on, and telling an operator which of their rules did it is the whole
    difference between a suppression they can review and one they cannot find.
    """

    detector_id: str
    resource_id: str
    rule_id: str
    reason: str
    at: datetime

    @property
    def summary(self) -> str:
        """Return the sentence the suppressed incident carries."""
        return (
            f"{self.detector_id} fired on {self.resource_id} and was suppressed by "
            f"{self.rule_id}: {self.reason}"
        )


@dataclass(frozen=True, slots=True)
class SuppressionRule:
    """One operator's declaration that something should not raise for a while.

    Every dimension is a filter and an empty one means "no filter on this",
    which is the reading that composes: a rule with only ``team_node_id`` set
    silences a team, and one with only ``detector_ids`` set silences a detector
    everywhere. A rule with *nothing* set would silence the deployment, so
    ``covers`` refuses one — the global pause is a separate, visible switch and
    an empty rule must not be a hidden second one.
    """

    rule_id: str
    reason: str
    resource_ids: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    detector_ids: tuple[str, ...] = ()
    team_node_id: str = ""
    #: Absolute instants, both optional. Comparison is between instants rather
    #: than between wall-clock readings, which is what makes a window spanning a
    #: daylight-saving change last exactly as long as it was declared to.
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @property
    def is_scoped(self) -> bool:
        """Return whether this rule narrows anything at all."""
        return bool(self.resource_ids or self.kinds or self.detector_ids or self.team_node_id)

    def is_active_at(self, at: datetime) -> bool:
        """Return whether this rule's window covers ``at``."""
        if self.starts_at is not None and at < self.starts_at:
            return False
        return not (self.ends_at is not None and at >= self.ends_at)

    def covers(
        self,
        *,
        detector: DetectorDeclaration,
        resource: Resource | None,
        resource_id: str,
        at: datetime,
    ) -> bool:
        """Return whether this rule silences ``detector`` on this resource at ``at``.

        An unscoped rule covers nothing. A rule that silenced everything by
        having no filters would be a global pause an operator could create by
        accident and could not see, and the visible one exists for exactly this.
        """
        if not self.is_scoped or not self.is_active_at(at):
            return False
        if self.detector_ids and detector.detector_id not in self.detector_ids:
            return False
        if self.resource_ids and resource_id not in self.resource_ids:
            return False
        if self.kinds and (resource is None or resource.kind not in self.kinds):
            return False
        if self.team_node_id:
            team = resource.team_node_id if resource is not None else None
            return (team or detector.team_node_id) == self.team_node_id
        return True


@dataclass(frozen=True, slots=True)
class Suppressor:
    """Everything that could stop a finding being raised, in one decision."""

    rules: tuple[SuppressionRule, ...] = ()
    #: The global stop. Nothing is unconfigured by it and its reason travels
    #: onto every suppression it causes, so a deployment that is deliberately
    #: quiet says so wherever anybody looks.
    paused: bool = False
    pause_reason: str = ""
    #: The estate, by resource id, for the maintenance windows it already holds.
    estate: dict[str, Resource] = field(default_factory=dict)

    def verdict(
        self,
        *,
        detector: DetectorDeclaration,
        resource_id: str,
        at: datetime,
    ) -> Suppression | None:
        """Return why this finding is suppressed, or ``None`` if it is not.

        Checked in order of how broad each one is, so the reason an operator is
        told is the broadest true one. Being told "a rack rule covered this"
        when the whole deployment is paused would send somebody to edit a rule
        that is not what stopped anything.
        """
        if self.paused:
            return Suppression(
                detector_id=detector.detector_id,
                resource_id=resource_id,
                rule_id=GLOBAL_PAUSE_RULE,
                reason=self.pause_reason or "detection is paused for the whole deployment",
                at=at,
            )

        resource = self.estate.get(resource_id)
        if resource is not None and resource.in_maintenance_at(at):
            return Suppression(
                detector_id=detector.detector_id,
                resource_id=resource_id,
                rule_id=MAINTENANCE_RULE,
                reason=(
                    resource.maintenance_reason
                    or f"{resource_id} is in a maintenance window until "
                    f"{resource.maintenance_until.isoformat() if resource.maintenance_until else ''}"
                ),
                at=at,
            )

        for rule in self.rules:
            if rule.covers(detector=detector, resource=resource, resource_id=resource_id, at=at):
                return Suppression(
                    detector_id=detector.detector_id,
                    resource_id=resource_id,
                    rule_id=rule.rule_id,
                    reason=rule.reason,
                    at=at,
                )
        return None


__all__ = [
    "GLOBAL_PAUSE_RULE",
    "MAINTENANCE_RULE",
    "Suppression",
    "SuppressionRule",
    "Suppressor",
]
