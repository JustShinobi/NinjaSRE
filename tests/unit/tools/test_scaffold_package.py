"""A new package starts out compliant.

FR-019. The tier a package belongs to decides what it may import, where its
constants live, and whether CI will let it merge. A scaffold that gets those
right by default is the difference between the architecture being enforced and
the architecture being remembered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.scaffold_package import (
    TIERS,
    ScaffoldError,
    follow_up_steps,
    scaffold_package,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    return tmp_path


# --- What it creates ---------------------------------------------------------


def test_creates_the_four_artefacts(repo: Path) -> None:
    created = scaffold_package(repo, "reporting", tier=3)

    assert (repo / "reporting" / "__init__.py").is_file()
    assert (repo / "reporting" / "AGENTS.md").is_file()
    assert (repo / "tests" / "unit" / "reporting").is_dir()
    assert set(created) >= {
        repo / "reporting" / "__init__.py",
        repo / "reporting" / "AGENTS.md",
        repo / "tests" / "unit" / "reporting",
    }


def test_the_module_docstring_states_the_tier_and_its_rules(repo: Path) -> None:
    scaffold_package(repo, "reporting", tier=2)

    docstring = (repo / "reporting" / "__init__.py").read_text(encoding="utf-8")

    assert "Tier 2" in docstring
    assert "surfaces" in docstring, "the docstring must name what the tier may not import"


def test_the_generated_package_is_importable_python(repo: Path) -> None:
    """A scaffold that does not parse is worse than no scaffold."""
    import ast

    scaffold_package(repo, "reporting", tier=3)

    ast.parse((repo / "reporting" / "__init__.py").read_text(encoding="utf-8"))


def test_the_agents_file_states_the_tier_rules(repo: Path) -> None:
    """The generated file is a starting point, not an empty one."""
    scaffold_package(repo, "reporting", tier=2)

    agents = (repo / "reporting" / "AGENTS.md").read_text(encoding="utf-8")

    assert "Tier 2" in agents
    assert "surfaces" in agents
    assert "AGENTS.md" in agents, "it must point back at the repository-wide rules"


def test_the_leaf_tier_is_told_it_imports_nothing(repo: Path) -> None:
    scaffold_package(repo, "settings", tier=4)

    docstring = (repo / "settings" / "__init__.py").read_text(encoding="utf-8")

    assert "no other first-party package" in docstring


# --- What it refuses ---------------------------------------------------------


def test_refuses_an_existing_package(repo: Path) -> None:
    scaffold_package(repo, "reporting", tier=3)

    with pytest.raises(ScaffoldError, match="already exists"):
        scaffold_package(repo, "reporting", tier=3)


@pytest.mark.parametrize("tier", [0, 5, -1])
def test_refuses_a_tier_that_does_not_exist(repo: Path, tier: int) -> None:
    with pytest.raises(ScaffoldError, match="tier"):
        scaffold_package(repo, "reporting", tier=tier)


@pytest.mark.parametrize(
    "name",
    ["Reporting", "my-package", "9lives", "my package", "", "tests"],
    ids=["capitalised", "hyphenated", "leading-digit", "spaced", "empty", "reserved"],
)
def test_refuses_a_name_that_is_not_a_usable_package(repo: Path, name: str) -> None:
    with pytest.raises(ScaffoldError):
        scaffold_package(repo, name, tier=3)


def test_a_refused_scaffold_leaves_nothing_behind(repo: Path) -> None:
    """A half-created package is worse than a clear error."""
    with pytest.raises(ScaffoldError):
        scaffold_package(repo, "Reporting", tier=3)

    assert list(repo.iterdir()) == [repo / "tests"]


# --- Dry run -----------------------------------------------------------------


def test_a_dry_run_reports_without_creating(repo: Path) -> None:
    planned = scaffold_package(repo, "reporting", tier=3, dry_run=True)

    assert planned
    assert not (repo / "reporting").exists()


# --- The follow-up it cannot do for you --------------------------------------


def test_names_the_steps_a_scaffold_must_not_automate(repo: Path) -> None:
    """A new package is unconstrained until it is in the contracts.

    The tool refuses to rewrite .importlinter on the author's behalf — deciding
    which boundaries a package sits behind is a judgement, and a silent edit to
    the file CI depends on is how that judgement gets skipped.
    """
    steps = follow_up_steps("reporting", tier=2)

    joined = "\n".join(steps)
    assert ".importlinter" in joined
    assert "AGENTS.md" in joined
    assert "test_contract_coverage.py" in joined


def test_every_tier_is_described() -> None:
    assert sorted(TIERS) == [1, 2, 3, 4]
    for tier in TIERS.values():
        assert tier.may_import
        assert tier.summary
