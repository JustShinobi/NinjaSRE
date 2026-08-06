"""One shape for "the run is waiting on a human", whatever it is waiting for.

A question the agent asked and an approval somebody has to grant are the same
situation seen twice: a run is suspended, N surfaces are showing something with
a button on it, a clock is running, and the first answer wins. Everything that
follows from that — closing every surface when one of them answers, surviving a
restart with the question still answerable, resolving two people who answered at
once, and telling a run listing that somebody is being waited on — is
implemented against this type rather than against either of the two.

Implementing them separately is not hypothetically worse; it is worse in a
predictable way. One of the two gets persistence and the other does not. One
closes cross-surface and the other leaves a live button in a Slack thread for
the rest of the week. And it is never the same one, so an operator learns that
"answered elsewhere" behaves differently depending on what they were answering.

**The four states are deliberately not the approval vocabulary.** An interaction
is ``PENDING`` until something closes it, and the three ways it closes are: a
human answered, the window ran out, or the thing it was asked about stopped
mattering. Whether the answer was *yes* belongs to the answer, not to the state
— an approval that was rejected and a question that was answered "no" are both
``ANSWERED``, and the surface that has to stop showing a button treats them the
same.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final, Protocol, runtime_checkable

from config.constants.investigation import INTERACTION_EXPIRY_SECONDS


class InteractionKind(StrEnum):
    """What kind of thing the run is waiting on."""

    QUESTION = "question"
    APPROVAL = "approval"


class InteractionState(StrEnum):
    """Where an interaction got to.

    ``SUPERSEDED`` is the state for an interaction that stopped mattering
    without anybody answering it: the run concluded, was cancelled, or a human
    took over and dealt with the thing directly. It is distinct from ``EXPIRED``
    because the two produce different sentences on a surface — "this timed out"
    invites somebody to raise it again, and "this no longer applies" does not.
    """

    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"

    @property
    def is_closed(self) -> bool:
        """Return whether this state is final and no answer applies any more."""
        return self is not InteractionState.PENDING

    @property
    def is_open(self) -> bool:
        """Return whether somebody is still being waited on."""
        return self is InteractionState.PENDING


class AttentionState(StrEnum):
    """Whether a run is waiting on a human, and on what.

    Four values rather than a boolean because a run listing is read to decide
    what to do next, and "waiting on an approval" and "waiting on an answer"
    call for different people. ``BOTH`` exists because a run that is blocked
    twice is the one to look at first.
    """

    NONE = "none"
    WAITING_ON_QUESTION = "waiting_on_question"
    WAITING_ON_APPROVAL = "waiting_on_approval"
    WAITING_ON_BOTH = "waiting_on_both"

    @property
    def needs_attention(self) -> bool:
        """Return whether somebody has to do something for this run to continue."""
        return self is not AttentionState.NONE


@dataclass(frozen=True, slots=True)
class Answer:
    """What a human said, and which human said it.

    ``answered`` is false for the value an expiry produces. Both reach the model
    through the same field, and the flag is what stops "nobody replied" from
    being read as a reply — an agent that cannot tell the two apart will treat
    silence as agreement exactly once, in front of a production change.

    ``principal`` is required in practice and defaulted here only so that the
    no-answer value does not have to invent one. An answer with nobody's name on
    it is not attributable, and Article I's whole claim is that every input to a
    conclusion can be traced to where it came from.
    """

    text: str
    principal: str = ""
    answered_at: datetime | None = None
    selected_option: str = ""
    answered: bool = True
    surface: str = ""
    #: Guardrail rules that rewrote this answer on its way into the run. Kept so
    #: the trace can say the text the model saw is not the text somebody typed.
    redacted_by: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """Return whether the agent may reason from this."""
        return self.answered and bool(self.text.strip())

    @property
    def redacted(self) -> bool:
        """Return whether the guardrails altered this answer."""
        return bool(self.redacted_by)

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this answer."""
        return {
            "text": self.text,
            "principal": self.principal,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
            "selected_option": self.selected_option,
            "answered": self.answered,
            "surface": self.surface,
            "redacted_by": list(self.redacted_by),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> Answer:
        """Return the answer a stored record describes."""
        answered_at = record.get("answered_at")
        return cls(
            text=str(record.get("text", "")),
            principal=str(record.get("principal", "")),
            answered_at=datetime.fromisoformat(str(answered_at)) if answered_at else None,
            selected_option=str(record.get("selected_option", "")),
            answered=bool(record.get("answered", True)),
            surface=str(record.get("surface", "")),
            redacted_by=tuple(str(rule) for rule in record.get("redacted_by") or ()),
        )


#: The surface name used when a run has no surface attached — a batch run, a
#: scheduled sweep, a test. Named rather than left empty so a listing can say
#: "raised nowhere" instead of showing a blank.
NO_SURFACE: Final = "unattached"


@dataclass(frozen=True, slots=True)
class Interaction:
    """One thing a run is waiting on a human for.

    Frozen, and every transition returns a new value. The registry is the only
    thing that decides whether a transition may happen, which is what makes
    first-writer-wins a property of one function rather than a convention every
    surface has to honour.
    """

    interaction_id: str
    run_id: str
    raised_at: datetime
    expires_at: datetime
    kind: InteractionKind = InteractionKind.QUESTION
    state: InteractionState = InteractionState.PENDING
    #: Every surface this was shown on. The origin is first, so a closure that
    #: has to be delivered in some order reaches the person who asked first.
    surfaces: tuple[str, ...] = (NO_SURFACE,)
    answer: Answer | None = None
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.interaction_id:
            raise ValueError("an interaction needs an identifier")
        if not self.run_id:
            raise ValueError("an interaction needs the run it belongs to")
        if self.expires_at <= self.raised_at:
            raise ValueError(
                f"{self.interaction_id!r} expires at or before it was raised. An interaction "
                f"that is already closed when it is raised is one nobody can answer."
            )

    # -- reading --------------------------------------------------------------

    @property
    def origin_surface(self) -> str:
        """Return the surface this was raised from."""
        return self.surfaces[0] if self.surfaces else NO_SURFACE

    @property
    def is_open(self) -> bool:
        """Return whether somebody is still being waited on."""
        return self.state.is_open

    def has_expired(self, now: datetime) -> bool:
        """Return whether the answering window has closed."""
        return self.is_open and now >= self.expires_at

    def describe(self) -> str:
        """Return the one line a run listing or a notification shows."""
        return self.summary or f"{self.kind.value} on run {self.run_id}"

    # -- building the next value ----------------------------------------------

    def answered_with(self, answer: Answer) -> Interaction:
        """Return this interaction closed by ``answer``."""
        return replace(self, state=InteractionState.ANSWERED, answer=answer)

    def expired(self) -> Interaction:
        """Return this interaction closed because nobody answered in time."""
        return replace(self, state=InteractionState.EXPIRED)

    def superseded(self) -> Interaction:
        """Return this interaction closed because it stopped applying."""
        return replace(self, state=InteractionState.SUPERSEDED)

    def on_surfaces(self, surfaces: tuple[str, ...]) -> Interaction:
        """Return this interaction as shown on ``surfaces``."""
        return replace(self, surfaces=surfaces or (NO_SURFACE,))

    # -- persistence ----------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """Return a JSON-serialisable record of this interaction."""
        record: dict[str, Any] = {
            "interaction_id": self.interaction_id,
            "run_id": self.run_id,
            "kind": self.kind.value,
            "state": self.state.value,
            "raised_at": self.raised_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "surfaces": list(self.surfaces),
            "summary": self.summary,
            "answer": self.answer.to_record() if self.answer else None,
        }
        record.update(self._detail_record())
        return record

    def _detail_record(self) -> dict[str, Any]:
        """Return the fields this interaction's kind adds to the record."""
        return {}

    @staticmethod
    def from_record(record: Mapping[str, Any]) -> Interaction:
        """Return the interaction a stored record describes, of its own kind.

        Dispatches on the recorded kind rather than always returning the
        supertype. A question that came back from storage without its options
        is a question a surface renders as free text, which silently loses the
        buttons somebody was going to tap.
        """
        kind = InteractionKind(str(record.get("kind", InteractionKind.QUESTION.value)))
        common = _common_from_record(record)
        if kind is InteractionKind.APPROVAL:
            return ApprovalInteraction(
                **common,
                kind=InteractionKind.APPROVAL,
                action=str(record.get("action", "")),
                diff=str(record.get("diff", "")),
                blast_radius=str(record.get("blast_radius", "")),
                rollback_plan=str(record.get("rollback_plan", "")),
            )
        return Question(
            **common,
            kind=InteractionKind.QUESTION,
            text=str(record.get("text", "")),
            options=tuple(str(option) for option in record.get("options") or ()),
            reason=str(record.get("reason", "")),
        )


@dataclass(frozen=True, slots=True)
class Question(Interaction):
    """A request for something only a person knows.

    ``reason`` is not decoration. The person reading this in a chat thread did
    not follow the investigation, and "what will change depending on your
    answer" is the difference between a question somebody answers and one they
    scroll past.
    """

    kind: InteractionKind = InteractionKind.QUESTION
    text: str = ""
    options: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        # Named explicitly rather than through zero-argument ``super()``:
        # ``slots=True`` rebuilds the class, and the closure the implicit form
        # depends on is a thing to not rely on across interpreter versions.
        Interaction.__post_init__(self)
        if not self.text.strip():
            raise ValueError(f"{self.interaction_id!r}: a question has to carry a question")

    def describe(self) -> str:
        """Return the question itself, which is the line a surface shows."""
        return self.text

    def _detail_record(self) -> dict[str, Any]:
        return {"text": self.text, "options": list(self.options), "reason": self.reason}


@dataclass(frozen=True, slots=True)
class ApprovalInteraction(Interaction):
    """A proposed change waiting on somebody with the standing to allow it.

    Carries what a reviewer is shown rather than what the change *is*. The
    change itself lives in the approvals service, which owns applying it; this
    is the waiting-on-a-human half, and keeping it to a summary is what stops a
    diff from being copied into every surface's transport.
    """

    kind: InteractionKind = InteractionKind.APPROVAL
    action: str = ""
    diff: str = ""
    blast_radius: str = ""
    rollback_plan: str = ""

    def describe(self) -> str:
        """Return the one line a reviewer sees before they open anything."""
        return self.summary or self.action

    def _detail_record(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "diff": self.diff,
            "blast_radius": self.blast_radius,
            "rollback_plan": self.rollback_plan,
        }


def _common_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fields every interaction carries, from a stored record."""
    answer = record.get("answer")
    return {
        "interaction_id": str(record["interaction_id"]),
        "run_id": str(record["run_id"]),
        "raised_at": datetime.fromisoformat(str(record["raised_at"])),
        "expires_at": datetime.fromisoformat(str(record["expires_at"])),
        "state": InteractionState(str(record.get("state", InteractionState.PENDING.value))),
        "surfaces": tuple(str(surface) for surface in record.get("surfaces") or (NO_SURFACE,)),
        "summary": str(record.get("summary", "")),
        "answer": Answer.from_record(answer) if isinstance(answer, Mapping) else None,
    }


def question(
    *,
    interaction_id: str,
    run_id: str,
    text: str,
    reason: str = "",
    options: tuple[str, ...] = (),
    surfaces: tuple[str, ...] = (),
    at: datetime | None = None,
    expiry_seconds: float = INTERACTION_EXPIRY_SECONDS,
) -> Question:
    """Return a question raised at ``at``, expiring after ``expiry_seconds``.

    The expiry is computed here rather than supplied, so no caller can raise a
    question that outlives the incident it was asked during.
    """
    raised = at if at is not None else datetime.now(UTC)
    return Question(
        interaction_id=interaction_id,
        run_id=run_id,
        raised_at=raised,
        expires_at=raised + timedelta(seconds=expiry_seconds),
        surfaces=surfaces or (NO_SURFACE,),
        summary=text,
        text=text,
        options=options,
        reason=reason,
    )


@dataclass(frozen=True, slots=True)
class Resolution:
    """The outcome of trying to answer an interaction.

    Carried as a value rather than raised, because "somebody else answered
    first" is a normal thing to happen during an incident and not an error. The
    surface that lost still has to tell its human something, and it needs the
    winning answer to say what.
    """

    interaction: Interaction
    won: bool
    #: Set when this attempt lost. The principal who did answer, so the loser is
    #: told who rather than only that they were too late.
    answered_by: str = ""
    reason: str = ""

    @property
    def lost(self) -> bool:
        """Return whether this attempt arrived after the interaction closed."""
        return not self.won


@dataclass(frozen=True, slots=True)
class ScreenedText:
    """Text after the guardrails have looked at it.

    ``blocked`` and ``text`` are both meaningful when a rule blocked: the text
    is the redacted form, and a caller that decides to proceed anyway proceeds
    with the redaction rather than with what somebody typed.
    """

    text: str
    rules: tuple[str, ...] = field(default_factory=tuple)
    blocked: bool = False

    @property
    def altered(self) -> bool:
        """Return whether anything matched."""
        return bool(self.rules)


@runtime_checkable
class ContentFilter(Protocol):
    """Whatever inspects human-supplied text before the agent reads it.

    A port rather than the guardrail engine itself, for the reason every port
    in this tier exists: the runtime's behaviour must not depend on a ruleset
    being configured, and a test of the closure path should not have to compile
    thirty regular expressions to run.

    ``platform.guardrails`` supplies the real one. The default here is no
    filtering, which is correct for a deployment that has not configured
    guardrails and is *not* correct for one that has — which is why the wiring
    is explicit rather than defaulted to something plausible.
    """

    def screen(self, text: str) -> ScreenedText:
        """Return ``text`` as the agent may see it, and what altered it."""


def screen_with(screen: ContentFilter | None, text: str) -> ScreenedText:
    """Return ``text`` screened by ``screen``, or unchanged when there is none."""
    return ScreenedText(text=text) if screen is None else screen.screen(text)


__all__ = [
    "NO_SURFACE",
    "Answer",
    "ApprovalInteraction",
    "AttentionState",
    "ContentFilter",
    "Interaction",
    "InteractionKind",
    "InteractionState",
    "Question",
    "Resolution",
    "ScreenedText",
    "question",
    "screen_with",
]
