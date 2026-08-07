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

## Four styles, and two real differences among them

FR-005 names cursor, offset, and page-token; page-number is the fourth, and it
is here because a large catalogue turns out to contain a great many vendors that
count pages rather than records.

**Cursor and page-token are one mechanism.** The vendor hands back an opaque
string and the walk ends when it stops handing one back. They are separate
members because an integration author reads their vendor's documentation and
writes down the word they find there, and a taxonomy that forces them to
translate is a taxonomy they get wrong.

**Offset and page-number share a termination rule and not a parameter.** Both
end on a page shorter than the one asked for, because nothing else says the
results ran out; what differs is what the caller sends — a count of records
already read, or a page ordinal counting from one. Sending one where the other
was meant reads from a completely unrelated part of the result set and answers
with data that looks plausible, so they cannot be collapsed either.

A client that assumed the cursor rule against a counted endpoint reads page one
forever, and one that assumed a counted rule against a cursor endpoint stops at
the first page a vendor happens to return short. Both failures look like "the
vendor has less data than it does", which is the worst way for an investigation
to be wrong.

The style is declared **per endpoint**, not per vendor. A single vendor commonly
cursors its log search and offsets its user list, and there is no version of
"the vendor's pagination style" that is true of both.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

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


# --- Declared styles (FR-005) ------------------------------------------------


class PaginationStyle(StrEnum):
    """How one endpoint says where the next page starts."""

    #: The vendor returns an opaque cursor and stops returning one at the end.
    CURSOR = "cursor"
    #: The caller counts records read so far and asks for the ones after them.
    #: The walk ends on a short page, because nothing else says it has.
    OFFSET = "offset"
    #: An opaque token, under the name most vendors that call it that use. Walks
    #: exactly as ``CURSOR`` does; see the module docstring.
    PAGE_TOKEN = "page_token"
    #: The caller asks for page *n*, counting from one. Terminates the way offset
    #: does — on a short page — and is a separate style because the number sent
    #: is a page count and not a record count. A vendor handed a record count in
    #: its page parameter reads from somewhere entirely unrelated and answers
    #: with data that looks plausible, which is the worst kind of wrong.
    PAGE_NUMBER = "page_number"


@dataclass(frozen=True, slots=True)
class Position:
    """Where in a vendor's result set the next request starts."""

    token: str | None = None
    offset: int = 0
    index: int = 0

    @property
    def is_first(self) -> bool:
        """Return whether nothing has been read yet."""
        return self.index == 0


#: The styles whose walk ends on a short page rather than on an absent token.
#: Both count something the caller tracks, so both need a declared page size —
#: without one there is no "short" to compare against and the walk cannot stop.
_COUNTED_STYLES: frozenset[PaginationStyle] = frozenset(
    {PaginationStyle.OFFSET, PaginationStyle.PAGE_NUMBER}
)


@dataclass(frozen=True, slots=True)
class EndpointPagination:
    """How one endpoint of one vendor is paged, declared beside the client.

    ``endpoint`` is the client method's own name, so the catalogue's declaration
    and the code it describes cannot drift without a contract failure naming
    both.
    """

    endpoint: str
    style: PaginationStyle
    parameter: str
    page_size_parameter: str = ""
    page_size: int = 0

    def __post_init__(self) -> None:
        if not self.endpoint.strip():
            raise ValueError("a pagination declaration must name the endpoint it describes")
        if not self.parameter.strip():
            raise ValueError(
                f"{self.endpoint}: a pagination style with no parameter cannot ask for page two"
            )
        if self.style in _COUNTED_STYLES and self.page_size < 1:
            raise ValueError(
                f"{self.endpoint}: a {self.style.value} endpoint must declare its page size, "
                f"because a short page is the only signal that the results have run out"
            )

    def parameters(self, position: Position) -> dict[str, str]:
        """Return the request parameters that ask for the page at ``position``."""
        asked: dict[str, str] = {}
        if self.style is PaginationStyle.OFFSET:
            asked[self.parameter] = str(position.offset)
        elif self.style is PaginationStyle.PAGE_NUMBER:
            asked[self.parameter] = str(position.index + 1)
        elif position.token:
            asked[self.parameter] = position.token
        if self.page_size_parameter and self.page_size:
            asked[self.page_size_parameter] = str(self.page_size)
        return asked

    def has_more[Item](self, page: Page[Item]) -> bool:
        """Return whether ``page`` says there is another one after it."""
        if self.style in _COUNTED_STYLES:
            return len(page.items) >= self.page_size > 0
        return bool(page.cursor)

    def advance[Item](self, position: Position, page: Page[Item]) -> Position:
        """Return where the request after ``page`` starts."""
        if self.style in _COUNTED_STYLES:
            return Position(offset=position.offset + len(page.items), index=position.index + 1)
        return Position(token=page.cursor, index=position.index + 1)


def supported_styles() -> tuple[PaginationStyle, ...]:
    """Return every style the walk below implements."""
    return tuple(PaginationStyle)


async def walk[Item](
    pagination: EndpointPagination,
    fetch: Callable[[Mapping[str, str]], Awaitable[Page[Item]]],
    *,
    max_pages: int = MAX_PAGES_PER_CALL,
    max_items: int | None = None,
) -> Pages[Item]:
    """Follow ``pagination``'s declared style and return what fits inside the bounds.

    The same bounds as ``collect``, and the same reason for them. What this adds
    is that the caller hands over a declaration rather than a cursor: the walk
    decides what to send and when to stop, so an endpoint's style is stated once,
    in the catalogue, instead of being implied by the shape of a closure.
    """
    collected: list[Item] = []
    position = Position()
    followed = 0
    truncated = False

    while followed < max_pages:
        page = await fetch(pagination.parameters(position))
        followed += 1
        collected.extend(page.items)

        if max_items is not None and len(collected) >= max_items:
            truncated = len(collected) > max_items or pagination.has_more(page)
            collected = collected[:max_items]
            break
        if not pagination.has_more(page):
            break
        position = pagination.advance(position, page)
    else:
        truncated = True

    return Pages(items=tuple(collected), pages_followed=followed, truncated=truncated)


__all__ = [
    "MAX_PAGES_PER_CALL",
    "EndpointPagination",
    "Page",
    "PaginationStyle",
    "Pages",
    "Position",
    "collect",
    "iterate",
    "page_of",
    "supported_styles",
    "walk",
]
