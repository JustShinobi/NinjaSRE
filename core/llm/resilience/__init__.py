"""Making a small model's mistakes cost a correction instead of an investigation.

A seven-billion-parameter model running on an operator's own hardware reaches the
same place a frontier model reaches, by a longer route. It emits a tool call as
prose, invents a parameter, omits a required one, asks for the same thing four
turns running. Each of those currently surfaces as an inscrutable failure
halfway through an incident.

This package is the layer that handles them. It sits between the provider
adapter and the runtime — one implementation rather than nine, and every repair
is a value the trace carries rather than something that happened inside an
adapter nobody can see into.

Three properties hold across all of it and none of them is optional.

**Nothing is invented.** Extraction and rejection only. There is exactly one
place a tool call is constructed, it verifies every argument value against the
model's own output, and a test walks the package's syntax tree to prove no
second place exists.

**Nothing branches on a provider.** Every mechanism keys off a behaviour that was
observed, so a frontier model that starts misbehaving is handled by this code
too. A test reads the package's source and fails on a provider identifier in it.

**A well-behaved model pays nothing.** Every mechanism is triggered by a detected
problem. A clean turn makes one call and comes back with no repairs.
"""

from __future__ import annotations

from core.llm.resilience.arguments import (
    ArgumentVerdict,
    check_arguments,
    correction_for,
    declared_parameters,
    required_parameters,
    signature,
)
from core.llm.resilience.bounds import RepairBudget
from core.llm.resilience.client import SESSION_METADATA_KEY, ResilientClient
from core.llm.resilience.extraction import (
    Extraction,
    InventedValueError,
    assemble_fragments,
    extract_tool_call,
    verified_arguments,
)
from core.llm.resilience.loops import RepetitionDetector, RepetitionVerdict
from core.llm.resilience.recorder import NO_RECORDER, NullRecorder, RepairRecorder

__all__ = [
    "NO_RECORDER",
    "SESSION_METADATA_KEY",
    "ArgumentVerdict",
    "Extraction",
    "InventedValueError",
    "NullRecorder",
    "RepairBudget",
    "RepairRecorder",
    "RepetitionDetector",
    "RepetitionVerdict",
    "ResilientClient",
    "assemble_fragments",
    "check_arguments",
    "correction_for",
    "declared_parameters",
    "extract_tool_call",
    "required_parameters",
    "signature",
    "verified_arguments",
]
