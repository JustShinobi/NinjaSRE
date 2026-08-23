"""The short, URL-safe address every incident is reached by, derived — not chosen.

An incident's primary key is a composite the correlation window and the
alerting source produced for it, never meant to be typed, pasted, or shown as
a name: colons, an ``@``, and a fractional-second timestamp, well past the
width a table row or an address bar should carry. The public address is a
digest of that key, prefixed so the edge can tell it apart from a run's own
address without a database round trip, and derived — rather than random — so
a migration backfilling an old row and the code raising a new one land on the
same value for the same internal key without either inventing one.
"""

from __future__ import annotations

import pytest

from platform.persistence.ports.incident_store import (
    INCIDENT_PUBLIC_ID_PREFIX,
    is_public_incident_id,
    public_incident_id,
)

pytestmark = pytest.mark.unit

RESERVED = frozenset(":@+/?#[]%")


def test_the_same_internal_key_always_derives_the_same_public_address() -> None:
    internal = "alert:alertmanager:9f2c4a1b8e7d3506@2026-08-22T23:43:23.303208+00:00"

    first = public_incident_id(internal)
    second = public_incident_id(internal)

    assert first == second, "a migration and the code that runs after it must agree by construction"


def test_two_distinct_internal_keys_derive_distinct_public_addresses() -> None:
    left = public_incident_id("alert:alertmanager:aaaa@2026-08-22T23:43:23.303208+00:00")
    right = public_incident_id("alert:alertmanager:bbbb@2026-08-22T23:43:23.303208+00:00")

    assert left != right


def test_the_public_address_carries_the_declared_prefix() -> None:
    address = public_incident_id("alert:alertmanager:cccc@2026-08-22T23:43:23.303208+00:00")

    assert address.startswith(INCIDENT_PUBLIC_ID_PREFIX)


def test_the_public_address_contains_no_character_a_url_segment_must_escape() -> None:
    address = public_incident_id("alert:alertmanager:dddd@2026-08-22T23:43:23.303208+00:00")

    found = RESERVED & set(address)
    assert not found, f"{address!r} carries reserved character(s) {sorted(found)}"


def test_the_public_address_is_short_enough_for_a_table_row() -> None:
    address = public_incident_id("alert:alertmanager:eeee@2026-08-22T23:43:23.303208+00:00")

    # Twenty characters: the four-character prefix plus sixteen hexadecimal
    # digest characters, the same width `_bounded` already uses in this same
    # module and for the same reason — collision stops being something that
    # happens, and the identifier stays short.
    assert len(address) == 20, address


def test_is_public_incident_id_recognises_the_grammar_it_derives() -> None:
    address = public_incident_id("alert:alertmanager:ffff@2026-08-22T23:43:23.303208+00:00")

    assert is_public_incident_id(address)


def test_is_public_incident_id_rejects_the_internal_key_it_was_derived_from() -> None:
    """The edge decides which column to read by shape alone. An internal key —
    still valid to paste into the address bar, still resolvable — must not be
    mistaken for the public grammar, or the edge would send it down the wrong
    lookup.
    """
    internal = "alert:alertmanager:9999@2026-08-22T23:43:23.303208+00:00"

    assert not is_public_incident_id(internal)


def test_is_public_incident_id_rejects_a_run_id() -> None:
    """A run's own address is thirty-two lowercase hexadecimal characters with
    no prefix — a different shape the edge must not confuse with an
    incident's.
    """
    assert not is_public_incident_id("a" * 32)


def test_is_public_incident_id_rejects_the_bare_prefix() -> None:
    assert not is_public_incident_id(INCIDENT_PUBLIC_ID_PREFIX)


def test_is_public_incident_id_rejects_uppercase_digest_characters() -> None:
    address = public_incident_id("alert:alertmanager:0000@2026-08-22T23:43:23.303208+00:00")

    assert not is_public_incident_id(address.upper())


__all__: list[str] = []
