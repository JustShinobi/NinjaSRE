"""The close-task helper accepts both legacy and wave-prefixed branches."""

from __future__ import annotations

import pytest

from tools.close_task_branch import CloseTaskError, parse_task_branch

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("branch", "prefix", "slug"),
    (
        ("feat/001-foundation", "", "001-foundation"),
        ("feat/v5-001-foundation", "v5-", "001-foundation"),
        ("feat/specs-v5-010-settings", "specs-v5-", "010-settings"),
    ),
)
def test_parse_task_branch_preserves_an_optional_wave_prefix(
    branch: str, prefix: str, slug: str
) -> None:
    """The next branch can preserve the naming convention of its wave."""
    assert parse_task_branch(branch) == (prefix, slug)


def test_parse_task_branch_rejects_a_branch_without_a_spec_slug() -> None:
    """A normal feature branch must not be closed as a spec task."""
    with pytest.raises(CloseTaskError, match=r"expected feat/\[wave-\]NNN-slug"):
        parse_task_branch("feat/console-hover-nav-and-brand")
