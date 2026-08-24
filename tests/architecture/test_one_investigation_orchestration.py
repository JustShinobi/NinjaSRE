"""One investigation orchestration serves production, and the other says it does not.

Two things in this repository assemble an investigation: the six-stage pipeline
and the runner that drives the canonical loop directly. Both are written, both
are tested, and only one of them is reachable from a composition root. That is
allowed — a mechanism kept for an instrument rather than for serving is a real
thing to have — but it is only allowed when the module says so, because
"reachable and unused" and "unreachable" are facts a reader cannot tell apart by
looking at the code.

So the property here is not "delete one". It is: exactly one is composed by the
path that serves a request, the other declares itself dormant, and the
declaration names what does build it. A dormancy note that says only "nothing
uses this" leaves the next reader to search the tree; naming the caller turns
the search into a sentence.
"""

from __future__ import annotations

import ast

import pytest

from config.constants.paths import REPO_ROOT

pytestmark = pytest.mark.architecture

#: Source a request can reach. ``tests/`` is outside it on purpose: the corpus
#: harness is a real caller and is deliberately not a serving one.
SERVING_PACKAGES = (
    "capabilities",
    "config",
    "core",
    "gateway",
    "integrations",
    "platform",
    "surfaces",
)

#: The two assemblers, and where each is declared.
PIPELINE_BUILDER = "build_pipeline"
PIPELINE_MODULE = "core/pipeline/build.py"
SERVING_RUNNER = "ReActInvestigationRunner"
SERVING_RUNNER_MODULE = "gateway/runtime/investigator.py"

#: What the dormant module has to name, so a reader does not have to search.
NAMES_ITS_CALLER = ("harness", "corpus")


def _call_sites(name: str, *, excluding: str) -> list[str]:
    """Return ``package/module.py:line`` for every call of ``name`` in serving source."""
    found: list[str] = []
    for package in SERVING_PACKAGES:
        for path in (REPO_ROOT / package).rglob("*.py"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative == excluding:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == name
                ):
                    found.append(f"{relative}:{node.lineno}")
    return found


def _constructions(name: str, *, excluding: str) -> list[str]:
    """Return every place serving source constructs ``name``."""
    return _call_sites(name, excluding=excluding)


def test_the_serving_runner_is_constructed_by_serving_source() -> None:
    """The canonical path: something a request reaches builds this one."""
    built = _constructions(SERVING_RUNNER, excluding=SERVING_RUNNER_MODULE)

    assert built, (
        f"{SERVING_RUNNER} is constructed nowhere a request can reach. The path that "
        f"serves an investigation would then be nobody's."
    )


def test_the_staged_pipeline_has_no_serving_caller() -> None:
    """Not a complaint — the fact the declaration below has to state."""
    built = _call_sites(PIPELINE_BUILDER, excluding=PIPELINE_MODULE)

    assert built == [], (
        f"{PIPELINE_BUILDER} is now called from {built}. Two orchestrations reachable "
        f"from serving is the duplication this test exists to keep decided; if that is "
        f"the intent, the dormancy note below is the thing to remove."
    )


def _docstring_of(function: str, *, module: str) -> str:
    """Return ``function``'s docstring, read from the file rather than by importing."""
    tree = ast.parse((REPO_ROOT / module).read_text(encoding="utf-8"), filename=module)
    found = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == function
    )
    return ast.get_docstring(found) or ""


def test_the_dormant_orchestration_says_so_of_itself() -> None:
    said = _docstring_of(PIPELINE_BUILDER, module=PIPELINE_MODULE).lower()

    assert "dormant" in said, (
        f"{PIPELINE_MODULE} assembles an investigation that no serving path builds and "
        f"does not say so. A reader cannot tell that apart from a path that is used."
    )


def test_the_dormancy_note_names_what_builds_it() -> None:
    """ "Nothing uses this" leaves a search; naming the caller ends it."""
    said = _docstring_of(PIPELINE_BUILDER, module=PIPELINE_MODULE).lower()

    assert any(word in said for word in NAMES_ITS_CALLER), (
        f"the dormancy note in {PIPELINE_MODULE} does not name what does construct the "
        f"pipeline. It is built by the evaluation harness that runs the scenario "
        f"corpus, and saying which turns a search into a sentence."
    )


def test_the_note_does_not_read_as_dead_code() -> None:
    """Dormant is about composition, not about worth."""
    said = _docstring_of(PIPELINE_BUILDER, module=PIPELINE_MODULE).lower()

    for wrong in ("dead", "unused", "deprecated"):
        assert wrong not in said, (
            f"the dormancy note calls the staged pipeline {wrong!r}. It has a caller and "
            f"a purpose; what it does not have is a place in the serving path."
        )


def test_the_walk_would_notice_a_caller_appearing() -> None:
    """A check nobody has shown a failure to is a check that passes vacuously."""
    tree = ast.parse("pipeline = build_pipeline(llm=llm, runtime=loop)\n")
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == PIPELINE_BUILDER
    ]
    assert calls, "the walk does not recognise a plain call, so it would pass anything"
