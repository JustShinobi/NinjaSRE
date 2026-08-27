"""There is one fictional deployment, and one way into it.

Two structural rules, both of the slow kind — nothing breaks today when either
is violated, and eighteen months later there are two datasets that disagree and
a demo that looks nothing like the screenshots.

**One deployment.** The mock serves the dataset to the console; a demo seeder
loads the same records into a real database. A second invented estate living
beside the seeder would drift from this one immediately.

**One way in.** Everything that writes a fixture goes through the anonymisation
pipeline: the gateway capture, the infrastructure projection, an answer somebody
recorded from a terminal, and the scenario builder. A second route is always
added for a good reason by somebody in a hurry, and a finding that arrives that
way is a finding the scan never saw.

Checked structurally rather than by review, because a review happens once and a
check happens on every commit.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tools.mockplane.seed import DEMONSTRATION_ORGANISATION, records_for_seeding

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKPLANE = REPO_ROOT / "tools" / "mockplane"
FIXTURES = REPO_ROOT / "fixtures"

#: Where the fictional deployment may be named. Everywhere else naming it is a
#: second copy of it.
MAY_NAME_THE_DEPLOYMENT = (MOCKPLANE, FIXTURES, REPO_ROOT / "tests")

#: Trees this check does not walk: the tooling's own caches, the virtual
#: environment, and local reference material that is never committed.
#: Directory names this sweep never walks into.
#:
#: Three kinds, and the last two keep being forgotten. Caches and installed
#: dependencies hold nobody's decisions. Agent worktrees hold a whole second
#: copy of this repository, so a sweep that walked one would find every file
#: twice and call the duplicate a second deployment — which it did, on every
#: run of the gate while a parallel slot was in flight. And a browser run
#: leaves its traces and screenshots behind: those are a recording of the
#: dataset being served, not a second declaration of it, and the run that
#: produced them is the same one this rule exists to protect.
SKIPPED = frozenset(
    {
        ".git",
        ".claude",
        ".venv",
        "__pycache__",
        "_research",
        "node_modules",
        "test-results",
        "playwright-report",
    }
)


def _is_wave_directory(name: str) -> bool:
    """Return whether ``name`` is a wave's planning directory.

    Matched by shape rather than listed by name: the list was three waves out
    of date the first time anybody looked at it, and a wave that has to be
    added to a test before the test tells the truth is a test that lies
    quietly in between.
    """
    return name == "specs" or _WAVE.fullmatch(name) is not None


_WAVE = re.compile(r"specs_v\d+")


def _searchable(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in suffixes
        and not SKIPPED.intersection(path.relative_to(root).parts)
        and not any(_is_wave_directory(part) for part in path.relative_to(root).parts)
    )


@pytest.mark.sweep
def test_exactly_one_fictional_deployment_exists_in_the_repository() -> None:
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _searchable(REPO_ROOT, (".py", ".json", ".md", ".yaml", ".yml"))
        if DEMONSTRATION_ORGANISATION in path.read_text(encoding="utf-8", errors="ignore")
        and not any(path.is_relative_to(allowed) for allowed in MAY_NAME_THE_DEPLOYMENT)
    ]
    assert not offenders, (
        "the fictional deployment is named outside the dataset that defines it, which is "
        f"how a second one starts: {offenders}"
    )


@pytest.mark.sweep
def test_only_one_directory_holds_scenario_fixtures() -> None:
    trees = [
        path.parent.parent
        for path in _searchable(REPO_ROOT, (".json",))
        if path.parent.parent.name == "scenarios"
    ]
    assert set(trees) <= {FIXTURES / "scenarios"}, (
        f"a second fixture tree exists: {sorted(set(trees))}"
    )


def test_the_demo_seeder_reads_this_dataset_and_defines_none_of_its_own() -> None:
    records = records_for_seeding()
    assert records, "the seeder found nothing to load"
    slugs = {record.slug for record in records}
    assert {"runs", "estate-resources", "incidents", "principals"} <= slugs


def test_every_seeded_record_carries_the_demonstration_label() -> None:
    from tools.mockplane.seed import DEMONSTRATION_LABEL_FIELD

    for record in records_for_seeding()[:50]:
        assert record.labelled()[DEMONSTRATION_LABEL_FIELD] is True


def test_the_seeder_loads_state_rather_than_the_answers_to_writes() -> None:
    # A run that has just been started is not in a freshly seeded database, and
    # loading the answer to the write that started it would put a run in the
    # trace that nothing ever ran.
    slugs = {record.slug for record in records_for_seeding()}
    assert "investigation-start" not in slugs
    assert "token-create" not in slugs


# --- One way into the dataset ------------------------------------------------------


def _modules_calling(name: str) -> set[Path]:
    found: set[Path] = set()
    for path in sorted(MOCKPLANE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                called = (
                    target.id
                    if isinstance(target, ast.Name)
                    else target.attr
                    if isinstance(target, ast.Attribute)
                    else ""
                )
                if called == name:
                    found.add(path.relative_to(REPO_ROOT))
    return found


def test_only_the_builder_writes_a_fixture_file() -> None:
    assert _modules_calling("write_fixture") == {Path("tools/mockplane/dataset/build.py")}, (
        "something other than the scenario builder writes into the fixture tree"
    )


def test_the_builder_writes_only_what_the_pipeline_produced() -> None:
    source = (MOCKPLANE / "dataset" / "build.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    writer = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "write_scenario"
    )
    calls = {
        node.func.id
        for node in ast.walk(writer)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "processed_for" in calls, (
        "write_scenario no longer goes through the anonymisation pipeline"
    )


def test_the_pipeline_is_the_only_thing_that_anonymises() -> None:
    # Renaming and shifting are applied from exactly one place, and the order
    # is not adjustable: credentials go before renaming, and the shift goes last
    # over the whole set at once. A second caller is a second order.
    inside = Path("tools/mockplane/anonymise")
    for step in ("anonymise", "shift"):
        outside = {path for path in _modules_calling(step) if not path.is_relative_to(inside)}
        assert not outside, f"{step} is applied outside the pipeline, by {outside}"
    assert Path("tools/mockplane/anonymise/pipeline.py") in _modules_calling("anonymise")


def test_the_capture_and_the_builder_both_end_at_the_same_function() -> None:
    from tools.mockplane.anonymise import pipeline

    assert callable(pipeline.process)
    builder = (MOCKPLANE / "dataset" / "build.py").read_text(encoding="utf-8")
    assert "from tools.mockplane.anonymise.pipeline import" in builder
