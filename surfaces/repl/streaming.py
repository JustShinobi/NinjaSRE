"""Showing an investigation while it happens.

Renders the pipeline's own event stream — thoughts, capability calls, sub-agent
activity, evidence, results — rather than a second narration built alongside it.
That is the property worth protecting: what the REPL shows is derived from the
same events the trace is made of, so anything on screen is something ``runs
replay`` can reproduce, and anything the trace does not carry never appears.

Two renderings, chosen by what the terminal can do rather than by a flag.
Interactive gets live, overwritten status lines; piped gets one line per event
in order. A progress spinner written into a file is a file full of escape
sequences and no information.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import IO, Any

from core.pipeline.streaming import PipelineEvent, PipelineEventKind
from surfaces.cli.output.degradation import PLAIN, Terminal
from surfaces.cli.output.tables import truncate

#: How each event kind is labelled. A closed mapping over a closed enum, so a
#: fourteenth kind is a compile-time-ish failure here rather than an event that
#: silently renders as nothing.
_LABELS: Mapping[PipelineEventKind, str] = {
    PipelineEventKind.STAGE_START: "stage",
    PipelineEventKind.STAGE_END: "stage done",
    PipelineEventKind.THOUGHT: "thinking",
    PipelineEventKind.TOOL_START: "calling",
    PipelineEventKind.TOOL_END: "called",
    PipelineEventKind.SUBAGENT_START: "sub-agent",
    PipelineEventKind.SUBAGENT_END: "sub-agent done",
    PipelineEventKind.EVIDENCE: "evidence",
    PipelineEventKind.QUESTION: "question",
    PipelineEventKind.APPROVAL_REQUEST: "approval",
    PipelineEventKind.MESSAGE_QUEUED: "queued",
    PipelineEventKind.RESULT: "result",
    PipelineEventKind.ERROR: "error",
}

#: Events that are shown in full rather than truncated to a line. A result the
#: operator has to scroll back for is a result they will not read.
_UNABBREVIATED = frozenset({PipelineEventKind.RESULT, PipelineEventKind.ERROR})


def label_of(kind: PipelineEventKind) -> str:
    """Return the word one event kind is shown under."""
    return _LABELS[kind]


def describe(event: PipelineEvent) -> str:
    """Return the one-line body of an event, whichever field carries it."""
    match event.kind:
        case PipelineEventKind.STAGE_START | PipelineEventKind.STAGE_END:
            return event.stage.value if event.stage else ""
        case PipelineEventKind.TOOL_START:
            return event.capability
        case PipelineEventKind.TOOL_END:
            outcome = "failed" if event.failed else "ok"
            return f"{event.capability} {outcome}: {event.text}".rstrip(": ")
        case PipelineEventKind.SUBAGENT_START | PipelineEventKind.SUBAGENT_END:
            return f"{event.subagent} {event.text}".strip()
        case PipelineEventKind.EVIDENCE:
            return event.evidence_id
        case _:
            return event.text


@dataclass(slots=True)
class StreamRenderer:
    """Writes an investigation's events as they arrive.

    Holds the counts a status line needs so ``/status`` and the live line agree
    about what has happened — two tallies of the same stream would eventually
    disagree, and the one on screen is the one nobody checks.
    """

    out: IO[str]
    terminal: Terminal = PLAIN
    evidence_seen: list[str] = field(default_factory=list)
    tool_calls: int = 0
    errors: list[str] = field(default_factory=list)
    result: str = ""
    _open_line: bool = field(default=False, repr=False)

    def handle(self, event: PipelineEvent) -> None:
        """Render one event and fold it into the running tally."""
        self._tally(event)
        if self.terminal.animates and event.kind not in _UNABBREVIATED:
            self._transient(event)
        else:
            self._line(event)

    def handle_all(self, events: Iterable[PipelineEvent]) -> None:
        """Render every event in ``events``, in order."""
        for event in events:
            self.handle(event)
        self.finish()

    def finish(self) -> None:
        """Close any transient line so ordinary output starts on a fresh row."""
        if self._open_line:
            self.out.write("\n")
            self._open_line = False

    def _tally(self, event: PipelineEvent) -> None:
        """Fold one event into the counts a status line reads."""
        match event.kind:
            case PipelineEventKind.EVIDENCE:
                self.evidence_seen.append(event.evidence_id)
            case PipelineEventKind.TOOL_START:
                self.tool_calls += 1
            case PipelineEventKind.ERROR:
                self.errors.append(event.text)
            case PipelineEventKind.RESULT:
                self.result = event.text
            case _:
                pass

    def _prefix(self, event: PipelineEvent) -> str:
        """Return the glyph one event is shown with."""
        if event.kind is PipelineEventKind.ERROR or event.failed:
            return self.terminal.glyph("failed")
        if event.kind is PipelineEventKind.RESULT:
            return self.terminal.glyph("ok")
        if event.kind in {PipelineEventKind.QUESTION, PipelineEventKind.APPROVAL_REQUEST}:
            return self.terminal.glyph("warning")
        return self.terminal.glyph("bullet")

    def _line(self, event: PipelineEvent) -> None:
        """Write one permanent line, the rendering a pipe gets."""
        self.finish()
        body = describe(event)
        head = f"{self._prefix(event)} {label_of(event.kind)}"
        if event.kind in _UNABBREVIATED:
            self.out.write(f"{head}\n{body}\n" if body else f"{head}\n")
            return
        width = max(self.terminal.width - len(head) - 2, 8)
        self.out.write(f"{head}  {truncate(body, width, terminal=self.terminal)}\n".rstrip() + "\n")

    def _transient(self, event: PipelineEvent) -> None:
        """Overwrite the current line, the rendering a terminal gets.

        Carriage return and pad, rather than an escape sequence. It is the one
        cursor movement every terminal that reports itself as a terminal
        actually implements, and the padding is what stops a long line leaving
        a tail behind when the next one is shorter.
        """
        body = f"{self._prefix(event)} {label_of(event.kind)}  {describe(event)}"
        fitted = truncate(body, self.terminal.width - 1, terminal=self.terminal)
        self.out.write("\r" + fitted.ljust(self.terminal.width - 1))
        self._open_line = True

    def status(self) -> Mapping[str, Any]:
        """Return what has happened so far, for ``/status`` to show."""
        return {
            "tool_calls": self.tool_calls,
            "evidence": len(self.evidence_seen),
            "errors": len(self.errors),
            "has_result": bool(self.result),
        }


def render_events(
    events: Iterable[PipelineEvent], out: IO[str], *, terminal: Terminal = PLAIN
) -> StreamRenderer:
    """Render a whole stream and return the renderer holding the tally."""
    renderer = StreamRenderer(out=out, terminal=terminal)
    renderer.handle_all(events)
    return renderer


__all__ = [
    "StreamRenderer",
    "describe",
    "label_of",
    "render_events",
]
