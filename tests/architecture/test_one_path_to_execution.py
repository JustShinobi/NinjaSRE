"""There is one path from a proposed action to an execution, and it goes through here.

The whole autonomy feature is worth nothing if an actuator can reach a provider
directly. That is not a thing a review catches reliably — it catches the obvious
version and misses the one where somebody adds a helper — so it is a test over
the call graph, and it fails the build rather than a code review.

Three properties, and each one has a way it would be broken:

**The executor is reached from one place.** ``RemediationExecutor.execute`` is
what actually performs a change. A second caller would be a second path, and the
second path is the one nobody wired the policy engine into.

**The gate consults the resolver before it executes.** A gate that stopped
calling the resolver would still pass every test about approvals and would have
quietly turned autonomy off — or, worse, on.

**No capability performs its own remediation.** Every tool under
``capabilities/tools/remediation/`` returns a refusal that routes the call
through the gate. A tool body that called an applier would run a change with no
plan, no policy decision, and no audit line.

The walk is over the AST rather than over imports, because an import says a
module *could* call something and this is about whether anything *does*. The
allowed callers are named here, so widening the path is an edit to this file
with a reason beside it — which is the review conversation that should happen.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The packages a production change could be performed from. ``tools/`` and
#: ``tests/`` are outside it deliberately: a benchmark or a fixture standing up
#: an executor is not a path an incident takes.
SOURCE_PACKAGES = ("capabilities", "core", "gateway", "integrations", "platform", "surfaces")

#: The one function that performs a remediation, and the one place it may be
#: called from. Widening this pair is the change this test exists to make
#: deliberate.
EXECUTOR_METHOD = "execute"
EXECUTOR_ATTRIBUTE = "executor"
THE_ONE_CALLER = "platform/remediation/gating.py"

#: Where the decision is made, and what it must reach to make it.
THE_GATE = "platform/remediation/gating.py"
THE_RESOLVER_PACKAGE = "platform.autonomy"

#: What a remediation capability may not touch. Performing a change from a tool
#: body is exactly the bypass this feature exists to make impossible.
#:
#: ``ComponentRegistry`` is deliberately absent: it holds the four components a
#: capability *declares* and performs nothing, and the package's own module is
#: where a deployment reads which writes it can do at all.
FORBIDDEN_IN_CAPABILITIES = (
    "RemediationExecutor",
    "AutonomyGate",
)


def source_files() -> Iterator[Path]:
    """Yield every first-party module a change could be performed from."""
    for package in SOURCE_PACKAGES:
        yield from sorted((REPO_ROOT / package).rglob("*.py"))


def relative(path: Path) -> str:
    """Return ``path`` as the repository sees it, with forward slashes."""
    return path.relative_to(REPO_ROOT).as_posix()


def parsed(path: Path) -> ast.Module:
    """Return ``path``'s syntax tree."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def executor_calls(tree: ast.Module) -> list[ast.Call]:
    """Return every ``<something>.executor.execute(...)`` call in ``tree``."""
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        method = node.func
        if not isinstance(method, ast.Attribute) or method.attr != EXECUTOR_METHOD:
            continue
        owner = method.value
        if isinstance(owner, ast.Attribute) and owner.attr == EXECUTOR_ATTRIBUTE:
            found.append(node)
    return found


def test_the_executor_is_called_from_exactly_one_module() -> None:
    callers = {relative(path) for path in source_files() if executor_calls(parsed(path))}
    assert callers == {THE_ONE_CALLER}, (
        f"a remediation executor is reached from {sorted(callers)}. There is one path "
        f"from a proposed action to an execution and it is {THE_ONE_CALLER}; a second "
        f"caller is a path the policy engine was never wired into."
    )


def test_the_gate_consults_the_autonomy_resolver() -> None:
    tree = parsed(REPO_ROOT / THE_GATE)
    imported = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert any(name.startswith(THE_RESOLVER_PACKAGE) for name in imported), (
        f"{THE_GATE} reaches an executor and never reaches {THE_RESOLVER_PACKAGE}. "
        f"Every actuator consults the resolver; a gate that stopped would pass every "
        f"approval test it has and have silently changed what runs unattended."
    )


def test_the_gate_decides_before_it_executes() -> None:
    """Reaching the resolver is not enough; the decision has to gate the call."""
    from platform.remediation.gating import RemediationGate

    source = ast.parse(inspect_source(RemediationGate))
    decide = next(
        node
        for node in ast.walk(source)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "decide"
    )
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(decide)
        if isinstance(node, ast.Attribute | ast.Name)
    }
    assert "_autonomy" in names or "autonomy" in names, (
        "RemediationGate.decide does not consult the autonomy decision. Whatever it "
        "does instead, it is not the one path this feature is built around."
    )


def inspect_source(target: type) -> str:
    """Return ``target``'s source, dedented enough to parse on its own."""
    import inspect
    import textwrap

    return textwrap.dedent(inspect.getsource(target))


@pytest.mark.parametrize(
    "path",
    sorted((REPO_ROOT / "capabilities" / "tools" / "remediation").rglob("*.py")),
    ids=lambda path: path.relative_to(REPO_ROOT).as_posix(),
)
def test_no_remediation_capability_performs_its_own_change(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_IN_CAPABILITIES:
        assert forbidden not in text, (
            f"{relative(path)} names {forbidden}. A remediation capability proposes and "
            f"refuses; what performs the change is the gate, so that the plan, the policy "
            f"decision and the audit line all happen."
        )


def test_the_remediation_capabilities_are_all_refusals() -> None:
    """The property that makes the single path real rather than conventional."""
    from capabilities.tools.remediation import _base

    bodies = sorted((REPO_ROOT / "capabilities" / "tools" / "remediation").rglob("tool.py"))
    assert len(bodies) >= 7

    for path in bodies:
        text = path.read_text(encoding="utf-8")
        assert "_base.refuse(" in text, (
            f"{relative(path)} does not route through {_base.refuse.__name__}. Every "
            f"remediation tool refuses and lets the gate perform the change."
        )


def test_the_walk_would_notice_a_second_caller() -> None:
    """A check nobody has shown a failure to is a check that passes vacuously."""
    bypass = ast.parse(
        "async def sneaky(self):\n"
        "    return await self.executor.execute(action, plan=None, before=None)\n"
    )
    assert executor_calls(bypass), (
        "the AST walk does not recognise a direct executor call, so it would pass a "
        "module that bypassed the gate"
    )


def test_the_walk_ignores_something_that_merely_shares_the_name() -> None:
    """And a check that flags everything is one somebody switches off."""
    innocent = ast.parse("result = await self.plan.execute()\ncursor.execute(query)\n")
    assert not executor_calls(innocent)
