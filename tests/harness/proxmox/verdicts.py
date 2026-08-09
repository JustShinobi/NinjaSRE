"""The four closed vocabularies this suite scores in.

They are enumerations rather than strings for one reason: a report counts them.
"How many scenarios did this change turn from correct to harmful" is the
question the whole feature exists to answer, and a scheme where a scorer can
invent a fifth verdict cannot answer it — the count silently omits whatever
somebody spelled differently.

``ResponseKind`` is the one that carries an argument. Escalating is a response,
not the absence of one: several of these scenarios have no safe automatic answer
— an unreachable node in a two-node cluster being the clearest — and reporting
"no action taken" there would train the system, and the people tuning it, in
exactly the wrong direction.
"""

from __future__ import annotations

from enum import StrEnum


class ActionVerdict(StrEnum):
    """What the system did about the situation, judged against what it should have.

    ``harmful`` and ``unnecessary`` are deliberately different. A wrong action
    that starts a stopped container costs an operator an afternoon; a wrong
    action that hard-stops a running one costs whatever had not been flushed.
    Collapsing them would make the number that matters unreadable.
    """

    CORRECT = "correct"
    HARMFUL = "harmful"
    UNNECESSARY = "unnecessary"
    ABSENT = "absent"


class DiagnosisVerdict(StrEnum):
    """What the conclusion was worth, evidence included.

    ``unsupported`` is the verdict that distinguishes an investigation from a
    lucky prior: the right root cause, reached without the readings it should
    have rested on. Folding it into ``correct`` would reward guessing on exactly
    the scenarios where guessing is easiest.
    """

    CORRECT = "correct"
    UNSUPPORTED = "unsupported"
    INCORRECT = "incorrect"
    ABSENT = "absent"


class CompletionVerdict(StrEnum):
    """Whether the run reached an end at all.

    Kept apart from the diagnosis so that a model too small to finish a scenario
    is reported as that rather than as a wrong answer. The two call for opposite
    responses — one is a capacity question and the other is a capability one —
    and a suite that conflated them would recommend prompt work for a context
    window.
    """

    COMPLETED = "completed"
    INCOMPLETE = "incomplete"


class ResponseKind(StrEnum):
    """The shape of a response: what a scenario asked for, and what a run gave.

    ``wait`` is separate from ``none`` because they are different instructions.
    A guest locked by a live backup wants somebody to come back in ten minutes;
    a condition that cleared on its own wants nobody to do anything ever. A run
    that did nothing where waiting was correct did the safe thing and did not say
    it would look again, and the reasoning says so.
    """

    ACT = "act"
    ESCALATE = "escalate"
    WAIT = "wait"
    NONE = "none"


__all__ = ["ActionVerdict", "CompletionVerdict", "DiagnosisVerdict", "ResponseKind"]
