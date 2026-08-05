"""The one record every declaration style collapses into.

A tool can be written as a decorated function, as a class, or bridged in from a
remote protocol server, and downstream nothing may depend on which. This is
where that promise is kept: three declaration paths, one ``RegisteredTool``,
and selection, approval, telemetry, and the console read only this.

Two behaviours live here rather than in the caller, because getting either
wrong is silent.

**Arguments are checked against the schema before the call.** A model that
misspells a parameter would otherwise have it dropped by ``**kwargs`` or
swallowed by a permissive signature, and the tool would run against something
other than what the model asked for — producing a plausible answer to a
question nobody asked.

**Exceptions become results.** Every path out of ``invoke`` returns a
``CapabilityResult``. An exception escaping into the loop ends the turn and
takes the trace with it, so the interesting failures are exactly the ones that
would leave no record.
"""

from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants.capabilities import CAPABILITY_MARKER_ATTRIBUTE
from core.capability.metadata import ToolMetadata
from core.capability.result import CapabilityErrorClass, CapabilityResult, Evidence
from core.capability.schema import derive_input_schema, derive_output_schema

#: Standard exceptions whose meaning is unambiguous, mapped to the class the
#: loop reasons about. Anything else is ``INTERNAL`` — guessing at an unfamiliar
#: exception is how a permanent failure gets retried until the budget is gone.
_EXCEPTION_CLASSES: tuple[tuple[type[BaseException], CapabilityErrorClass], ...] = (
    (TimeoutError, CapabilityErrorClass.TIMEOUT),
    (PermissionError, CapabilityErrorClass.PERMISSION_DENIED),
    (FileNotFoundError, CapabilityErrorClass.NOT_FOUND),
    (ConnectionError, CapabilityErrorClass.UPSTREAM_ERROR),
    (NotImplementedError, CapabilityErrorClass.UNAVAILABLE),
    (TypeError, CapabilityErrorClass.INVALID_ARGUMENTS),
    (ValueError, CapabilityErrorClass.INVALID_ARGUMENTS),
)


def classify_exception(error: BaseException) -> CapabilityErrorClass:
    """Return the class ``error`` belongs to, defaulting to ``INTERNAL``."""
    for exception_type, classification in _EXCEPTION_CLASSES:
        if isinstance(error, exception_type):
            return classification
    return CapabilityErrorClass.INTERNAL


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """One declared tool, with everything the catalogue and the loop need.

    ``source_module`` and ``source_qualname`` are not diagnostics. A duplicate
    name has to name both offenders for the failure to be actionable, and by
    the time the registry notices, the only thing it holds is two of these.
    """

    metadata: ToolMetadata
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    call: Callable[..., Any]
    source_module: str
    source_qualname: str
    evidence_builder: Callable[[Any], tuple[Evidence, ...]] | None = field(default=None)

    @property
    def name(self) -> str:
        """Return the name the model calls this tool by."""
        return self.metadata.name

    @property
    def source(self) -> str:
        """Return where the declaration was written, for a failure that names it."""
        return f"{self.source_module}.{self.source_qualname}"

    def argument_violations(self, arguments: Mapping[str, Any]) -> tuple[str, ...]:
        """Return every way ``arguments`` disagrees with the declared schema.

        Presence and spelling only. Type checking belongs to the tool, which
        knows what it meant; a missing or misspelled name is what nobody
        notices.
        """
        properties = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            return ()

        violations: list[str] = []
        missing = [name for name in required if name not in arguments]
        if missing:
            violations.append(f"missing required argument(s): {', '.join(sorted(missing))}")

        unknown = [name for name in arguments if name not in properties]
        if unknown and self.input_schema.get("additionalProperties") is not True:
            violations.append(f"unknown argument(s): {', '.join(sorted(unknown))}")

        return tuple(violations)

    async def invoke(self, arguments: Mapping[str, Any]) -> CapabilityResult:
        """Return the outcome of one call. Never raises, whatever the tool does."""
        started = time.perf_counter()

        violations = self.argument_violations(arguments)
        if violations:
            return CapabilityResult.failed(
                self.name,
                CapabilityErrorClass.INVALID_ARGUMENTS,
                "; ".join(violations),
                duration_seconds=time.perf_counter() - started,
            )

        try:
            produced = self.call(**arguments)
            if inspect.isawaitable(produced):
                produced = await produced
        except Exception as error:  # noqa: BLE001 — FR-017 is exactly this catch
            return CapabilityResult.failed(
                self.name,
                classify_exception(error),
                f"{self.name} failed: {type(error).__name__}",
                detail=str(error),
                duration_seconds=time.perf_counter() - started,
            )

        duration = time.perf_counter() - started

        if isinstance(produced, CapabilityResult):
            # A tool that classified its own failure knows more about it than
            # any wrapper could. Re-wrapping would flatten that back to success.
            return produced

        evidence = self.evidence_builder(produced) if self.evidence_builder else ()
        return CapabilityResult.ok(
            self.name, value=produced, evidence=evidence, duration_seconds=duration
        )


def build_registration(
    *,
    metadata: ToolMetadata,
    call: Callable[..., Any],
    source_module: str,
    source_qualname: str,
    signature_source: Any = None,
    skip_first: bool = False,
    input_schema: Mapping[str, Any] | None = None,
    input_model: Any = None,
    output_schema: Mapping[str, Any] | None = None,
    output_model: Any = None,
    evidence_builder: Callable[[Any], tuple[Evidence, ...]] | None = None,
) -> RegisteredTool:
    """Return the registration for one declaration, whichever style wrote it.

    Both declaration styles funnel through here, which is what makes "the same
    tool written two ways produces the same record" a property of the code
    rather than a thing two implementations have to keep agreeing on.
    """
    return RegisteredTool(
        metadata=metadata,
        input_schema=derive_input_schema(
            label=metadata.name,
            function=signature_source,
            input_schema=input_schema,
            input_model=input_model,
            skip_first=skip_first,
        ),
        output_schema=derive_output_schema(
            label=metadata.name,
            function=signature_source,
            output_schema=output_schema,
            output_model=output_model,
        ),
        call=call,
        source_module=source_module,
        source_qualname=source_qualname,
        evidence_builder=evidence_builder,
    )


def mark_capability(target: Any, registered: RegisteredTool) -> None:
    """Attach ``registered`` to ``target`` where discovery will find it."""
    setattr(target, CAPABILITY_MARKER_ATTRIBUTE, registered)


def capability_marker(target: Any) -> RegisteredTool | None:
    """Return the registration attached to ``target``, or ``None``.

    Read with ``vars`` rather than ``getattr`` for classes, so a subclass that
    declared nothing does not appear to be a second copy of its parent's tool —
    which is how one declaration becomes a duplicate-name build failure.
    """
    if isinstance(target, type):
        found = vars(target).get(CAPABILITY_MARKER_ATTRIBUTE)
    else:
        found = getattr(target, CAPABILITY_MARKER_ATTRIBUTE, None)
    return found if isinstance(found, RegisteredTool) else None


__all__ = [
    "RegisteredTool",
    "build_registration",
    "capability_marker",
    "classify_exception",
    "mark_capability",
]
