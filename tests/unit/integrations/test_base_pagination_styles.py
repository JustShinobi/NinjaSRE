"""The three styles, and the one place they genuinely differ.

Every test here is about *where the walk ends*, because that is the property a
style declaration buys. A cursor endpoint says when it has run out; an offset
endpoint never does, and the only signal is a page shorter than the one that was
asked for. Getting that backwards produces a client that either reads page one
forever or reports that a vendor has less data than it does — and both look like
a correct answer.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from integrations._base.pagination import (
    EndpointPagination,
    Page,
    PaginationStyle,
    Position,
    supported_styles,
    walk,
)

CURSOR_PAGES = EndpointPagination(
    endpoint="search_logs", style=PaginationStyle.CURSOR, parameter="cursor"
)
TOKEN_PAGES = EndpointPagination(
    endpoint="list_objects", style=PaginationStyle.PAGE_TOKEN, parameter="pageToken"
)
OFFSET_PAGES = EndpointPagination(
    endpoint="list_users",
    style=PaginationStyle.OFFSET,
    parameter="offset",
    page_size_parameter="limit",
    page_size=2,
)
NUMBERED_PAGES = EndpointPagination(
    endpoint="list_projects",
    style=PaginationStyle.PAGE_NUMBER,
    parameter="page",
    page_size_parameter="per_page",
    page_size=2,
)


def scripted(pages: list[Page[str]]) -> tuple[object, list[Mapping[str, str]]]:
    """Return a fetch that answers from ``pages`` and the record of what it was asked."""
    asked: list[Mapping[str, str]] = []

    async def fetch(parameters: Mapping[str, str]) -> Page[str]:
        asked.append(dict(parameters))
        return pages.pop(0) if pages else Page(items=())

    return fetch, asked


def test_every_declared_style_is_walkable() -> None:
    """A style in the enum with no walk behind it would pass every other check silently."""
    assert set(supported_styles()) == {
        PaginationStyle.CURSOR,
        PaginationStyle.OFFSET,
        PaginationStyle.PAGE_NUMBER,
        PaginationStyle.PAGE_TOKEN,
    }


async def test_a_cursor_walk_stops_when_the_vendor_stops_sending_one() -> None:
    fetch, asked = scripted([Page(items=("a",), cursor="c2"), Page(items=("b",))])

    found = await walk(CURSOR_PAGES, fetch)

    assert found.items == ("a", "b")
    assert found.pages_followed == 2
    assert not found.truncated
    assert asked == [{}, {"cursor": "c2"}]


async def test_a_page_token_walk_sends_the_vendors_own_parameter_name() -> None:
    fetch, asked = scripted([Page(items=("a",), cursor="tok"), Page(items=("b",))])

    await walk(TOKEN_PAGES, fetch)

    assert asked == [{}, {"pageToken": "tok"}]


async def test_an_offset_walk_counts_records_and_stops_on_a_short_page() -> None:
    """The whole reason offset is a separate style: nothing else says it ended."""
    fetch, asked = scripted([Page(items=("a", "b")), Page(items=("c",))])

    found = await walk(OFFSET_PAGES, fetch)

    assert found.items == ("a", "b", "c")
    assert asked == [{"offset": "0", "limit": "2"}, {"offset": "2", "limit": "2"}]


async def test_a_full_offset_page_with_no_cursor_still_asks_for_the_next_one() -> None:
    """A cursor walk would have stopped here, having read a third of the data."""
    fetch, _ = scripted([Page(items=("a", "b")), Page(items=("c", "d")), Page(items=("e",))])

    found = await walk(OFFSET_PAGES, fetch)

    assert found.items == ("a", "b", "c", "d", "e")
    assert found.pages_followed == 3


async def test_a_numbered_walk_counts_pages_rather_than_records() -> None:
    """A page-number vendor handed a record count reads from the wrong place entirely."""
    fetch, asked = scripted([Page(items=("a", "b")), Page(items=("c",))])

    found = await walk(NUMBERED_PAGES, fetch)

    assert found.items == ("a", "b", "c")
    assert asked == [{"page": "1", "per_page": "2"}, {"page": "2", "per_page": "2"}]


async def test_a_numbered_walk_stops_on_a_short_page() -> None:
    """Same termination rule as offset, and the same reason: nothing else says it ended."""
    fetch, _ = scripted([Page(items=("a", "b")), Page(items=("c",)), Page(items=("d", "e"))])

    found = await walk(NUMBERED_PAGES, fetch)

    assert found.items == ("a", "b", "c")
    assert found.pages_followed == 2


def test_a_numbered_endpoint_that_declares_no_page_size_is_refused() -> None:
    """Without one there is no short page to detect, so the walk cannot terminate."""
    with pytest.raises(ValueError, match="short page"):
        EndpointPagination(
            endpoint="list_projects", style=PaginationStyle.PAGE_NUMBER, parameter="page"
        )


def test_the_page_numbering_starts_at_one_because_that_is_what_vendors_count_from() -> None:
    """A first request asking for page zero is answered with an empty list or a 400."""
    assert NUMBERED_PAGES.parameters(Position()) == {"page": "1", "per_page": "2"}


async def test_the_page_ceiling_is_reported_rather_than_hidden() -> None:
    """A truncated answer read as a complete one is how a search concludes wrongly."""
    fetch, _ = scripted([Page(items=(str(index),), cursor="more") for index in range(10)])

    found = await walk(CURSOR_PAGES, fetch, max_pages=3)

    assert found.pages_followed == 3
    assert found.truncated


async def test_the_item_ceiling_is_reported_and_the_answer_is_cut_to_it() -> None:
    fetch, _ = scripted([Page(items=("a", "b"), cursor="c2"), Page(items=("c", "d"))])

    found = await walk(CURSOR_PAGES, fetch, max_items=3)

    assert found.items == ("a", "b", "c")
    assert found.truncated


def test_one_vendor_may_use_a_different_style_per_endpoint() -> None:
    """FR-005's second half, which is why the declaration is per endpoint."""
    vendor = (CURSOR_PAGES, OFFSET_PAGES)

    assert {endpoint.style for endpoint in vendor} == {
        PaginationStyle.CURSOR,
        PaginationStyle.OFFSET,
    }
    assert {endpoint.endpoint for endpoint in vendor} == {"search_logs", "list_users"}


def test_an_offset_endpoint_that_declares_no_page_size_is_refused() -> None:
    """Without one there is no short page to detect, so the walk cannot terminate."""
    with pytest.raises(ValueError, match="short page"):
        EndpointPagination(endpoint="list_users", style=PaginationStyle.OFFSET, parameter="offset")


def test_a_declaration_with_no_parameter_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot ask for page two"):
        EndpointPagination(endpoint="search", style=PaginationStyle.CURSOR, parameter=" ")


def test_the_first_position_asks_for_no_token_at_all() -> None:
    """A vendor handed an empty cursor commonly answers 400 rather than page one."""
    assert CURSOR_PAGES.parameters(Position()) == {}
    assert OFFSET_PAGES.parameters(Position()) == {"offset": "0", "limit": "2"}
