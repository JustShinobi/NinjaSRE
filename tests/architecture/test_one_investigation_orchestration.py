"""The six stages are what serves a request, and the loop is what one of them drives.

Two things in this repository assemble an investigation: the six-stage pipeline
and the runner that drives the canonical loop directly. For a long time only the
second was reachable from a composition root, and the first declared itself
dormant — which was the honest arrangement while nobody had decided, because
"reachable and unused" and "unreachable" are facts a reader cannot tell apart by
looking at the code.

The decision has been made, and it was forced by a screen. `/agent` has always
shown "the stages an investigation runs" — six of them, in order, with what each
consults — and a served investigation ran none of them: it ran a flat loop of
numbered turns. The console was describing a shape the deployment did not have,
which is the same class of defect as a panel naming a model no call reaches, and
the fix is not to soften the screen. The stages are the product's own account of
what an investigation *is*, so a served investigation runs them.

So the property inverts. The serving path composes the pipeline; the loop is
what the gather stage is built with, not a second orchestration beside it; and
no dormancy note survives, because a note saying "nothing serving builds this"
would now be false.
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

PIPELINE_BUILDER = "build_pipeline"
PIPELINE_MODULE = "core/pipeline/build.py"
SERVING_RUNNER = "ReActInvestigationRunner"
SERVING_RUNNER_MODULE = "gateway/runtime/investigator.py"


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


def _docstring_of(function: str, *, module: str) -> str:
    """Return ``function``'s docstring, read from the file rather than by importing."""
    tree = ast.parse((REPO_ROOT / module).read_text(encoding="utf-8"), filename=module)
    found = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == function
    )
    return ast.get_docstring(found) or ""


def test_the_serving_runner_is_constructed_by_serving_source() -> None:
    """The surface a request arrives at still has to be somebody's."""
    built = _call_sites(SERVING_RUNNER, excluding=SERVING_RUNNER_MODULE)

    assert built, (
        f"{SERVING_RUNNER} is constructed nowhere a request can reach. The path that "
        f"serves an investigation would then be nobody's."
    )


def test_the_staged_pipeline_is_what_a_served_investigation_runs() -> None:
    """The whole of the change, as one assertion.

    `/agent` names six stages and says an investigation runs them. It has to be
    true of a served run, not only of the corpus harness — otherwise the screen
    is describing the instrument and calling it the product.
    """
    built = _call_sites(PIPELINE_BUILDER, excluding=PIPELINE_MODULE)

    assert built, (
        f"{PIPELINE_BUILDER} is called from nowhere a request can reach, so a served "
        f"investigation runs no stages while `/agent` says it runs six. Compose it in "
        f"the serving path, or change what that screen claims."
    )


def test_no_dormancy_note_survives_the_composition() -> None:
    """A note saying nothing serving builds this would now be false.

    Kept as a test rather than left to a reviewer because the note was correct
    for as long as it stood, and the failure mode is somebody composing the
    pipeline and leaving the paragraph that says nobody has.
    """
    said = _docstring_of(PIPELINE_BUILDER, module=PIPELINE_MODULE).lower()

    assert "dormant" not in said, (
        f"{PIPELINE_MODULE} still calls itself dormant while the serving path builds "
        f"it. The note outlived what it described."
    )


def test_the_walk_would_notice_a_caller_disappearing() -> None:
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
