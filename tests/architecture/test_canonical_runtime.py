"""Exactly one runtime may publish a number, and the build says which.

The unit tests cover the adapter that exists. This covers the one somebody adds
next: an alternative runtime that forgot to declare itself experimental would
pass every test it shipped with and quietly contaminate the first benchmark run
after it landed.

So the rule is structural rather than per-adapter. Everything in
``core/agent/adapters/`` answers ``False`` to ``is_canonical`` and lists what it
cannot enforce, and this walks the package to check it.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

import pytest

import core.agent.adapters as adapters
from core.agent.guard import NonCanonicalRuntimeError, require_canonical_runtime
from core.agent.react_loop import ReActLoop
from core.agent.runtime_port import Runtime

pytestmark = pytest.mark.architecture


def _adapter_modules() -> list[ModuleType]:
    """Return every module under ``core/agent/adapters/``."""
    return [
        importlib.import_module(f"{adapters.__name__}.{found.name}")
        for found in pkgutil.iter_modules(adapters.__path__)
    ]


def _runtime_classes(module: ModuleType) -> list[type]:
    """Return the runtime implementations ``module`` declares."""
    return [
        member
        for _, member in inspect.getmembers(module, inspect.isclass)
        if member.__module__ == module.__name__
        and hasattr(member, "is_canonical")
        and hasattr(member, "run")
    ]


def test_the_adapters_package_holds_at_least_one_runtime() -> None:
    """A check that walks an empty package proves nothing, quietly."""
    found = [cls for module in _adapter_modules() for cls in _runtime_classes(module)]

    assert found, "core/agent/adapters/ declares no runtime — has the package moved?"


def test_every_adapter_declares_itself_experimental() -> None:
    for module in _adapter_modules():
        for cls in _runtime_classes(module):
            assert cls().is_canonical is False, (
                f"{cls.__module__}.{cls.__qualname__} claims to be canonical. "
                "Exactly one runtime may publish a number and it is the first-party loop."
            )


def test_every_adapter_lists_what_it_cannot_enforce() -> None:
    """A gap nobody wrote down is a gap an operator discovers during an
    incident, which is the worst possible time to find out that approval
    gating was not running."""
    for module in _adapter_modules():
        listed = getattr(module, "UNENFORCEABLE_GUARDRAILS", None)
        assert listed, f"{module.__name__} does not declare UNENFORCEABLE_GUARDRAILS"
        assert all(isinstance(entry, str) and entry for entry in listed)


def test_every_adapter_is_marked_experimental_in_its_docstring() -> None:
    for module in _adapter_modules():
        assert module.__doc__ is not None, f"{module.__name__} has no module docstring"
        assert "EXPERIMENTAL" in module.__doc__, (
            f"{module.__name__} does not say it is experimental where a reader will see it"
        )


def test_every_adapter_is_refused_by_the_benchmark_guard() -> None:
    for module in _adapter_modules():
        for cls in _runtime_classes(module):
            with pytest.raises(NonCanonicalRuntimeError):
                require_canonical_runtime(cls(), context="the scenario benchmark")


def test_the_first_party_loop_is_the_canonical_runtime() -> None:
    from tests.unit.core.agent.conftest import ScriptedLLM, text_turn

    loop = ReActLoop(llm=ScriptedLLM([text_turn("done")]))

    assert isinstance(loop, Runtime)
    assert loop.is_canonical is True
