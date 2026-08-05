"""The check that keeps an experimental runtime out of a published number.

Article V allows alternative runtimes and allows exactly one of them to produce
an evaluation result. That is not a preference about code: the product's claim
is that trajectory quality is measured against golden trajectories and a
regression fails CI, and that comparison is only valid if every scenario ran the
same way. Split the suite across two runtimes and a score change could be the
model, the prompt, the memory, or the runtime — and nobody can tell which.

So the guard reads ``Runtime.is_canonical``, a declared property, rather than
matching a class name. A name check would pass the day somebody subclassed the
adapter, and it would pass silently.

The guard belongs in front of *entry points*, not in front of the loop. Running
the SDK adapter is a legitimate thing to do; running it and calling the result a
benchmark is not.
"""

from __future__ import annotations

import os

from config.constants.investigation import (
    DEFAULT_RUNTIME,
    NINJASRE_RUNTIME_ENV,
    RUNTIME_CANONICAL,
    SUPPORTED_RUNTIMES,
)
from core.agent.runtime_port import Runtime


class NonCanonicalRuntimeError(RuntimeError):
    """An evaluation or benchmark was invoked with a runtime that cannot publish.

    A distinct type rather than a bare ``RuntimeError`` so a harness can catch
    exactly this and report it as a configuration mistake — which is what it
    always is — instead of as a failed scenario.
    """


def selected_runtime_name() -> str:
    """Return the configured runtime identifier, defaulting to the canonical one.

    An unrecognised value reads as the default rather than raising. A typo in an
    environment variable must not silently select something else, and the guard
    below is what catches an intentional non-canonical selection anyway.
    """
    requested = os.environ.get(NINJASRE_RUNTIME_ENV, "").strip().lower()
    return requested if requested in SUPPORTED_RUNTIMES else DEFAULT_RUNTIME


def experimental_runtime_requested() -> bool:
    """Return whether the operator has explicitly asked for a non-canonical runtime."""
    return selected_runtime_name() != RUNTIME_CANONICAL


def require_canonical_runtime(runtime: Runtime, *, context: str) -> Runtime:
    """Return ``runtime``, or raise if it may not produce a published number.

    ``context`` names the entry point in the message — "the scenario benchmark",
    "the trajectory evaluation" — because the person who sees this failure is
    usually the person who set the environment variable, and the fix is to unset
    it for that command.
    """
    if runtime.is_canonical:
        return runtime

    raise NonCanonicalRuntimeError(
        f"{context} may only run on the canonical runtime, and {runtime.name!r} "
        f"declares itself experimental. Alternative runtimes exist so a team can "
        f"migrate; they never produce a published number, because a score that "
        f"could have moved because the runtime changed measures nothing. "
        f"Unset {NINJASRE_RUNTIME_ENV} for this command."
    )


__all__ = [
    "NonCanonicalRuntimeError",
    "experimental_runtime_requested",
    "require_canonical_runtime",
    "selected_runtime_name",
]
