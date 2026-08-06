"""The last boundary: what each destination is allowed to be told.

Redaction happens *here* rather than at each call site, and that placement is
the design rather than a convenience. Redacting centrally at the point a failure
is constructed would mean the engineer running ``ninjasre investigate`` at their
own terminal sees ``[REDACTED]`` too — and they are already authorised, already
looking at the logs, and now unable to debug. Redacting at the sink means one
shared code path produces the full detail for them and the safe summary for
everybody else, with no flag anybody can default wrongly.

Two independent questions are answered here, and they are answered separately
because their answers differ.

**Is this destination external?** An HTTP response, a chat message, a web
console, and the database are all filtered. The local CLI and the REPL are not.
Persistence is on the filtered side even though nothing leaves the host: a
secret written to the database is a secret in every backup, every replica, and
every export from then on, and "it stays on our infrastructure" is a claim about
the network rather than about the blast radius.

**Is this reader authorised to see identifiers?** Separate question, separate
answer. Restoration turns tokens back into pod names, and a chat channel with
mixed membership is a place where redaction is not wanted but restoration is
not either. A token left in place is meaningless without the mapping, which is
exactly what makes it the right thing to leave.
"""

from __future__ import annotations

from enum import StrEnum

from config.constants.surfaces import (
    SURFACE_CHAT,
    SURFACE_CLI,
    SURFACE_REPL,
    SURFACE_REST_API,
    SURFACE_WEB_CONSOLE,
)
from core.llm.redaction import external_error_summary, internal_detail
from platform.guardrails.engine import GuardrailEngine, ScanResult
from platform.masking.context import MaskingContext


class Sink(StrEnum):
    """Where a piece of text is on its way to.

    Closed, and partitioned by ``EXTERNAL_SINKS`` and ``LOCAL_SINKS`` below. A
    sink nobody classified would fall into whichever branch happened to be
    written first, so a test asserts the two sets cover this enum exactly.
    """

    CLI = SURFACE_CLI
    REPL = SURFACE_REPL
    REST_API = SURFACE_REST_API
    WEB_CONSOLE = SURFACE_WEB_CONSOLE
    CHAT = SURFACE_CHAT
    PERSISTENCE = "persistence"
    REPORT = "report"


#: Filtered. Everything that is published, transmitted, or written down.
EXTERNAL_SINKS: frozenset[Sink] = frozenset(
    {
        Sink.REST_API,
        Sink.WEB_CONSOLE,
        Sink.CHAT,
        Sink.PERSISTENCE,
        Sink.REPORT,
    }
)

#: Unfiltered. A human at a terminal on the operator's own host, who can read
#: the logs anyway and is trying to find out why something broke.
LOCAL_SINKS: frozenset[Sink] = frozenset({Sink.CLI, Sink.REPL})


def is_external(sink: Sink) -> bool:
    """Return whether ``sink`` publishes beyond the process that produced the text."""
    return sink in EXTERNAL_SINKS


class SinkGuard:
    """The one place text and failures cross from inside to outside.

    Holds the engine and, optionally, the run's masking context. The context is
    optional because not every sink belongs to a run — a health endpoint has no
    investigation behind it — and a guard without one simply never restores.
    """

    __slots__ = ("_engine", "_masking")

    def __init__(
        self,
        *,
        engine: GuardrailEngine,
        masking: MaskingContext | None = None,
    ) -> None:
        self._engine = engine
        self._masking = masking

    @property
    def masking(self) -> MaskingContext | None:
        """Return the run's masking context, if this guard belongs to a run."""
        return self._masking

    def render(self, text: str, *, sink: Sink, authorised: bool = False) -> str:
        """Return ``text`` as ``sink`` may see it.

        A local sink is authorised by construction — the person reading it is
        sitting at the host — so ``authorised`` only decides anything for the
        external ones.
        """
        restored = self._restore(text) if (authorised or not is_external(sink)) else text
        if not is_external(sink):
            return restored
        return self._engine.scan(restored).text

    def inspect(self, text: str) -> ScanResult:
        """Return what the ruleset finds in ``text``, without rendering anything.

        How a caller audits a *local* sink. ``render`` leaves local text alone,
        which is the point of redacting at the sink at all, so a deployment
        that wants the trail to say what would have matched at the terminal
        calls this beside it. The engine is never removed from the boundary; at
        a local sink it is only the acting on the result that is skipped.
        """
        return self._engine.scan(text)

    def render_failure(self, error: BaseException, *, sink: Sink) -> str:
        """Return what ``sink`` may be told about ``error``.

        The external rendering is a fixed sentence plus, at most, the
        exception's *type name*. A type name is a fact about NinjaSRE's own
        code; a message is a fact about the request, and the request is what has
        to stay inside.
        """
        if is_external(sink):
            return external_error_summary(error)
        return internal_detail(error)

    def _restore(self, text: str) -> str:
        """Return ``text`` with this run's tokens turned back into identifiers."""
        if self._masking is None:
            return text
        return self._masking.unmask(text)


__all__ = [
    "EXTERNAL_SINKS",
    "LOCAL_SINKS",
    "Sink",
    "SinkGuard",
    "is_external",
]
