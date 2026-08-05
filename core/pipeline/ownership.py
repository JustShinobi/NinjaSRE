"""Which stage is allowed to write which field, as data rather than as a habit.

Pure-function stages are only pure if nothing writes outside what it declared.
Convention does not survive twenty contributors — the third time somebody needs
one more field, "it was convenient" wins — so this is a table, and
``tests/unit/core/pipeline/test_stage_purity.py`` reads it and fails the build.

Granularity is ``slice.field`` rather than the slice. "The intake stage writes
the investigation slice" would be true of five of the six stages and would
enforce nothing; "the intake stage writes ``investigation.alert`` and
``investigation.window``" is a claim that can be violated.

Two entries deserve their reason written down.

``investigation.outcome`` has four writers. Every stage that can end the run
early has to be able to say why it ended, and the alternative — a separate
``halt`` flag per stage — would put the same fact in four places.

The accounting fields have three. Intake and diagnosis each make a model call,
and a run that accounted only for the loop's tokens would under-report its own
cost, which is the number an operator uses to decide whether this is affordable.

``approvals`` and ``memory`` have no writer at all, on purpose. The slices exist
because the shape has to be settled before the features that fill them
(approvals gating, episodic memory) land; declaring a writer that does not
exist would mean the purity test permitted a write nobody makes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from core.state.types import StageName

#: The cost fields any stage that spends tokens may write.
_ACCOUNTING: Final[frozenset[str]] = frozenset(
    {
        "accounting.tokens",
        "accounting.llm_calls",
    }
)

#: Every accounting field, which only the stage that runs the loop touches.
_FULL_ACCOUNTING: Final[frozenset[str]] = _ACCOUNTING | {
    "accounting.capability_executions",
    "accounting.iterations",
    "accounting.runtime",
    "accounting.status",
}

#: The declared write set per stage. A path absent from a stage's entry is a
#: path that stage may not change, and the purity test says so by name.
STAGE_WRITES: Final[Mapping[StageName, frozenset[str]]] = {
    StageName.RESOLVE_INTEGRATIONS: frozenset(
        {
            "investigation.catalogue",
            "investigation.outcome",
        }
    ),
    StageName.INTAKE: frozenset(
        {
            "investigation.alert",
            "investigation.window",
            "investigation.classification",
            "investigation.link",
            "investigation.outcome",
            "chat.messages",
            "chat.channel",
            "chat.thread_id",
        }
    )
    | _ACCOUNTING,
    StageName.PLAN_EVIDENCE: frozenset({"investigation.plan"}),
    StageName.GATHER_EVIDENCE: frozenset(
        {
            "evidence.entries",
            "investigation.conclusion",
            "investigation.outcome",
        }
    )
    | _FULL_ACCOUNTING,
    StageName.DIAGNOSE: frozenset({"investigation.diagnosis"}) | _ACCOUNTING,
    StageName.DELIVER: frozenset(
        {
            "investigation.delivery",
            "investigation.outcome",
        }
    ),
}


def writes_of(stage: StageName) -> frozenset[str]:
    """Return the paths ``stage`` is allowed to change."""
    return STAGE_WRITES[stage]


def violations(stage: StageName, changed: frozenset[str]) -> tuple[str, ...]:
    """Return the paths ``stage`` changed that it did not declare, in name order."""
    return tuple(sorted(changed - writes_of(stage)))


def owners_of(path: str) -> tuple[StageName, ...]:
    """Return every stage allowed to write ``path``, in pipeline order."""
    return tuple(stage for stage, declared in STAGE_WRITES.items() if path in declared)


__all__ = [
    "STAGE_WRITES",
    "owners_of",
    "violations",
    "writes_of",
]
