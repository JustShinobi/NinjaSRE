"""SC-003: adding a capability creates one package and edits nothing.

The claim is easy to state and quietly easy to lose. It survives exactly as
long as nobody adds "just one line" to a list somewhere — so the test that
protects it takes a snapshot of every existing file, scaffolds a capability,
and asserts the snapshot is unchanged. Not that the *intended* files were left
alone: that nothing was touched.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from capabilities.registry.discovery import discover
from tools.scaffold_capability import (
    ScaffoldError,
    remaining_work,
    scaffold_capability,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def repository(tmp_path: Path) -> Iterator[Path]:
    """Return a miniature repository the scaffold can write into.

    The ``capabilities`` package is unbound for the duration, so an import of
    ``capabilities.tools.<domain>`` resolves against this tree rather than the
    real one — a scaffolded package cannot be discovered while the package it
    belongs to is already bound to the repository's own directory.
    """
    for package in ("capabilities/tools", "integrations"):
        directory = tmp_path / package
        directory.mkdir(parents=True)
        (directory / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "capabilities" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "capabilities" / "skills").mkdir()
    (tmp_path / "tests" / "contract").mkdir(parents=True)

    shadowed = {
        name: module
        for name, module in sys.modules.items()
        if name == "capabilities" or name.startswith("capabilities.")
    }
    for name in shadowed:
        del sys.modules[name]

    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path.remove(str(tmp_path))
        for name in [
            name
            for name in sys.modules
            if name == "capabilities" or name.startswith("capabilities.")
        ]:
            del sys.modules[name]
        sys.modules.update(shadowed)


def _snapshot(root: Path) -> dict[str, str]:
    """Return a digest of every file under ``root``."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_a_scaffold_writes_three_files(repository: Path) -> None:
    written = scaffold_capability(repository, "invented_read", "observability")

    assert len(written) == 3
    assert all(path.exists() for path in written)


def test_a_scaffold_edits_no_existing_file(repository: Path) -> None:
    """SC-003, asserted against every file rather than the expected ones."""
    before = _snapshot(repository)

    scaffold_capability(repository, "invented_read", "observability")

    after = _snapshot(repository)
    unchanged = {name: digest for name, digest in after.items() if name in before}

    assert unchanged == before


def test_a_scaffolded_tool_is_discovered_with_no_registry_edit(repository: Path) -> None:
    scaffold_capability(repository, "invented_read", "observability")

    catalogue = discover(
        tool_packages=("capabilities.tools.observability",),
        skill_roots=(repository / "capabilities" / "skills",),
    )

    assert "invented_read" in {found.name for found in catalogue.tools}


def test_a_scaffolded_capability_declares_a_side_effect_level(repository: Path) -> None:
    """A scaffold that produced an incomplete declaration would fail the build."""
    written = scaffold_capability(repository, "invented_read", "observability")
    source = written[0].read_text(encoding="utf-8")

    assert "side_effect_level=" in source
    assert "anti_examples=" in source


def test_a_scaffolded_skill_binds_to_the_tool_it_shipped_with(repository: Path) -> None:
    written = scaffold_capability(repository, "invented_read", "observability")
    manifest = written[1].read_text(encoding="utf-8")

    assert "directs_tools:" in manifest
    assert "invented_read" in manifest


def test_a_vendor_capability_lands_in_that_vendor_s_package(repository: Path) -> None:
    written = scaffold_capability(
        repository, "datadog_log_statistics", "observability", vendor="datadog"
    )

    assert written[0] == repository / "integrations" / "datadog" / "tools" / (
        "datadog_log_statistics.py"
    )
    assert written[1] == repository / "capabilities" / "skills" / "observability-datadog" / (
        "SKILL.md"
    )


def test_a_utility_tool_may_ship_without_a_skill(repository: Path) -> None:
    written = scaffold_capability(repository, "invented_read", "system", skill=False)

    assert len(written) == 2
    assert not (repository / "capabilities" / "skills" / "system").exists()


def test_a_name_a_model_cannot_emit_is_refused(repository: Path) -> None:
    with pytest.raises(ScaffoldError, match="symbol"):
        scaffold_capability(repository, "Invented-Read", "observability")


def test_a_scaffold_over_an_existing_capability_is_refused(repository: Path) -> None:
    scaffold_capability(repository, "invented_read", "observability")

    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_capability(repository, "invented_read", "observability")


def test_a_refused_scaffold_leaves_nothing_behind(repository: Path) -> None:
    before = _snapshot(repository)

    with pytest.raises(ScaffoldError):
        scaffold_capability(repository, "Invented-Read", "observability")

    assert _snapshot(repository) == before


def test_a_dry_run_reports_without_writing(repository: Path) -> None:
    before = _snapshot(repository)

    written = scaffold_capability(repository, "invented_read", "observability", dry_run=True)

    assert len(written) == 3
    assert _snapshot(repository) == before


def test_the_scaffold_names_what_it_deliberately_cannot_write() -> None:
    """The judgement calls have to be visible, or the TODOs ship."""
    steps = " ".join(remaining_work()).lower()

    assert "side-effect level" in steps
    assert "anti-example" in steps
