"""The one seam between "what changed" and wherever the answer comes from.

One method, with the shape of the question: *what was altered between T−N and
T*. Everything a source differs in — a directory of apply records, a vendor's
commit API, a pipeline's deployment log — is on the far side of it, and nothing
above this line can tell which answered.

The protocol lives in the platform tier and the implementations sit below it,
which is the same arrangement estate discovery uses: the tier that owns the
domain concept names the contract, and the tier with the vendor knowledge
satisfies it. The infra-apply source is the exception that proves the rule — it
needs no vendor at all, so it lives here, beside the concept it implements.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from config.constants.changes import MAX_CHANGES_PER_WINDOW
from platform.changes.models import Change, ChangeWindow


@runtime_checkable
class ChangeSource(Protocol):
    """Whatever can say what was altered in a window.

    ``name`` is read into the evidence entry rather than derived from the class,
    because the sentence a report has to be able to make is "the infra-apply
    record and the GitLab history were consulted" — and a class name is not what
    an operator calls the thing they configured.
    """

    name: str

    async def changes_in(
        self,
        window: ChangeWindow,
        *,
        limit: int = MAX_CHANGES_PER_WINDOW,
    ) -> Sequence[Change]:
        """Return the changes this source knows about inside ``window``, newest first.

        Bounded by ``limit`` rather than by the caller filtering afterwards: a
        source that read ten thousand commits and handed back fifty has already
        spent what the bound exists to protect.
        """


__all__ = ["ChangeSource"]
