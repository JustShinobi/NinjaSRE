"""Following a vendor's pages, without following them forever.

Two failure modes, and the bound below is aimed at both.

**A vendor whose cursor never terminates.** Some return a next-page token that
points at the same page under load, and a naive loop follows it until the
process runs out of memory. ``max_pages`` is not defensive programming; it is a
bound on a thing that has happened.

**A query the model wrote that matches everything.** An agent asking for "all
logs" against a busy service gets a truthful answer of ten million lines, and
the investigation dies of its own evidence. Article II's bounded autonomy means
the ceiling is a named constant and the caller is told it was hit, rather than
being handed a quietly shortened answer that looks complete.

So ``Pages.truncated`` exists and callers are expected to surface it. An
investigation that says "the first 500 matches, and there were more" is doing
its job; one that says "500 matches" is wrong.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

#: The default ceiling on pages followed in one call. Ten pages of a hundred is
#: a thousand records, which is more than any single piece of evidence in an
#: investigation has ever usefully been.
MAX_PAGES_PER_CALL = 10


@dataclass(frozen=True, slots=True)
class Page[Item]:
    """One page of results, and where the next one starts.

    ``cursor`` is opaque. Vendors variously call it a cursor, a next token, an
    offset, or a link, and normalising them to one word here is what lets the
    pagination loop be written once.
    """

    items: tuple[Item, ...]
    cursor: str | None = None

    @property
    def has_more(self) -> bool:
        """Return whether the vendor said there is another page."""
        return self.cursor is not None


@dataclass(frozen=True, slots=True)
class Pages[Item]:
    """Everything collected across a bounded page walk."""

    items: tuple[Item, ...]
    pages_followed: int
    truncated: bool

    def __len__(self) -> int:
        return len(self.items)


async def collect[Item](
    fetch: Callable[[str | None], Awaitable[Page[Item]]],
    *,
    max_pages: int = MAX_PAGES_PER_CALL,
    max_items: int | None = None,
) -> Pages[Item]:
    """Follow ``fetch``'s cursor and return what fits inside the bounds.

    ``truncated`` is true when either bound stopped the walk while the vendor
    still had more — which is the fact a caller has to pass on, because a
    truncated answer read as a complete one is how an investigation concludes
    that something did not happen.
    """
    collected: list[Item] = []
    cursor: str | None = None
    followed = 0
    truncated = False

    while followed < max_pages:
        page = await fetch(cursor)
        followed += 1
        collected.extend(page.items)

        if max_items is not None and len(collected) >= max_items:
            truncated = len(collected) > max_items or page.has_more
            collected = collected[:max_items]
            break
        if not page.has_more:
            break
        cursor = page.cursor
    else:
        truncated = True

    return Pages(items=tuple(collected), pages_followed=followed, truncated=truncated)


async def iterate[Item](
    fetch: Callable[[str | None], Awaitable[Page[Item]]],
    *,
    max_pages: int = MAX_PAGES_PER_CALL,
) -> AsyncIterator[Item]:
    """Yield items page by page, for a caller that streams rather than collects.

    Same bound, no accumulation. Worth having for a capability that summarises
    as it goes, which is how a long log query stays inside a context budget.
    """
    cursor: str | None = None
    for _ in range(max_pages):
        page = await fetch(cursor)
        for item in page.items:
            yield item
        if not page.has_more:
            return
        cursor = page.cursor


def page_of[Item](items: Sequence[Item], cursor: str | None = None) -> Page[Item]:
    """Return a ``Page`` over ``items``. A convenience for vendor clients."""
    return Page(items=tuple(items), cursor=cursor)


__all__ = [
    "MAX_PAGES_PER_CALL",
    "Page",
    "Pages",
    "collect",
    "iterate",
    "page_of",
]
