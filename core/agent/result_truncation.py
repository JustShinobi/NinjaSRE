"""Showing the model as much of a capability result as it can hold, and saying so.

A single log query against a busy service returns more text than a
seven-billion-parameter model's whole context window. Sending it whole costs the
turn; sending part of it silently is worse, because a model that cannot tell a
short answer from a shortened one reasons from the absence of what it never saw
— "there were no errors after 11:04" is a conclusion the truncation caused.

So the shortening is stated in the text the model reads, and it names the
evidence identifier the whole result is filed under. That identifier is the
difference between this and the context budget next door: the budget *loses* what
it drops, deliberately, once the run is over its ceiling. This drops nothing. The
evidence entry keeps every character, the trace carries the entry, and a
conclusion citing it is checkable against the whole thing.

The two mechanisms compose in the obvious order. This one bounds what any single
result costs; the budget then decides, across everything the run holds, what
still has to go.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.constants.investigation import TOOL_RESULT_TRUNCATION_NOTICE


@dataclass(frozen=True, slots=True)
class TruncatedResult:
    """What the model reads, and what the session keeps.

    Both are carried because the caller needs both at once: ``content`` goes into
    the tool result on the transcript, ``full`` goes onto the evidence entry, and
    a caller holding only one of them would have to go back for the other.
    """

    content: str
    full: str
    truncated: bool = False

    @property
    def dropped_characters(self) -> int:
        """Return how much of the result the model was not shown."""
        return max(len(self.full) - len(self.content), 0)


def truncate_for_model(
    content: str,
    *,
    evidence_id: str,
    ceiling: int,
) -> TruncatedResult:
    """Return ``content`` bounded to ``ceiling``, with the shortening stated.

    ``ceiling`` of zero means "show all of it", and it is what a deployment that
    never probed its model passes. There is deliberately no default: a fixed
    character bound applied everywhere would shorten a frontier model's log
    queries for the sake of a mechanism that exists for small local builds, and a
    default is how that would happen without anybody choosing it.

    A result inside the bound comes back untouched and unmarked — the clean path
    costs one comparison, which is what keeps this from being a tax on a
    deployment whose model has room for its results.

    The notice is counted *inside* the ceiling rather than added on top of it. A
    notice that pushed the result back over the limit would make the mechanism
    increase the thing it exists to bound.
    """
    if ceiling <= 0 or len(content) <= ceiling:
        return TruncatedResult(content=content, full=content)

    # Rendered twice: the notice's own length depends on the numbers in it, and
    # the numbers depend on how much room the notice leaves.
    reserve = len(
        TOOL_RESULT_TRUNCATION_NOTICE.format(
            dropped=len(content), kept=ceiling, evidence=evidence_id
        )
    )
    kept = max(ceiling - reserve, 0)
    head = content[:kept]
    notice = TOOL_RESULT_TRUNCATION_NOTICE.format(
        dropped=len(content) - kept, kept=kept, evidence=evidence_id
    )
    return TruncatedResult(content=head + notice, full=content, truncated=True)


__all__ = ["TruncatedResult", "truncate_for_model"]
