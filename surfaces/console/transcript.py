"""The one component that renders a run, live or replayed.

Both consume the same event vocabulary — ``platform/runs/events.py``'s
``TraceEventKind``, which is what the SSE stream carries and what the replay
route returns. The only difference between watching a run and reviewing one is
where the events came from, so building this once is what guarantees a replay
looks exactly like the live run did. Two components would diverge, and the
divergence would be invisible: nobody compares a live run against its own replay
except by accident, and by then the trace is the thing being relied on.

Three properties this file owns.

**Every event kind is rendered.** Including the ones where nothing the user
asked for happened — a guardrail action, a budget eviction, a masking
application. Those are the events an operator needs and the easiest to leave
out, and a transcript that silently skipped a kind would be a transcript that
disagreed with the trace.

**Only a window is built.** Ten events and ten thousand produce the same number
of elements (see ``virtualisation.py``), so opening a long run costs what
opening a short one costs.

**A masked identifier is shown as masked.** The console never restores one —
restoration is the server's decision, made per viewer at the sink
(``platform/guardrails/sinks.py``) — but a token rendered as plain text reads
like a hostname, and a reader who does not know it is a token will go looking
for a pod by that name.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from platform.masking.mapping import TOKEN_PATTERN
from platform.runs.events import TraceEventKind
from surfaces.console.html import Child, Element, element, fragment
from surfaces.console.virtualisation import Window, slice_of, window_at_end

#: How much of a capability result is shown before it is folded away. A result
#: payload can be a megabyte of JSON, and pasting one into the page is how a
#: transcript stops scrolling.
MAX_INLINE_RESULT_CHARS: Final = 2_000

#: What each event kind is called on screen. A mapping rather than a formatting
#: rule, because "budget_eviction" is not a phrase and an operator reading it at
#: three in the morning should not have to translate.
EVENT_LABELS: Final[Mapping[TraceEventKind, str]] = {
    TraceEventKind.RUN_STARTED: "Investigation started",
    TraceEventKind.TURN_COMPLETED: "Thought",
    TraceEventKind.CAPABILITY_CALLED: "Capability call",
    TraceEventKind.EVIDENCE_OBSERVED: "Evidence",
    TraceEventKind.SUBAGENT_DISPATCHED: "Sub-agent dispatched",
    TraceEventKind.GUARDRAIL_ACTION: "Guardrail",
    TraceEventKind.MASKING_APPLIED: "Masking",
    TraceEventKind.BUDGET_EVICTION: "Context budget",
    TraceEventKind.APPROVAL_REQUESTED: "Approval requested",
    TraceEventKind.ATTENTION_CHANGED: "Waiting for a person",
    TraceEventKind.RUN_INTERRUPTED: "Interrupted",
    TraceEventKind.RUN_FINISHED: "Finished",
}


@dataclass(frozen=True, slots=True)
class TranscriptEvent:
    """One event of a run, as the transcript needs it.

    Deliberately not ``platform.runs.events.RunEvent``: the console receives
    JSON from the API and never holds the platform's own types, which is what
    keeps FR-030 true rather than aspirational.
    """

    run_id: str
    kind: str
    sequence: int
    occurred_at: str | None = None
    turn_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def of(cls, document: Mapping[str, Any]) -> TranscriptEvent:
        """Return the event a stream frame or a replay record describes."""
        payload = document.get("payload")
        return cls(
            run_id=str(document.get("run_id", "")),
            kind=str(document.get("kind", "")),
            sequence=int(document.get("sequence", 0)),
            occurred_at=document.get("occurred_at"),
            turn_id=document.get("turn_id"),
            payload=dict(payload) if isinstance(payload, Mapping) else {},
        )

    @property
    def label(self) -> str:
        """Return what this event is called on screen."""
        try:
            return EVENT_LABELS[TraceEventKind(self.kind)]
        except ValueError:
            # A trace written by a newer deployment. Shown rather than dropped:
            # an unrecognised event is still evidence that something happened,
            # and hiding it would make the transcript disagree with the trace.
            return self.kind.replace("_", " ").capitalize()

    @property
    def is_subagent(self) -> bool:
        """Return whether this event dispatched a sub-agent with turns of its own."""
        return self.kind == TraceEventKind.SUBAGENT_DISPATCHED.value


def masked_text(text: str) -> Element:
    """Return ``text`` with every masking token marked up as one.

    The console does not and cannot restore a token: it never receives the
    mapping for content the viewer is not authorised to see unmasked. What it
    can do is stop a token reading as a real name, which is the difference
    between "this identifier is hidden from you" and an operator searching a
    cluster for a pod that was never called that.
    """
    parts: list[Child] = []
    position = 0
    for match in TOKEN_PATTERN.finditer(text):
        if match.start() > position:
            parts.append(text[position : match.start()])
        parts.append(
            element(
                "span",
                match.group(0),
                class_="masked",
                title="A masked identifier. Restoring it needs an authorisation you do not hold.",
            )
        )
        position = match.end()
    if position < len(text):
        parts.append(text[position:])
    return fragment(*parts)


def render_event(event: TranscriptEvent, *, expanded: bool = False) -> Element:
    """Return one transcript entry.

    ``expanded`` opens a sub-agent's nested turns and calls. Closed by default:
    a run that dispatched six sub-agents would otherwise open as six transcripts
    at once, and the reader wanted the outer one.
    """
    body: list[Child] = [
        element(
            "p",
            element("span", event.label, class_="transcript__kind"),
            " ",
            element("time", event.occurred_at, datetime=event.occurred_at)
            if event.occurred_at
            else None,
            class_="transcript__head",
        )
    ]

    text = _text_of(event.payload)
    if text:
        body.append(element("p", masked_text(text)))

    capability = event.payload.get("capability") or event.payload.get("tool")
    if capability:
        body.append(_capability_block(str(capability), event.payload))

    if event.is_subagent:
        body.append(_subagent_block(event, expanded=expanded))

    return element(
        "li",
        *body,
        class_="transcript__event",
        data_kind=event.kind,
        data_sequence=str(event.sequence),
        id=f"event-{event.sequence}",
    )


def render_transcript(
    events: Sequence[TranscriptEvent],
    *,
    window: Window | None = None,
    expanded: Sequence[int] = (),
) -> Element:
    """Return the transcript, rendering only the events inside ``window``.

    The spacers are ``<li>`` elements carrying a count rather than nothing at
    all: a reader who scrolls into one should be told what is there, and a list
    whose length disagrees with the number of items in it is a list a screen
    reader announces wrongly.
    """
    chosen = window if window is not None else window_at_end(len(events))
    opened = frozenset(expanded)

    entries: list[Child] = []
    if chosen.before:
        entries.append(_spacer(chosen.before, "earlier"))
    entries.extend(
        render_event(event, expanded=event.sequence in opened) for event in slice_of(events, chosen)
    )
    if chosen.after:
        entries.append(_spacer(chosen.after, "later"))

    return element(
        "ol",
        *entries,
        class_="transcript",
        aria_label="Investigation transcript",
        data_total=str(chosen.total),
        data_rendered=str(chosen.count),
    )


def _spacer(count: int, direction: str) -> Element:
    """Return the stand-in for the events outside the window."""
    return element(
        "li",
        element("button", f"Show {count} {direction} events", type="button"),
        class_="transcript__spacer",
        data_spacer=direction,
        data_count=str(count),
    )


def _capability_block(capability: str, payload: Mapping[str, Any]) -> Element:
    """Return the call, its arguments, and its result — the three Article I needs."""
    return element(
        "details",
        element("summary", capability),
        _pre("Arguments", payload.get("arguments")),
        _pre("Result", payload.get("result")),
        element("p", "Side effect: ", str(payload.get("side_effect_level", "read")), class_="muted")
        if payload.get("side_effect_level")
        else None,
        class_="transcript__call",
        data_capability=capability,
    )


def _subagent_block(event: TranscriptEvent, *, expanded: bool) -> Element:
    """Return a sub-agent's own turns and calls, expandable (FR-007)."""
    nested = event.payload.get("turns")
    turns = nested if isinstance(nested, list) else []
    return element(
        "details",
        element(
            "summary",
            f"{len(turns)} nested turn{'' if len(turns) == 1 else 's'}",
        ),
        element(
            "ol",
            *[
                render_event(TranscriptEvent.of(turn), expanded=False)
                for turn in turns
                if isinstance(turn, Mapping)
            ],
            class_="transcript transcript--nested",
        ),
        class_="transcript__subagent",
        open=expanded,
    )


def _pre(label: str, value: Any) -> Element | None:
    """Return a labelled, length-bounded rendering of a payload value."""
    if value is None:
        return None
    rendered = value if isinstance(value, str) else json.dumps(value, indent=2, sort_keys=True)
    truncated = len(rendered) > MAX_INLINE_RESULT_CHARS
    shown = rendered[:MAX_INLINE_RESULT_CHARS] if truncated else rendered
    # A description list rather than a heading. "Arguments" labels the block
    # beneath it, but it is not a section of the document, and putting it in the
    # outline would make a transcript of two hundred calls a table of contents
    # with four hundred entries in it.
    return element(
        "dl",
        element("dt", label),
        element(
            "dd",
            element("pre", masked_text(shown)),
            element(
                "p",
                f"Truncated: {len(rendered) - MAX_INLINE_RESULT_CHARS} more characters.",
                class_="muted",
            )
            if truncated
            else None,
        ),
        class_="transcript__payload",
    )


def _text_of(payload: Mapping[str, Any]) -> str:
    """Return whatever this payload says in words, or the empty string."""
    for key in ("text", "summary", "message", "reason", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


__all__ = [
    "EVENT_LABELS",
    "MAX_INLINE_RESULT_CHARS",
    "TranscriptEvent",
    "masked_text",
    "render_event",
    "render_transcript",
]
