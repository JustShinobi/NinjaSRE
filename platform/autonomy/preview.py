"""What a policy change would have done, said in actions rather than in fields.

An operator editing autonomy is not really asking "what does this field mean".
They are asking "what would have happened", and the honest answer is a list:
*these eleven actions from last week would now run without you*. A diff of the
configuration cannot say that, and the two documents can look almost identical
while the answer changes completely.

This works because resolution is pure. The same function the gate calls is
called again over each recorded action, once against the policy set as it is and
once against the proposed one, and the differences are reported. There is no
second implementation of the precedence rules here, which is the property that
stops the preview and the decision drifting apart — the failure that would make
this feature worse than useless, because it would be reassuring and wrong.

**A preview is bounded.** It replays a fixed number of recent actions, most
recent first. A preview nobody can read is one nobody reads, and a preview that
walked a year of history would be a query somebody runs once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config.constants.autonomy import MAX_AUTONOMY_PREVIEW_ACTIONS
from platform.autonomy.levels import AutonomyLevel
from platform.autonomy.policy import PolicySet
from platform.autonomy.resolution import Resolution, resolve
from platform.autonomy.subjects import ProposedAction


@dataclass(frozen=True, slots=True)
class RecordedAction:
    """One action a deployment took, as history remembers it.

    Carries the instant as well as the action, because a freeze window and an
    override both mean different things at different times — replaying last
    Tuesday's action against today's clock would answer a question nobody asked.
    """

    action: ProposedAction
    at: datetime


@dataclass(frozen=True, slots=True)
class PreviewedAction:
    """One recorded action, resolved twice: as it is, and as it would be."""

    action_id: str
    capability: str
    subjects: tuple[str, ...]
    at: datetime
    before: AutonomyLevel
    after: AutonomyLevel
    before_reason: str
    after_reason: str

    @property
    def changed(self) -> bool:
        """Return whether the change would decide this action differently."""
        return self.before is not self.after

    @property
    def more_autonomous(self) -> bool:
        """Return whether the change would let this action run with less asking."""
        return self.after.rank > self.before.rank

    def describe(self) -> str:
        """Return the line the preview shows for this action."""
        if not self.changed:
            return (
                f"{self.capability} on {', '.join(self.subjects)}: unchanged ({self.before.value})"
            )
        direction = "would now" if self.more_autonomous else "would no longer"
        return (
            f"{self.capability} on {', '.join(self.subjects)}: {self.before.value} → "
            f"{self.after.value} ({direction} act with less human involvement)"
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the API and the CLI render."""
        return {
            "action_id": self.action_id,
            "capability": self.capability,
            "subjects": list(self.subjects),
            "at": self.at.isoformat(),
            "before": self.before.value,
            "after": self.after.value,
            "before_reason": self.before_reason,
            "after_reason": self.after_reason,
            "changed": self.changed,
            "more_autonomous": self.more_autonomous,
        }


@dataclass(frozen=True, slots=True)
class PolicyChange:
    """A proposed posture beside the current one, and what separates them."""

    before: PolicySet
    after: PolicySet
    previewed: tuple[PreviewedAction, ...] = ()

    @property
    def changed(self) -> tuple[PreviewedAction, ...]:
        """Return only the actions the change would decide differently."""
        return tuple(entry for entry in self.previewed if entry.changed)

    @property
    def newly_autonomous(self) -> tuple[PreviewedAction, ...]:
        """Return the actions that would run with less asking than before.

        The half an operator has to read. An action that becomes *more* gated is
        a change somebody can discover at leisure; one that becomes less gated is
        a change they are agreeing to have happen while they are asleep.
        """
        return tuple(entry for entry in self.previewed if entry.more_autonomous)

    def summarise(self) -> str:
        """Return the sentence that goes above the list."""
        if not self.previewed:
            return "There is no recorded history to preview this change against."
        if not self.changed:
            return (
                f"None of the last {len(self.previewed)} action(s) would have been decided "
                f"differently."
            )
        return (
            f"{len(self.changed)} of the last {len(self.previewed)} action(s) would be decided "
            f"differently, and {len(self.newly_autonomous)} would run with less human "
            f"involvement than before."
        )

    def to_record(self) -> dict[str, Any]:
        """Return the stored form the API returns and the console renders."""
        return {
            "summary": self.summarise(),
            "considered": len(self.previewed),
            "changed": len(self.changed),
            "newly_autonomous": len(self.newly_autonomous),
            "actions": [entry.to_record() for entry in self.previewed],
        }


def preview_change(
    before: PolicySet,
    after: PolicySet,
    history: Sequence[RecordedAction],
    *,
    limit: int = MAX_AUTONOMY_PREVIEW_ACTIONS,
) -> PolicyChange:
    """Return what ``after`` would have decided differently over ``history``.

    Each action is resolved at *its own* instant rather than at now, so a freeze
    window and an override are evaluated against the moment the action actually
    happened.
    """
    previewed: list[PreviewedAction] = []
    for recorded in list(history)[:limit]:
        was = resolve(recorded.action, before, at=recorded.at)
        would = resolve(recorded.action, after, at=recorded.at)
        previewed.append(_previewed(recorded, was, would))
    return PolicyChange(before=before, after=after, previewed=tuple(previewed))


def _previewed(recorded: RecordedAction, was: Resolution, would: Resolution) -> PreviewedAction:
    """Return one action's before-and-after, as the preview lists it."""
    return PreviewedAction(
        action_id=recorded.action.action_id,
        capability=recorded.action.capability,
        subjects=tuple(subject.resource_id for subject in recorded.action.subjects),
        at=recorded.at,
        before=was.level,
        after=would.level,
        before_reason=was.reason,
        after_reason=would.reason,
    )


__all__ = [
    "PolicyChange",
    "PreviewedAction",
    "RecordedAction",
    "preview_change",
]
