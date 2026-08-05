"""Declaring a tool as a class, for the cases a function cannot cover.

A minority of tools need something a decorated function has nowhere to put: a
client held across calls, a paginator, a family of near-identical tools sharing
one implementation with different bindings. Forcing those into module-level
state is how a tool becomes order-dependent and stops being safe to run in
parallel with itself.

Registration happens at class creation, through the same builder the decorator
uses, so the record is identical and no downstream code can tell the two apart.
A class that declares no ``run`` of its own is treated as an abstract base and
skipped — otherwise a shared parent would register as a tool, and every child
would collide with it on the name it never meant to claim.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from core.capability.metadata import (
    EvidenceType,
    Requirements,
    RollbackPlanner,
    SideEffectLevel,
    ToolMetadata,
)
from core.capability.registered import build_registration, mark_capability
from core.capability.result import Evidence


class BaseTool:
    """Base class for a tool that needs more than a function can hold.

    Subclasses set the declaration as class attributes and implement ``run``.
    The required ones carry no value here, so omitting ``side_effect_level``
    raises at class creation rather than producing a tool that claims nothing.
    """

    name: ClassVar[str]
    display_name: ClassVar[str]
    description: ClassVar[str]
    evidence_source: ClassVar[str]
    evidence_type: ClassVar[EvidenceType]
    side_effect_level: ClassVar[SideEffectLevel]
    parallel_safe: ClassVar[bool]

    domain: ClassVar[str] = ""
    tags: ClassVar[Sequence[str]] = ()
    use_cases: ClassVar[Sequence[str]] = ()
    anti_examples: ClassVar[Sequence[str]] = ()
    requires: ClassVar[Requirements] = Requirements()
    requires_approval: ClassVar[bool] = False
    approval_reason: ClassVar[str] = ""
    rollback_plan: ClassVar[str] = ""
    rollback_planner: ClassVar[RollbackPlanner | None] = None
    input_schema: ClassVar[Mapping[str, Any] | None] = None
    input_model: ClassVar[Any] = None
    output_schema: ClassVar[Mapping[str, Any] | None] = None
    output_model: ClassVar[Any] = None
    evidence_builder: ClassVar[Callable[[Any], tuple[Evidence, ...]] | None] = None

    #: Set on a subclass that exists to be inherited from rather than called.
    abstract: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        if cls.abstract or "run" not in vars(cls):
            return

        metadata = ToolMetadata(
            name=cls.name,
            display_name=cls.display_name,
            description=cls.description,
            domain=cls.domain,
            tags=tuple(cls.tags),
            use_cases=tuple(cls.use_cases),
            anti_examples=tuple(cls.anti_examples),
            requires=cls.requires,
            evidence_source=cls.evidence_source,
            evidence_type=cls.evidence_type,
            side_effect_level=cls.side_effect_level,
            parallel_safe=cls.parallel_safe,
            requires_approval=cls.requires_approval,
            approval_reason=cls.approval_reason,
            rollback_plan=cls.rollback_plan,
            rollback_planner=cls.rollback_planner,
        )

        registered = build_registration(
            metadata=metadata,
            # A fresh instance per call. Sharing one across a turn would let two
            # parallel-safe calls to the same tool see each other's state, which
            # is the exact bug ``parallel_safe`` is a promise about.
            call=lambda **arguments: cls().run(**arguments),
            source_module=cls.__module__,
            source_qualname=cls.__qualname__,
            signature_source=cls.run,
            skip_first=True,
            input_schema=cls.input_schema,
            input_model=cls.input_model,
            output_schema=cls.output_schema,
            output_model=cls.output_model,
            evidence_builder=cls.evidence_builder,
        )
        mark_capability(cls, registered)

    async def run(self, **arguments: Any) -> Any:
        """Return this tool's result for ``arguments``.

        Subclasses override with the real, named parameters — the schema is
        derived from that signature, so ``**arguments`` here would produce a
        tool with no declared inputs.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement run()")


__all__ = ["BaseTool"]
