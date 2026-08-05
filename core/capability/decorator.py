"""Declaring a tool by decorating the function that is the tool.

This is the form roughly four capabilities in five will use, and its job is to
make the complete declaration — the one with the side-effect level, the
evidence contract, and the anti-examples — no more effort than an incomplete
one would have been. A framework where the safe thing is the tedious thing gets
the unsafe thing.

The decorated function is returned unchanged. It stays importable, callable,
and unit-testable as a plain function; the registration rides along as an
attribute, which is what discovery scans for. Wrapping the function instead
would mean every tool's own tests went through the framework, and a tool whose
tests only exercise the framework's path is a tool nobody has tested.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from core.capability.metadata import (
    EvidenceType,
    Requirements,
    RollbackPlanner,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.registered import build_registration, mark_capability
from core.capability.result import Evidence

_Declared = TypeVar("_Declared", bound=Callable[..., Any])


def tool(
    *,
    name: str,
    display_name: str,
    description: str,
    evidence_source: str,
    evidence_type: EvidenceType,
    side_effect_level: SideEffectLevel,
    parallel_safe: bool,
    domain: str = "",
    tags: Sequence[str] = (),
    use_cases: Sequence[str] = (),
    anti_examples: Sequence[str] = (),
    requires: Requirements = Requirements(),
    requires_approval: bool = False,
    approval_reason: str = "",
    rollback_plan: str = "",
    rollback_planner: RollbackPlanner | None = None,
    input_schema: Mapping[str, Any] | None = None,
    input_model: Any = None,
    output_schema: Mapping[str, Any] | None = None,
    output_model: Any = None,
    evidence_builder: Callable[[Any], tuple[Evidence, ...]] | None = None,
) -> Callable[[_Declared], _Declared]:
    """Return a decorator registering the function it is applied to as a tool.

    Every argument is keyword-only and the dangerous ones are required, so an
    incomplete declaration is a ``TypeError`` at import — which is to say, a
    build failure with the module and line in the traceback, rather than a tool
    that reaches the catalogue having promised nothing.
    """

    def register(declared: _Declared) -> _Declared:
        metadata = ToolMetadata(
            name=name,
            display_name=display_name,
            description=description,
            domain=domain,
            tags=tuple(tags),
            use_cases=tuple(use_cases),
            anti_examples=tuple(anti_examples),
            requires=requires,
            evidence_source=evidence_source,
            evidence_type=evidence_type,
            side_effect_level=side_effect_level,
            parallel_safe=parallel_safe,
            requires_approval=requires_approval,
            approval_reason=approval_reason,
            rollback_plan=rollback_plan,
            rollback_planner=rollback_planner,
        )

        registered = build_registration(
            metadata=metadata,
            call=declared,
            source_module=getattr(declared, "__module__", "<unknown>"),
            source_qualname=getattr(declared, "__qualname__", name),
            signature_source=declared,
            input_schema=input_schema,
            input_model=input_model,
            output_schema=output_schema,
            output_model=output_model,
            evidence_builder=evidence_builder,
        )
        mark_capability(declared, registered)
        return declared

    return register


__all__ = ["tool"]
