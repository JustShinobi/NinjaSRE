"""What a change is, what a window is, and what a change source promises.

The three assertions worth stating before any source exists.

**A window is a pair of instants and a ceiling**, not a duration somebody
subtracts at a call site. A tool that accepted "hours" and did the arithmetic
itself would be one where the ceiling is enforced in whichever caller remembered
to, and the caller that forgot would be the one reading a year of history into a
context window.

**Applied and committed are one record with a field**, not two kinds of thing. A
commit nobody applied did not change the cluster, and the distinction is what
separates correlation from coincidence — but it is a property of the change, so
a caller that ignores the field gets a superset rather than a different answer.

**The bounds are named constants.** Asserted against the constant rather than
against a literal, because the test exists to prove the bound is enforced and
not to freeze the number somebody measured it into.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.constants.changes import (
    DEFAULT_CHANGE_WINDOW_HOURS,
    MAX_CHANGE_MESSAGE_CHARS,
    MAX_CHANGE_WINDOW_HOURS,
    MAX_CHANGES_PER_WINDOW,
    MAX_PATHS_PER_CHANGE,
)
from platform.changes.errors import ChangeWindowInvalid
from platform.changes.models import Change, ChangeWindow
from platform.changes.port import ChangeSource

pytestmark = pytest.mark.unit

NOW = datetime(2026, 6, 1, 14, 32, tzinfo=UTC)


def test_a_window_ending_now_reaches_back_the_default_when_nobody_names_one() -> None:
    window = ChangeWindow.ending(NOW)

    assert window.end == NOW
    assert window.start == NOW - timedelta(hours=DEFAULT_CHANGE_WINDOW_HOURS)
    assert window.hours == pytest.approx(DEFAULT_CHANGE_WINDOW_HOURS)


def test_a_window_wider_than_the_ceiling_is_refused_naming_the_constant() -> None:
    with pytest.raises(ChangeWindowInvalid) as refusal:
        ChangeWindow.ending(NOW, hours=MAX_CHANGE_WINDOW_HOURS + 1)

    assert "MAX_CHANGE_WINDOW_HOURS" in str(refusal.value)


def test_a_window_that_ends_before_it_starts_is_refused_rather_than_reversed() -> None:
    with pytest.raises(ChangeWindowInvalid):
        ChangeWindow(start=NOW, end=NOW - timedelta(hours=1))


def test_a_window_is_half_open_so_two_adjacent_windows_share_no_change() -> None:
    window = ChangeWindow(start=NOW - timedelta(hours=1), end=NOW)

    assert window.contains(NOW - timedelta(hours=1)) is True
    assert window.contains(NOW - timedelta(minutes=1)) is True
    assert window.contains(NOW) is False


def test_a_change_says_whether_it_reached_the_cluster_or_only_the_repository() -> None:
    committed = Change(
        change_id="a1b2c3d",
        occurred_at=NOW,
        author="erik",
        message="fix(services)!: Decommission CT109",
        paths=("services/monitoring/stack/values.yaml",),
        source="infra_apply",
    )
    applied = Change(
        change_id="a1b2c3d",
        occurred_at=NOW,
        author="erik",
        message="fix(services)!: Decommission CT109",
        paths=("services/monitoring/stack/values.yaml",),
        source="infra_apply",
        component="monitoring",
        applied_at=NOW + timedelta(minutes=4),
    )

    assert committed.applied is False
    assert applied.applied is True


def test_a_message_past_the_ceiling_is_cut_and_says_so() -> None:
    change = Change(
        change_id="a1b2c3d",
        occurred_at=NOW,
        author="erik",
        message="x" * (MAX_CHANGE_MESSAGE_CHARS + 200),
        paths=(),
        source="infra_apply",
    )

    assert len(change.message) == MAX_CHANGE_MESSAGE_CHARS
    assert change.message_truncated is True


def test_more_paths_than_one_change_may_carry_are_cut_and_the_count_is_kept() -> None:
    touched = tuple(
        f"services/monitoring/file{index}.tf" for index in range(MAX_PATHS_PER_CHANGE + 5)
    )

    change = Change(
        change_id="a1b2c3d",
        occurred_at=NOW,
        author="erik",
        message="feat(monitoring): move the stack",
        paths=touched,
        source="infra_apply",
    )

    assert len(change.paths) == MAX_PATHS_PER_CHANGE
    assert change.paths_seen == len(touched)
    assert change.paths_truncated is True


def test_a_change_record_has_nowhere_to_put_a_diff() -> None:
    # Structural rather than documentary. Judging whether a change was *right*
    # is out of scope, and the way to keep it out is for the record to have no
    # field a diff could arrive in.
    assert not any("diff" in name or "patch" in name or "body" in name for name in Change.__slots__)


def test_a_change_source_is_satisfied_by_shape_rather_than_by_inheritance() -> None:
    class Recorded:
        """A source that answers from a list, as every fixture source does."""

        name = "recorded"

        async def changes_in(
            self,
            window: ChangeWindow,
            *,
            limit: int = MAX_CHANGES_PER_WINDOW,
        ) -> tuple[Change, ...]:
            """Return nothing, which is a legitimate answer."""
            del window, limit
            return ()

    assert isinstance(Recorded(), ChangeSource)


def test_something_that_answers_no_window_is_not_a_change_source() -> None:
    class Halfway:
        name = "halfway"

    assert not isinstance(Halfway(), ChangeSource)
