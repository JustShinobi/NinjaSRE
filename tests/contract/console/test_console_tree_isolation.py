"""These tests share one console checkout, so they share one worker.

The lock in this directory's ``conftest`` is per process. ``guard_the_tree``
takes it exclusively and calls ``pytest.exit`` when it cannot, because two runs
seeding and unseeding the same paths interleave into a state neither one's
cleanup repairs.

Under ``pytest-xdist`` every worker is its own process with its own session, so
a run that spread these tests across workers would have each worker after the
first refuse to start — and the suite would fail with "another run is already
writing into the console checkout", which describes nothing that is actually
wrong. Grouping them onto one worker is what lets the lock and parallelism
coexist.

That grouping is applied by a collection hook, which is the kind of thing that
disappears in a refactor without anybody noticing until CI breaks in a way that
reads as a mystery. So it is asserted here, from inside the directory it
protects: this test is itself a collected item, and it checks its own mark.
"""

from __future__ import annotations

import pytest

from tests.contract.console.conftest import CONSOLE_TREE_GROUP

pytestmark = pytest.mark.contract


def test_every_test_in_this_directory_is_pinned_to_one_worker(
    request: pytest.FixtureRequest,
) -> None:
    """The mark is on this very item, which is the only proof that collection applied it."""
    marker = request.node.get_closest_marker("xdist_group")

    assert marker is not None, (
        "this test carries no xdist group, so the console suites can be split "
        "across workers and the tree lock will stop the run"
    )
    assert marker.args == (CONSOLE_TREE_GROUP,)
