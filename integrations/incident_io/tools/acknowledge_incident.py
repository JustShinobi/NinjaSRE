"""incident.io: the one change this integration is allowed to make.

A write, and therefore a different kind of object from everything else in this
package. It declares its side-effect level, it requires a human, and it carries
a planner that turns the arguments of one invocation into the steps that undo
it — before the invocation is allowed to happen, because a rollback written
afterwards is written by somebody who already has the problem.

Source of truth: incident.io's ``/v2/incident_updates``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.capability.decorator import tool
from core.capability.metadata import EvidenceType, Requirements, SideEffectLevel
from core.capability.metadata import RollbackPlan as DeclaredRollbackPlan
from core.capability.result import CapabilityResult, Evidence
from integrations._base.access import current
from integrations._base.capability import unconfigured, vendor_failure
from integrations._base.errors import IntegrationError
from integrations.incident_io.client import IncidentIoClient
from integrations.incident_io.schema import INTEGRATION

TOOL_NAME = "incident_io_acknowledge_incident"

_USE_CASES = (
    "an investigation that has started and will report shortly",
    "stopping a second escalation while a first responder is already engaged",
)

_ANTI_EXAMPLES = (
    "an incident nobody is actually working, where the clock should run",
    "closing an incident, which acknowledging deliberately does not do",
)


@dataclass(frozen=True, slots=True)
class IncidentIoAcknowledgeIncidentRollback:
    """Turns one invocation's arguments into the steps that undo it."""

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing the change ``arguments`` describes."""
        target = arguments.get("incident", "the target")
        return DeclaredRollbackPlan(
            summary=(
                f"Reverse the incident.io change made to {target}, and say in the same "
                "place that it was reversed."
            ),
            steps=(
                f"Record what incident.io returned for {target}, including its identifier.",
                "Undo the change in incident.io using that identifier.",
                "Post a short correction where the original change is visible, so nobody "
                "acts on a state that no longer holds.",
            ),
            reversible=True,
        )


@tool(
    name=TOOL_NAME,
    display_name="incident.io acknowledge incident",
    description=(
        "Acknowledge an incident and attach a note saying an automated investigation is under way. It stops the escalation clock, which is a change to who gets woken and therefore needs a human to agree to it."
    ),
    domain="incident",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.INCIDENT,
    # Above read_sensitive, so approval and a rollback plan are not optional —
    # the metadata refuses to be constructed without both.
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "Acknowledging stops the escalation clock, so the next person in the rotation is not paged. That is a decision about who is woken up, and it belongs to a human even though it is reversible."
    ),
    rollback_planner=IncidentIoAcknowledgeIncidentRollback(),
    tags=(
        "incident",
        "incident_io",
        "write",
        "incidents",
        "response",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def incident_io_acknowledge_incident(incident: str, note: str) -> CapabilityResult:
    """Make the change in incident.io and return what it said."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(IncidentIoClient, capability=TOOL_NAME)
    try:
        answer = await client.acknowledge(incident, note)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    return CapabilityResult.ok(
        TOOL_NAME,
        value={"incident": incident, "note": note, "response": answer},
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.INCIDENT,
                summary=f"incident.io accepted the change to {incident!r}",
                reference=f"incident_io:acknowledge_incident:{incident}",
            ),
        ),
    )
