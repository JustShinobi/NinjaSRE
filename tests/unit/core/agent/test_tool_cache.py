"""The in-run duplicate cache, and the sentence that makes it work.

Serving a repeated call from cache saves the vendor round trip, which is the
small half. The large half is telling the model, in words, that it already holds
the result: a bare repeat of the payload reads as a fresh answer, and a model
that thinks it learned something new asks the same question again.
"""

from __future__ import annotations

import pytest

from core.agent.tool_cache import ToolCallCache, cache_key

pytestmark = pytest.mark.unit


def test_argument_order_does_not_change_the_key() -> None:
    """Providers serialise argument objects in whatever order they like."""
    assert cache_key("f", {"a": 1, "b": 2}) == cache_key("f", {"b": 2, "a": 1})


def test_nested_argument_order_does_not_change_the_key() -> None:
    left = cache_key("f", {"filter": {"service": "checkout", "env": "prod"}})
    right = cache_key("f", {"filter": {"env": "prod", "service": "checkout"}})

    assert left == right


def test_different_arguments_are_different_calls() -> None:
    assert cache_key("f", {"q": "a"}) != cache_key("f", {"q": "b"})


def test_the_capability_name_is_part_of_the_key() -> None:
    assert cache_key("f", {"q": "a"}) != cache_key("g", {"q": "a"})


def test_a_first_call_misses_and_the_second_hits() -> None:
    cache = ToolCallCache()

    assert cache.get("fixture_log_search", {"query": "x"}) is None
    cache.put("fixture_log_search", {"query": "x"}, content="412 matches")

    hit = cache.get("fixture_log_search", {"query": "x"})
    assert hit is not None
    assert hit.content == "412 matches"


def test_the_replay_text_tells_the_model_it_already_has_the_result() -> None:
    cache = ToolCallCache()
    stored = cache.put("fixture_log_search", {"query": "x"}, content="412 matches")

    replay = stored.replay_text()

    assert "already" in replay.lower()
    assert "412 matches" in replay
    assert "fixture_log_search" in replay


def test_a_cached_failure_is_replayed_as_a_failure() -> None:
    """Replaying a timeout as a success would have the model reason from a
    result that does not exist."""
    cache = ToolCallCache()
    stored = cache.put("fixture_log_search", {"query": "x"}, content="timed out", is_error=True)

    assert stored.is_error
    hit = cache.get("fixture_log_search", {"query": "x"})
    assert hit is not None and hit.is_error


def test_the_cache_is_bounded_by_entry_count() -> None:
    cache = ToolCallCache(max_entries=2, max_chars=1_000_000)

    cache.put("f", {"n": 1}, content="one")
    cache.put("f", {"n": 2}, content="two")
    cache.put("f", {"n": 3}, content="three")

    assert cache.get("f", {"n": 1}) is None, "the oldest entry is the one evicted"
    assert cache.get("f", {"n": 3}) is not None
    assert len(cache) == 2


def test_reading_an_entry_makes_it_the_most_recently_used() -> None:
    cache = ToolCallCache(max_entries=2, max_chars=1_000_000)
    cache.put("f", {"n": 1}, content="one")
    cache.put("f", {"n": 2}, content="two")

    cache.get("f", {"n": 1})
    cache.put("f", {"n": 3}, content="three")

    assert cache.get("f", {"n": 1}) is not None
    assert cache.get("f", {"n": 2}) is None


def test_the_cache_is_bounded_by_size_as_well_as_by_count() -> None:
    """A long run holding a hundred small results and one enormous one is the
    case an entry count alone does not bound."""
    cache = ToolCallCache(max_entries=100, max_chars=100)

    cache.put("f", {"n": 1}, content="x" * 60)
    cache.put("f", {"n": 2}, content="x" * 60)

    assert cache.get("f", {"n": 1}) is None
    assert cache.get("f", {"n": 2}) is not None


def test_an_entry_larger_than_the_whole_budget_is_not_stored() -> None:
    cache = ToolCallCache(max_entries=10, max_chars=100)

    cache.put("f", {"n": 1}, content="x" * 500)

    assert cache.get("f", {"n": 1}) is None
    assert len(cache) == 0


def test_evidence_identifiers_travel_with_the_cached_result() -> None:
    """A replayed call points at the evidence the first call produced rather
    than recording the same observation twice."""
    cache = ToolCallCache()
    cache.put("f", {"n": 1}, content="one", evidence_ids=("e1", "e2"))

    hit = cache.get("f", {"n": 1})
    assert hit is not None and hit.evidence_ids == ("e1", "e2")


def test_unserialisable_arguments_still_produce_a_stable_key() -> None:
    """A model can send anything; the cache must not be the thing that raises."""

    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    first = cache_key("f", {"thing": Opaque()})
    second = cache_key("f", {"thing": Opaque()})

    assert first == second
