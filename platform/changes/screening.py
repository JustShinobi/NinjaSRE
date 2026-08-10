"""What a change is put through before anything can read it.

A commit message is free text written by whoever was in a hurry, and a path is a
filename chosen by the same person. Both reach an investigation's trace, which
is stored, rendered in a console, and — the part that matters — put in front of
whichever model the deployment configured. A credential pasted into a commit
message while somebody rotated it is the obvious leak, and it is the one that
actually happens.

Nothing new is declared here. A change passes the same guardrail ruleset a
synced document passes, so "what counts as a secret" stays one decision taken in
one place. What differs is the *response*, and the difference is deliberate: a
document carrying a secret is refused, because a corpus is better off without
it; a change carrying one is redacted and kept, because the change is the
evidence and an investigation blind to the apply that broke the cluster is worse
than one that reads a redaction marker.

Screening happens inside the source, not at the caller. A boundary a caller has
to remember is one the third source forgets.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from platform.changes.models import Change
from platform.guardrails.engine import GuardrailEngine
from platform.observability.logging import get_logger

logger = get_logger(__name__)


def screen(change: Change, *, engine: GuardrailEngine | None = None) -> Change:
    """Return ``change`` with its message and paths redacted, rules named.

    Returns the same object when nothing fired, so the ordinary case — which is
    every change in every well-behaved repository — costs one scan and no
    allocation.
    """
    scanner = engine if engine is not None else GuardrailEngine()

    message = scanner.scan(change.message)
    paths: list[str] = []
    fired: set[str] = {match.rule for match in message.matches}
    altered = message.text != change.message

    for path in change.paths:
        scanned = scanner.scan(path)
        fired.update(match.rule for match in scanned.matches)
        altered = altered or scanned.text != path
        paths.append(scanned.text)

    if not altered:
        return change

    logger.info(
        "changes.screened",
        change_id=change.change_id,
        source=change.source,
        rules=sorted(fired),
    )
    return replace(
        change,
        message=message.text,
        paths=tuple(paths),
        # Merged with what the change already carries, so screening a change
        # twice names the rule once rather than twice.
        redactions=tuple(sorted(set(change.redactions) | fired)),
        # Recomputed by the record itself, and passed through unchanged: a
        # redaction marker is shorter than what it replaced, so re-deriving the
        # counts here would report fewer paths than the change really touched.
        paths_seen=change.paths_seen,
        paths_truncated=change.paths_truncated,
        message_truncated=change.message_truncated,
    )


def screen_all(
    changes: Iterable[Change],
    *,
    engine: GuardrailEngine | None = None,
) -> Sequence[Change]:
    """Return every change screened, in the order it arrived."""
    scanner = engine if engine is not None else GuardrailEngine()
    return tuple(screen(change, engine=scanner) for change in changes)


__all__ = ["screen", "screen_all"]
