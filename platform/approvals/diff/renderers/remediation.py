"""Production remediation, diffed as the steps it would run and how to undo them.

The contract, filled in when remediation execution lands. It is here now rather
than later for one reason: the approval mechanism is shared, and a change type
with no renderer would fail at the moment somebody tried to review a
remediation — which is during an incident, in front of the person least able to
work around it.

What it renders is the shape a remediation approval has to carry. Not a before
and an after, because the target is a live system rather than a document: the
"before" is what the step would act on and the "after" is what it would do. And
the rollback plan is rendered *beside* the action rather than behind a link,
because a step whose undo procedure nobody read is a step approved on the
assumption that one exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from platform.approvals.diff.engine import DiffLine, DiffOperation, DiffSection, render_value

#: Where the action list and the undo list live in a remediation payload.
STEPS_KEY: Final = "steps"
ROLLBACK_KEY: Final = "rollback"

ACTION_TITLE: Final = "would run"
ROLLBACK_TITLE: Final = "would be undone by"


class RemediationRenderer:
    """Renders a proposed remediation as its steps and its rollback plan."""

    def render(
        self, current: Mapping[str, Any], proposed: Mapping[str, Any]
    ) -> tuple[DiffSection, ...]:
        """Return the steps section, then the rollback section.

        ``current`` is the system state the steps were planned against, and it
        is rendered as the "before" of each step it names. A remediation
        approved against a cluster that has since recovered is exactly the
        conflict the fingerprint catches, and the diff has to make the state
        visible for a reviewer to catch it first.
        """
        sections: list[DiffSection] = []

        actions = tuple(
            DiffLine(
                path=_label(step, ordinal),
                operation=DiffOperation.CHANGED,
                before=render_value(current.get(_name(step, ordinal))),
                after=render_value(_described(step)),
            )
            for ordinal, step in enumerate(_steps(proposed, STEPS_KEY), start=1)
        )
        if actions:
            sections.append(DiffSection(title=ACTION_TITLE, lines=actions))

        undo = tuple(
            DiffLine(
                path=_label(step, ordinal),
                operation=DiffOperation.ADDED,
                after=render_value(_described(step)),
            )
            for ordinal, step in enumerate(_steps(proposed, ROLLBACK_KEY), start=1)
        )
        if undo:
            sections.append(DiffSection(title=ROLLBACK_TITLE, lines=undo))

        return tuple(sections)


def _steps(payload: Mapping[str, Any], key: str) -> tuple[Any, ...]:
    """Return the ordered steps under ``key``, or nothing."""
    found = payload.get(key)
    if isinstance(found, Sequence) and not isinstance(found, str | bytes):
        return tuple(found)
    return ()


def _name(step: Any, ordinal: int) -> str:
    """Return the capability a step calls, for looking its prior state up."""
    if isinstance(step, Mapping):
        return str(step.get("capability", ordinal))
    return str(ordinal)


def _label(step: Any, ordinal: int) -> str:
    """Return how a step is addressed in the diff: its position and its call."""
    return f"{ordinal}. {_name(step, ordinal)}"


def _described(step: Any) -> Any:
    """Return what a step would do, arguments included.

    Arguments included, always. "Restart the deployment" is not what a reviewer
    is approving; "restart the deployment named ``checkout`` in ``production``"
    is, and an approval granted against a description that omitted the target is
    an approval for whichever target the executor happens to pass.
    """
    if not isinstance(step, Mapping):
        return step
    described = step.get("description")
    arguments = step.get("arguments")
    if described is None:
        return arguments if arguments is not None else step
    return f"{described} {render_value(arguments)}" if arguments else described


__all__ = ["RemediationRenderer"]
