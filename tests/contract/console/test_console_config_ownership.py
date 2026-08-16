"""Every configuration field has one screen that edits it, or is named as having none.

The raw configuration editor is being retired. That is only safe if parity is a
fact a check holds rather than an intention somebody had, because a field whose
single place of editing disappears is a capability regression nobody notices
until the day they need it.

So the console declares, per field, which Settings page owns it — and, just as
explicitly, which fields no page owns yet. These tests hold both lists against
the schema itself, which is the only thing that knows what fields exist.

**The failure that matters most is the one nobody wrote a test for.** A field
added to a section months from now, by somebody who has never read this file,
appears in neither list and fails here by name. That is the check turning an
absence into a build defect instead of a discovery made by an operator looking
for a setting that is not there.

**The unowned list only shrinks.** Nothing enforces that directly — a person
could add to it — but every entry is visible in review, and the count is
asserted below so that growing it is a deliberate edit to a number rather than
a line that slips in.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from platform.config_service.fields import declared_fields
from tests.contract.console.test_console_shell import (
    console_root,
    declared_settings_page_ids,
)

OWNERSHIP_MODULE: Final = console_root() / "src" / "shell" / "config-ownership.ts"

#: `{ path: 'a.b', page: 'settings-x' }` — whitespace-tolerant on purpose.
#:
#: The formatter wraps an entry whose path is long enough to pass the print
#: width, so a pattern anchored to one line silently stops seeing exactly the
#: entries with the longest paths. It did, and six fields read as unaccounted
#: for while their declaration sat in the file.
_OWNER: Final = re.compile(r"\{\s*path:\s*'([a-z0-9_.]+)',\s*page:\s*'([a-z-]+)',?\s*\}")

#: A bare quoted path, which is how the unowned list is written. Never wrapped,
#: because a lone string always fits, but read with the same tolerance.
_UNOWNED_ENTRY: Final = re.compile(r"^\s*'([a-z0-9_.]+)',$", re.MULTILINE)


def _source() -> str:
    return OWNERSHIP_MODULE.read_text(encoding="utf-8")


def _section(name: str) -> str:
    """Return the array literal `name` declares, so one list cannot read the other."""
    source = _source()
    start = source.index(f"export const {name}")
    end = source.index("];", start)
    return source[start:end]


def owned() -> dict[str, str]:
    """Return every field with an owning page, as path -> page id."""
    return dict(_OWNER.findall(_section("CONFIG_FIELD_OWNERS")))


def unowned() -> tuple[str, ...]:
    """Return every field the console admits no page owns yet."""
    return tuple(_UNOWNED_ENTRY.findall(_section("CONFIG_FIELDS_UNOWNED")))


def schema_fields() -> frozenset[str]:
    """Return every field the configuration schema declares."""
    return frozenset(field.path for field in declared_fields())


def test_the_parser_reads_both_lists_rather_than_silently_finding_nothing() -> None:
    """A regex that matched nothing would make every check below vacuously true."""
    assert len(owned()) > 0
    assert len(unowned()) > 0


def test_every_field_the_schema_declares_is_accounted_for() -> None:
    """The check the whole file exists for: a new field belongs to somebody, or fails here."""
    accounted = frozenset(owned()) | frozenset(unowned())
    missing = sorted(schema_fields() - accounted)
    assert not missing, (
        f"{len(missing)} configuration field(s) are in neither list of "
        f"console/src/shell/config-ownership.ts: {missing}. A field with no owning "
        f"screen and no admission that it has none is a setting an operator cannot "
        f"reach and nobody decided to drop."
    )


def test_nothing_is_claimed_that_the_schema_does_not_declare() -> None:
    """A path that outlived its field would be coverage on paper only."""
    accounted = frozenset(owned()) | frozenset(unowned())
    stale = sorted(accounted - schema_fields())
    assert not stale, (
        f"config-ownership.ts names {len(stale)} path(s) the schema no longer has: "
        f"{stale}. Remove them, or restore the fields they were written for."
    )


def test_no_field_is_both_owned_and_admitted_unowned() -> None:
    """The two lists answer the same question and may not disagree."""
    both = sorted(frozenset(owned()) & frozenset(unowned()))
    assert not both, f"claimed and disclaimed at once: {both}"


def test_every_owning_page_is_a_page_the_subnav_actually_has() -> None:
    """An owner nobody can navigate to is not an owner."""
    pages = declared_settings_page_ids()
    unknown = sorted({page for page in owned().values() if page not in pages})
    assert not unknown, (
        f"config-ownership.ts names {unknown} as owning pages, which the Settings "
        f"subnav in routes.ts does not declare."
    )


@pytest.mark.parametrize("path", sorted(unowned()))
def test_an_unowned_field_is_a_real_field_named_one_at_a_time(path: str) -> None:
    """Parametrised so the report names the field, not a set difference of a hundred."""
    assert path in schema_fields()


def test_the_size_of_the_gap_is_what_the_console_says_it_is() -> None:
    """The burndown, asserted so that closing or widening it is a deliberate edit.

    Not a threshold that quietly permits drift in one direction: this is the
    number that says how much of the schema still has no human screen, and it
    should move only when somebody builds one or the schema itself grows.
    """
    assert len(unowned()) == 101, (
        f"{len(unowned())} fields have no owning screen, not the 101 recorded here. "
        f"If a screen now owns some of them, update this number in the same change "
        f"that moved them out of CONFIG_FIELDS_UNOWNED."
    )
