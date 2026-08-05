"""The reference is generated, and the check proves it has not drifted.

A hand-maintained reference for a catalogue this size is wrong from the first
tool whose side-effect level changes — and a reference claiming a tool is
read-only when it is not is worse than having none. So the page is generated
from the same metadata the scorer and the approval gate read, and `--check`
fails the build when the committed page and the declarations disagree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from capabilities.registry.api import catalogue_view
from capabilities.registry.catalogue import build_registry, reset_registry_cache
from tools.generate_capability_docs import DEFAULT_OUTPUT, main, render

pytestmark = pytest.mark.unit


@pytest.fixture
def page() -> str:
    reset_registry_cache()
    return render(catalogue_view(build_registry()))


def test_the_page_lists_both_kinds(page: str) -> None:
    assert "## Skills" in page
    assert "## Tools" in page


def test_a_write_tool_is_shown_with_its_approval_reason(page: str) -> None:
    """The field an operator reads before clicking approve."""
    assert "`restart_workload`" in page
    assert "**Approval:** required" in page


def test_a_side_effect_level_is_shown_with_what_it_means(page: str) -> None:
    """`write_irreversible` does not tell a reader what they are approving."""
    assert "cannot be undone" in page


def test_anti_examples_reach_the_reference(page: str) -> None:
    """They steer a human choosing a tool the same way they steer selection."""
    assert "**Not for:**" in page


def test_generation_is_deterministic(page: str) -> None:
    reset_registry_cache()

    assert render(catalogue_view(build_registry())) == page


def test_the_committed_page_is_up_to_date() -> None:
    """The check a build step runs. A stale reference is a reference that lies."""
    assert main(["--check"]) == 0


def test_check_reports_a_page_that_has_drifted(tmp_path: Path) -> None:
    stale = tmp_path / "capabilities.md"
    stale.write_text("# Capability reference\n\nOut of date.\n", encoding="utf-8")

    assert main(["--check", "--output", str(stale)]) == 1


def test_check_reports_a_page_that_was_never_generated(tmp_path: Path) -> None:
    assert main(["--check", "--output", str(tmp_path / "missing.md")]) == 1


def test_the_default_output_is_inside_the_repository() -> None:
    assert DEFAULT_OUTPUT.name == "capabilities.md"
    assert DEFAULT_OUTPUT.parent.name == "docs"
