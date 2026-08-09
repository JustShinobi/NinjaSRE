"""Which model answers which kind of call, and the record of what answered what.

Not every call an investigation makes is the same call. Deciding which capability
to run next, summarising an incident, pulling structured fields out of prose,
embedding an episode and classifying an alert as noise are five jobs a
seven-billion-parameter model on an operator's own hardware does perfectly well.
Writing the root-cause synthesis at the end may be the one that is worth
something else. An operator who wants to make that split should be able to.

**This does not make a second runtime.** Article V is about the loop that produces
an evaluation number, and the loop is untouched: the same ReAct control flow runs,
the same bounds hold, and the only thing routing changes is which endpoint answers
a particular call. What Article V *does* require is that a published number
records what produced it, and that is what :class:`AttributionLedger` is for —
``model_set`` is the line a benchmark writes down beside its score.

**A task class is a role.** The config service already declares a closed set of
roles a deployment may bind a provider and model to; these six classes map onto
it rather than inventing a parallel vocabulary, so an operator configures models
in one place and there is one answer to "what is this deployment running on".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from config.constants.config_service import (
    MODEL_ROLE_EMBEDDING,
    MODEL_ROLE_EXTRACTION,
    MODEL_ROLE_INTAKE,
    MODEL_ROLE_INVESTIGATOR,
    MODEL_ROLE_SELECTION,
    MODEL_ROLE_SUMMARISATION,
)
from config.constants.llm import DEFAULT_MODEL_ID, DEFAULT_PROVIDER


class TaskClass(StrEnum):
    """What one model call is for.

    Closed, and each member is a call the runtime actually makes somewhere. A
    class nobody makes a call for would be a configuration field an operator
    could set and never see the effect of.
    """

    #: The investigation's own thinking: the ReAct turn.
    REASONING = "reasoning"
    #: Choosing which capability to run next, where that is asked separately.
    CAPABILITY_SELECTION = "capability_selection"
    #: Writing an incident or episode summary.
    SUMMARISATION = "summarisation"
    #: Pulling declared fields out of prose.
    EXTRACTION = "extraction"
    #: Turning text into a vector.
    EMBEDDING = "embedding"
    #: Deciding what something is — noise, a duplicate, a severity.
    CLASSIFICATION = "classification"


#: Which configured role each class resolves through. Reasoning shares the
#: investigator's role because it *is* the investigator's call, and
#: classification shares intake's because intake is the stage that classifies —
#: inventing separate roles for those two would give an operator two fields that
#: had to agree.
TASK_ROLES: Mapping[TaskClass, str] = {
    TaskClass.REASONING: MODEL_ROLE_INVESTIGATOR,
    TaskClass.CAPABILITY_SELECTION: MODEL_ROLE_SELECTION,
    TaskClass.SUMMARISATION: MODEL_ROLE_SUMMARISATION,
    TaskClass.EXTRACTION: MODEL_ROLE_EXTRACTION,
    TaskClass.EMBEDDING: MODEL_ROLE_EMBEDDING,
    TaskClass.CLASSIFICATION: MODEL_ROLE_INTAKE,
}


@runtime_checkable
class ModelSelectionSource(Protocol):
    """Somewhere a role's provider and model can be looked up."""

    def selection_for(self, role: str) -> tuple[str, str] | None:
        """Return the provider and model bound to ``role``, or ``None``."""


@dataclass(frozen=True, slots=True)
class TaskBinding:
    """What one task class resolved to, and whether anybody chose it.

    ``configured`` is not decoration. A deployment where five of six classes fell
    back to the default is one where somebody thought they had split their models
    and has not, and the difference is invisible from the provider and model alone.
    """

    task: TaskClass
    role: str
    provider_id: str
    model_id: str
    configured: bool = False

    @property
    def label(self) -> str:
        """Return the ``provider/model`` form a trace and a report both use."""
        return f"{self.provider_id}/{self.model_id}"


class TaskRouter:
    """Resolves a task class to a provider and model, falling back to the default.

    A class nobody configured resolves to the deployment default rather than
    failing, for the reason the config service gives about roles: an
    investigation that cannot start is worse than one that starts on the default
    model and records in its trace which model that was.
    """

    def __init__(
        self,
        *,
        source: ModelSelectionSource | None = None,
        default_provider: str = DEFAULT_PROVIDER,
        default_model: str = DEFAULT_MODEL_ID,
    ) -> None:
        self._source = source
        self._default = (default_provider, default_model)

    def binding_for(self, task: TaskClass) -> TaskBinding:
        """Return which provider and model ``task`` runs on."""
        role = TASK_ROLES[task]
        selection = self._source.selection_for(role) if self._source is not None else None
        provider_id, model_id = selection if selection is not None else self._default
        return TaskBinding(
            task=task,
            role=role,
            provider_id=provider_id,
            model_id=model_id,
            configured=selection is not None,
        )

    def bindings(self) -> tuple[TaskBinding, ...]:
        """Return every class's binding, in class order.

        What a surface prints when somebody asks what this deployment is running
        on, and what a benchmark records beside its number.
        """
        return tuple(self.binding_for(task) for task in TaskClass)


@dataclass(frozen=True, slots=True)
class ModelAttribution:
    """One output, and the model that produced it.

    ``output`` is a label rather than the output itself — "turn 3", "incident
    summary". The trace already holds what was produced; what it could not say
    before this is which model produced it, and that is the whole of what this
    adds.
    """

    task: str
    provider_id: str
    model_id: str
    output: str = ""

    @property
    def label(self) -> str:
        """Return the ``provider/model`` form."""
        return f"{self.provider_id}/{self.model_id}"

    def to_record(self) -> dict[str, str]:
        """Return a JSON-serialisable record of this attribution."""
        return {
            "task": self.task,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "output": self.output,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> ModelAttribution:
        """Return the attribution a stored record describes."""
        return cls(
            task=str(record["task"]),
            provider_id=str(record["provider_id"]),
            model_id=str(record["model_id"]),
            output=str(record.get("output", "")),
        )


@dataclass(slots=True)
class AttributionLedger:
    """Every model call one run made, by task and by model."""

    entries: list[ModelAttribution] = field(default_factory=list)

    def record(
        self,
        task: TaskClass | str,
        *,
        provider_id: str,
        model_id: str,
        output: str = "",
    ) -> ModelAttribution:
        """Note that ``model_id`` produced ``output`` for ``task``."""
        entry = ModelAttribution(
            task=task.value if isinstance(task, TaskClass) else str(task),
            provider_id=provider_id,
            model_id=model_id,
            output=output,
        )
        self.entries.append(entry)
        return entry

    def model_set(self) -> tuple[str, ...]:
        """Return the distinct models this run used, sorted.

        The line a published evaluation number carries beside it. Sorted and
        deduplicated so two runs that used the same models produce the same
        string whatever order they happened to call them in — a model set that
        depended on call order would make every comparison a diff of nothing.
        """
        return tuple(sorted({entry.label for entry in self.entries}))

    def for_task(self, task: TaskClass) -> tuple[ModelAttribution, ...]:
        """Return every attribution recorded for one task class."""
        return tuple(entry for entry in self.entries if entry.task == task.value)

    def to_record(self) -> list[dict[str, str]]:
        """Return a JSON-serialisable record of the ledger."""
        return [entry.to_record() for entry in self.entries]

    @classmethod
    def from_record(cls, record: Any) -> AttributionLedger:
        """Return the ledger a stored record describes."""
        return cls(entries=[ModelAttribution.from_record(item) for item in record or ()])


__all__ = [
    "TASK_ROLES",
    "AttributionLedger",
    "ModelAttribution",
    "ModelSelectionSource",
    "TaskBinding",
    "TaskClass",
    "TaskRouter",
]
