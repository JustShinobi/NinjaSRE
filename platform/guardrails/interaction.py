"""The guardrail engine, as the runtime's filter for text a human supplied.

Two paths bring human prose into an investigation's context: an answer to a
question the agent asked, and guidance somebody queued mid-run. Both are typed
by a person under time pressure during an incident, which is precisely when
somebody pastes a stack trace with a connection string in it, or a curl command
with a bearer token, into a chat thread — and both end up in the transcript, the
run trace, and the episode written from it.

Tool arguments and tool results already go through the engine at their two
hooks. Human input arrives through neither, so this is the third boundary, and
it is the same engine and the same ruleset rather than a second set of rules
that would drift from the first.

**A block redacts rather than refuses.** The other boundaries can decline: a
blocked tool call simply does not run. Declining a human's answer is different —
the person has already typed it, the run is suspended waiting on it, and
throwing it away means the investigation stalls on a question that *was*
answered. So a blocking rule here redacts the span and lets the rest through,
and the fact that it blocked is recorded on the answer so a reviewer can see the
run reasoned from something that had a secret cut out of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.agent.interaction.models import ContentFilter, ScreenedText
from platform.guardrails.audit import GuardrailAuditor, log_fields
from platform.guardrails.engine import GuardrailEngine
from platform.observability.logging import get_logger

logger = get_logger(__name__)

#: Where a scan of human-supplied text is recorded as having happened. Distinct
#: from the two tool-call locations so an audit can answer "did a person paste a
#: secret at us" without it being mixed in with what the tools returned.
HUMAN_INPUT_LOCATION = "human_input"


@dataclass(slots=True)
class GuardrailContentFilter:
    """Screens human-supplied text through the live ruleset.

    Satisfies ``core.agent.interaction.ContentFilter`` structurally, which is
    what lets the runtime hold a port and a deployment hold this without the
    runtime importing a ruleset loader.
    """

    engine: GuardrailEngine
    auditor: GuardrailAuditor | None = None
    org_id: str = ""
    team_id: str = ""

    def screen(self, text: str) -> ScreenedText:
        """Return ``text`` as the agent may see it, and which rules altered it."""
        if not text:
            return ScreenedText(text=text)

        scan = self.engine.scan(text)
        if scan.clean:
            return ScreenedText(text=text)

        rules = tuple(dict.fromkeys(match.rule for match in scan.matches))
        logger.info(
            "guardrails.matched",
            capability=HUMAN_INPUT_LOCATION,
            **log_fields(scan, location=HUMAN_INPUT_LOCATION),
        )
        return ScreenedText(text=scan.text, rules=rules, blocked=scan.blocked)

    async def screen_and_audit(self, text: str) -> ScreenedText:
        """Screen ``text`` and write the scan to the audit trail.

        Separate from ``screen`` because the port is synchronous and auditing is
        not. A caller on an async path — the handoff desk closing an answer —
        gets the audit line; one on a synchronous path still gets the redaction,
        which is the half that must never be optional.
        """
        screened = self.screen(text)
        if not screened.altered or self.auditor is None or not self.org_id:
            return screened

        await self.auditor.record_scan(
            self.engine.scan(text),
            org_id=self.org_id,
            team_id=self.team_id,
            location=HUMAN_INPUT_LOCATION,
        )
        return screened


def content_filter(
    engine: GuardrailEngine,
    *,
    auditor: GuardrailAuditor | None = None,
    org_id: str = "",
    team_id: str = "",
) -> ContentFilter:
    """Return the filter the runtime screens human input with."""
    return GuardrailContentFilter(engine=engine, auditor=auditor, org_id=org_id, team_id=team_id)


__all__ = [
    "HUMAN_INPUT_LOCATION",
    "GuardrailContentFilter",
    "content_filter",
]
