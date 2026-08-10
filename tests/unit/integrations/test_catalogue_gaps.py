"""An honest gap is fine. A silent one is not.

The parity check walks the packages that exist, so a vendor nobody wrote is a
vendor nobody is told about — the catalogue reports full parity and an operator
discovers the absence while looking for it. These assertions are what make the
omission a declaration.
"""

from __future__ import annotations

import pytest

from integrations._catalogue.discovery import vendor_packages
from integrations._catalogue.gaps import (
    NOT_BUILT,
    UNREACHABLE,
    GapCause,
    gap_for,
    gaps,
    is_recorded,
    not_built,
    unreachable,
)

pytestmark = pytest.mark.unit


def test_every_gap_names_the_vendor_the_reason_and_what_would_change_it() -> None:
    """A reason nobody can act on is a shrug with a schema."""
    assert gaps()
    for gap in gaps():
        assert gap.integration.strip()
        assert gap.reason.strip()
        assert gap.what_would_change_it.strip()


def test_no_recorded_gap_is_also_an_installed_integration() -> None:
    """A vendor that reached parity and is still listed as a gap is a stale record."""
    installed = set(vendor_packages())

    overlap = sorted(installed & {gap.integration for gap in gaps()})

    assert not overlap, f"{overlap} are installed and still recorded as unreachable"


def test_a_gap_is_looked_up_by_name() -> None:
    found = gap_for(UNREACHABLE[0].integration)

    assert found is not None
    assert found.integration == UNREACHABLE[0].integration


def test_a_vendor_nobody_recorded_is_not_reported_as_a_gap() -> None:
    """Otherwise every typo would come back as a documented omission."""
    assert gap_for("not-a-vendor") is None
    assert not is_recorded("not-a-vendor")


def test_each_gap_is_recorded_once() -> None:
    names = [gap.integration for gap in gaps()]

    assert len(names) == len(set(names))


def test_a_gap_renders_the_line_the_console_and_the_docs_both_show() -> None:
    record = gaps()[0].to_record()

    assert set(record) == {
        "integration",
        "display_name",
        "category",
        "cause",
        "reason",
        "resolution",
    }


def test_the_two_causes_are_kept_apart() -> None:
    """ "This cannot be built" and "this was decided against" are different
    sentences, and an operator weighing whether to ask for one needs to know
    which they are reading."""
    assert gaps() == UNREACHABLE + NOT_BUILT
    assert all(gap.cause is GapCause.UNREACHABLE for gap in unreachable())
    assert all(gap.cause is GapCause.NOT_BUILT for gap in not_built())


def test_the_two_observability_decisions_are_recorded_rather_than_forgotten() -> None:
    """Acceptance 5. Gatus and NetBox are absences somebody chose, and a chosen
    absence with the reasoning written down is what stops the same conversation
    happening from scratch every quarter."""
    recorded = {gap.integration: gap for gap in not_built()}

    assert set(recorded) == {"gatus", "netbox"}
    for gap in recorded.values():
        assert gap.reason.strip()
        assert gap.what_would_change_it.strip()
