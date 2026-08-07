"""Slack: the one change this integration is allowed to make.

A write, and therefore a different kind of object from everything else in this
package. It declares its side-effect level, it requires a human, and it carries
a planner that turns the arguments of one invocation into the steps that undo
it — before the invocation is allowed to happen, because a rollback written
afterwards is written by somebody who already has the problem.

Source of truth: Slack's ``/api/chat.postMessage``.
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
from integrations.slack.client import SlackClient
from integrations.slack.schema import INTEGRATION

TOOL_NAME = "slack_post_message"

_USE_CASES = (
    "delivering a finding into the channel an incident is being run from",
    "telling responders that an automated investigation has concluded",
)

_ANTI_EXAMPLES = (
    "paging somebody, which is an escalation rather than a message",
    "anything an investigation has not finished establishing",
)


@dataclass(frozen=True, slots=True)
class SlackPostMessageRollback:
    """Turns one invocation's arguments into the steps that undo it."""

    def plan(self, arguments: Mapping[str, Any]) -> DeclaredRollbackPlan:
        """Return the plan reversing the change ``arguments`` describes."""
        target = arguments.get("channel", "the target")
        return DeclaredRollbackPlan(
            summary=(
                f"Reverse the Slack change made to {target}, and say in the same "
                "place that it was reversed."
            ),
            steps=(
                f"Record what Slack returned for {target}, including its identifier.",
                "Undo the change in Slack using that identifier.",
                "Post a short correction where the original change is visible, so nobody "
                "acts on a state that no longer holds.",
            ),
            reversible=True,
        )


@tool(
    name=TOOL_NAME,
    display_name="Slack post message",
    description=(
        "Post a message to a channel. Used to deliver a finding where the incident is already being discussed, rather than in a place somebody has to go and look."
    ),
    domain="communication",
    evidence_source=INTEGRATION,
    evidence_type=EvidenceType.DOCUMENT,
    # Above read_sensitive, so approval and a rollback plan are not optional —
    # the metadata refuses to be constructed without both.
    side_effect_level=SideEffectLevel.WRITE_REVERSIBLE,
    parallel_safe=False,
    requires=Requirements(integrations=(INTEGRATION,)),
    requires_approval=True,
    approval_reason=(
        "A message to a channel is visible to everyone in it and cannot be unsaid, only followed by a correction. A human decides whether a finding is ready to be read by the people responding."
    ),
    rollback_planner=SlackPostMessageRollback(),
    tags=(
        "communication",
        "slack",
        "write",
        "chat",
        "incident-channel",
    ),
    use_cases=_USE_CASES,
    anti_examples=_ANTI_EXAMPLES,
)
async def slack_post_message(channel: str, text: str) -> CapabilityResult:
    """Make the change in Slack and return what it said."""
    access = current()
    if access is None:
        return unconfigured(TOOL_NAME, INTEGRATION)

    client = access.client(SlackClient, capability=TOOL_NAME)
    try:
        answer = await client.post_message(channel, text)
    except IntegrationError as error:
        return vendor_failure(TOOL_NAME, error)

    return CapabilityResult.ok(
        TOOL_NAME,
        value={"channel": channel, "text": text, "response": answer},
        evidence=(
            Evidence(
                source=INTEGRATION,
                evidence_type=EvidenceType.DOCUMENT,
                summary=f"Slack accepted the change to {channel!r}",
                reference=f"slack:post_message:{channel}",
            ),
        ),
    )
