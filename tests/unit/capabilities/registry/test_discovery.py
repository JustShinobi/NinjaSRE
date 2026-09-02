"""Adding a capability is creating one package, and discovery is why.

The claim under test is SC-003: a new capability appears in the catalogue with
zero edits to existing files. It is easy to state and easy to lose — the first
time somebody adds "just one line" to a list somewhere, it stops being true and
nothing fails.

So these tests build a package tree that no repository file mentions, point
discovery at it, and assert the capabilities come back.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from capabilities.registry.discovery import (
    DiscoveryError,
    default_skill_root,
    discover,
    discover_skills,
)
from config.constants.capabilities import CAPABILITY_TOOLS_PACKAGE
from core.capability.registered import RegisteredTool

pytestmark = pytest.mark.unit


TOOL_MODULE = '''
"""A vendor package that no repository file mentions."""

from __future__ import annotations

from core.capability import EvidenceType, SideEffectLevel, tool


@tool(
    name="{name}",
    display_name="Invented tool",
    description="Reads something from a vendor nobody has integrated.",
    evidence_source="invented",
    evidence_type=EvidenceType.LOG,
    side_effect_level=SideEffectLevel.READ,
    parallel_safe=True,
)
async def {name}(query: str) -> dict[str, int]:
    """Return a count for ``query``."""
    return {{"count": len(query)}}
'''

MANIFEST = """---
name: invented-methodology
description: How to investigate with the invented vendor's data.
domain: observability
directs_tools: [invented_read]
---

Start with statistics.
"""


@pytest.fixture
def importable(tmp_path: Path) -> Iterator[Path]:
    """Put ``tmp_path`` on the import path for the duration of one test."""
    sys.path.insert(0, str(tmp_path))
    try:
        yield tmp_path
    finally:
        sys.path.remove(str(tmp_path))
        for name in [module for module in sys.modules if module.startswith("invented")]:
            del sys.modules[name]


def _package(root: Path, name: str, *, tool_name: str = "invented_read") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text("", encoding="utf-8")
    (directory / "read.py").write_text(TOOL_MODULE.format(name=tool_name), encoding="utf-8")
    return directory


def test_a_new_package_appears_with_no_central_file_edited(importable: Path) -> None:
    _package(importable, "invented")

    catalogue = discover(tool_packages=("invented",), skill_roots=())

    assert [found.name for found in catalogue.tools] == ["invented_read"]


def test_discovery_reaches_modules_nested_below_the_root(importable: Path) -> None:
    package = _package(importable, "invented")
    nested = package / "deeper"
    nested.mkdir()
    (nested / "__init__.py").write_text("", encoding="utf-8")
    (nested / "more.py").write_text(TOOL_MODULE.format(name="invented_deep"), encoding="utf-8")

    catalogue = discover(tool_packages=("invented",), skill_roots=())

    assert {found.name for found in catalogue.tools} == {"invented_read", "invented_deep"}


def test_a_re_exported_tool_is_not_discovered_twice(importable: Path) -> None:
    """A package root re-exporting its tools is idiomatic and must stay free.

    Counting the re-export would produce a duplicate-name failure against one
    declaration, which is a build failure with no possible fix.
    """
    package = _package(importable, "invented")
    (package / "__init__.py").write_text(
        "from invented.read import invented_read\n\n__all__ = ['invented_read']\n",
        encoding="utf-8",
    )

    catalogue = discover(tool_packages=("invented",), skill_roots=())

    assert len(catalogue.tools) == 1


def test_a_missing_package_is_not_an_error(importable: Path) -> None:
    """Not every vendor ships tools, and the empty case is the starting state."""
    assert discover(tool_packages=("nothing_here_at_all",), skill_roots=()).tools == ()


def test_a_module_that_raises_on_import_fails_the_build_by_name(importable: Path) -> None:
    """A vendor silently absent from the catalogue is the worst outcome available."""
    package = _package(importable, "invented")
    (package / "broken.py").write_text("raise RuntimeError('bad module')\n", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="invented.broken"):
        discover(tool_packages=("invented",), skill_roots=())


def test_a_broken_declaration_fails_the_build_rather_than_being_skipped(
    importable: Path,
) -> None:
    package = _package(importable, "invented")
    (package / "undeclared.py").write_text(
        TOOL_MODULE.format(name="undeclared").replace(
            "    side_effect_level=SideEffectLevel.READ,\n", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(DiscoveryError, match="side_effect_level"):
        discover(tool_packages=("invented",), skill_roots=())


def test_skills_are_found_by_their_manifest(tmp_path: Path) -> None:
    directory = tmp_path / "invented-methodology"
    directory.mkdir()
    (directory / "SKILL.md").write_text(MANIFEST, encoding="utf-8")

    found = discover_skills([tmp_path])

    assert [skill.name for skill in found] == ["invented-methodology"]


def test_templates_are_not_capabilities(tmp_path: Path) -> None:
    """A template is text for a scaffold to copy, and is incomplete on purpose."""
    directory = tmp_path / "_templates" / "logstore"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(MANIFEST, encoding="utf-8")

    assert discover_skills([tmp_path]) == []


def test_a_malformed_manifest_fails_the_build_naming_the_file(tmp_path: Path) -> None:
    directory = tmp_path / "broken"
    directory.mkdir()
    (directory / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")

    with pytest.raises(DiscoveryError, match="SKILL.md"):
        discover_skills([tmp_path])


def test_discovery_is_ordered_so_a_catalogue_is_reproducible(tmp_path: Path) -> None:
    """Two builds of one repository must produce the same catalogue.

    Filesystem order is not guaranteed, and an unordered catalogue would make
    the determinism golden test pass or fail depending on the machine.
    """
    for name in ("zulu", "alpha", "mike"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            MANIFEST.replace("invented-methodology", name).replace(
                "directs_tools: [invented_read]", ""
            ),
            encoding="utf-8",
        )

    assert [skill.name for skill in discover_skills([tmp_path])] == ["alpha", "mike", "zulu"]


def test_the_shipped_skill_root_exists() -> None:
    """Discovery's default root has to be a real directory or nothing ships."""
    assert default_skill_root().is_dir()


def test_the_real_repository_discovers_without_error() -> None:
    catalogue = discover()

    assert catalogue.scanned_packages
    assert catalogue.scanned_skill_roots


def test_discovery_of_the_real_packages_is_walked_once_within_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A render asks for the catalogue several times; the packages are walked once.

    The walk is sixteen thousand modules through ``pkgutil`` and every skill
    manifest parsed from disk, and it happened on every request that needed
    the catalogue. A caller naming its own roots — every test above — is
    never served from the cache: it asked about a different tree.
    """
    from capabilities.registry import discovery

    discovery.forget_discovered()
    walks = {"packages": 0}
    real_walk = discovery._walk_package

    def counted(package: str) -> list[RegisteredTool]:
        walks["packages"] += 1
        return real_walk(package)

    monkeypatch.setattr(discovery, "_walk_package", counted)

    first = discovery.discover()
    walked = walks["packages"]
    second = discovery.discover()
    assert walked > 0
    assert walks["packages"] == walked
    assert second is first

    discovery.discover(tool_packages=(CAPABILITY_TOOLS_PACKAGE,), skill_roots=())
    assert walks["packages"] == walked + 1, "explicit roots are walked, never cached"

    discovery.forget_discovered()
    discovery.discover()
    assert walks["packages"] == 2 * walked + 1
