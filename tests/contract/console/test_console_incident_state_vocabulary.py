"""Hold the console's incident vocabulary against the store's own enumeration.

There is already a check of this shape for run statuses
(``tools/check_run_status_vocabulary.py``), and there was never one for
incident states. The drift it would have caught was live: the console declared
``closed``, which ``IncidentState`` does not contain and the gateway therefore
cannot serve, and did not declare ``resolved``, ``awaiting_human``,
``remediating`` or ``closed_without_action``, every one of which it does.

Both directions are defects, and they are different defects:

*excess*
    A word the gateway never serves. Every screen that compares against it
    is dead code — the overview skipped an incident when its state equalled
    ``closed``, so the skip never once fired and a finished investigation was
    counted as one waiting on a person.

*missing*
    A word the gateway does serve. It falls through
    ``statusPresentation`` to the neutral "unknown" rendering, so a resolved
    incident is drawn in the same grey as a state the console has never heard
    of.

The enumeration is imported rather than copied, because a literal list here
would just be a third vocabulary for this check to drift from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from platform.persistence.ports.incident_store import IncidentState
from tools.check_incident_state_vocabulary import (
    console_presentation,
    console_vocabulary,
)
from tools.console_toolchain import console_root

pytestmark = pytest.mark.contract

STATUS_MODULE: Path = console_root() / "src" / "design" / "status.ts"


def test_the_console_declares_every_state_the_store_can_write() -> None:
    """Every member of the enumeration is a word the console draws deliberately."""
    declared = set(console_vocabulary(STATUS_MODULE))
    missing = sorted(state.value for state in IncidentState if state.value not in declared)
    assert missing == [], (
        f"console/src/design/status.ts does not declare {missing}, which the gateway serves "
        "verbatim from IncidentState — each one renders as an unknown status today"
    )


def test_the_console_declares_no_incident_state_the_store_cannot_write() -> None:
    """`INCIDENT_STATES` is this enumeration and nothing else.

    Equality rather than a guess about which words look like a state: the
    console's closed set exists precisely so this question has an exact answer.
    """
    declared = sorted(console_vocabulary(STATUS_MODULE))
    real = sorted(state.value for state in IncidentState)
    assert declared == real, (
        "console/src/design/status.ts::INCIDENT_STATES and IncidentState disagree; every "
        "word in one and not the other is either a screen nobody will see or a real "
        "incident sent down the fallback rendering path"
    )


def test_every_state_is_drawn_deliberately_rather_than_as_an_unknown_word() -> None:
    """Each state has a role and a shape, so none renders as a status nobody declared."""
    presented = set(console_presentation(STATUS_MODULE))
    undrawn = sorted(state.value for state in IncidentState if state.value not in presented)
    assert undrawn == [], (
        f"ATTENTION_STATUSES gives no role or shape to {undrawn}, so a real incident is "
        "drawn in the neutral grey the console reserves for a word it has never seen"
    )
