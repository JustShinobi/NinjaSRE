"""The whole of configuration, in one type.

Six sections and nothing else. That closure is what makes the rest of the
feature possible: a reference to a capability can be validated because there is
one field it can appear in, and the console can render a form because the shape
is knowable without asking a vendor.

**A node with no configuration resolves to a working system.** Every field has a
default sourced from ``config/constants/`` or ``config/prompts/``, so
``RootConfig()`` is a deployment that investigates incidents. Configuration is
what a team changes, never what makes the platform start.

**Adding a field is a schema change.** Not a new key in a document — a typed
field on the owning section, with a default, which the console then renders and
validation then enforces. That is the whole argument against free-form
configuration: an untyped second codebase that nothing validates and nobody can
document.

**``read`` never raises, and that costs it a salvage pass.** Validation refused
bad documents at the write, so anything reaching the read path predates a schema
change or bypassed the service — and refusing to resolve would be refusing to
investigate an incident. Pydantic validates a document as a whole, so one bad
field would take every good one with it; ``read`` therefore prunes the fields
that failed and revalidates, leaving the rest of the team's configuration
intact. If even that fails, the shipped defaults are a working system.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from platform.config_service import paths
from platform.config_service.errors import ConfigInvalid, FieldError
from platform.config_service.schema.agents import AgentsConfig, ModelsConfig
from platform.config_service.schema.capabilities import CapabilitiesConfig
from platform.config_service.schema.integrations import IntegrationsConfig
from platform.config_service.schema.policies import PoliciesConfig
from platform.config_service.schema.surfaces import SurfacesConfig
from platform.config_service.schema.types import ConfigSection, field_errors

#: The six sections. The tier table of configuration: a key that is not one of
#: these is not configuration, whatever it is.
ROOT_SECTIONS: tuple[str, ...] = (
    "agents",
    "models",
    "capabilities",
    "integrations",
    "policies",
    "surfaces",
)


class RootConfig(ConfigSection):
    """One node's effective configuration, typed."""

    agents: AgentsConfig = AgentsConfig()
    models: ModelsConfig = ModelsConfig()
    capabilities: CapabilitiesConfig = CapabilitiesConfig()
    integrations: IntegrationsConfig = IntegrationsConfig()
    policies: PoliciesConfig = PoliciesConfig()
    surfaces: SurfacesConfig = SurfacesConfig()

    @classmethod
    def of(cls, values: Mapping[str, Any]) -> RootConfig:
        """Return the configuration ``values`` describes, or raise naming the fields.

        Raises ``ConfigInvalid`` carrying every problem rather than the first.
        """
        config, errors = cls.read(values)
        if errors:
            raise ConfigInvalid(errors)
        return config

    @classmethod
    def read(cls, values: Mapping[str, Any]) -> tuple[RootConfig, tuple[FieldError, ...]]:
        """Return the configuration ``values`` describes and everything wrong with it.

        The non-raising form, for callers that have more validation to run
        before deciding — cross-referencing capability names, scanning for
        secrets — and want to report all of it at once, and for the resolution
        path, which must produce a configuration whatever it was handed.
        """
        try:
            return cls.model_validate(values), ()
        except ValidationError as invalid:
            errors = field_errors(invalid)
        return cls._salvaged(values, errors), errors

    @classmethod
    def _salvaged(cls, values: Mapping[str, Any], errors: Sequence[FieldError]) -> RootConfig:
        """Return the most of ``values`` that validates, with the rest defaulted."""
        pruned = _without(values, [error.path for error in errors])
        try:
            return cls.model_validate(pruned)
        except ValidationError:
            return cls()

    def capability_references(self) -> tuple[str, ...]:
        """Return every capability name this configuration mentions.

        Across all the places one can appear — the allow-list, the deny-list,
        the parameter overrides, a sub-agent's capability list, and the
        autonomous allow-list — because a dangling reference in any of them is
        the same silent misconfiguration.
        """
        named = list(self.capabilities.referenced_names())
        for subagent in self.agents.subagents:
            named.extend(subagent.capabilities)
        named.extend(self.policies.approvals.autonomous_capabilities)
        return tuple(dict.fromkeys(named))

    def integration_references(self) -> tuple[str, ...]:
        """Return every integration name this configuration mentions."""
        return self.integrations.referenced_names()

    def trace_summary(self) -> Mapping[str, object]:
        """Return what a run trace records about the configuration it ran under."""
        return {
            "config_models": {
                role: f"{self.models.for_role(role).provider}/{self.models.for_role(role).model}"
                for role in self.models.bound_roles()
            },
            "config_subagents": [each.name for each in self.agents.enabled_subagents()],
            **self.policies.ablation_summary(),
        }


def section_fields() -> Mapping[str, Sequence[str]]:
    """Return the declared field names per section, for the console's form.

    Exposed as data rather than reflected over at the call site: the console is
    tier 1 and this is tier 3, and a form that reached into the models directly
    would be a form that renders whatever a refactor left behind.
    """
    return {name: tuple(_section_model(name).model_fields) for name in ROOT_SECTIONS}


def _section_model(name: str) -> type[ConfigSection]:
    """Return the model backing section ``name``."""
    annotation = RootConfig.model_fields[name].annotation
    if not isinstance(annotation, type) or not issubclass(annotation, ConfigSection):
        raise TypeError(f"the {name!r} section is not a configuration section")
    return annotation


def _without(values: Mapping[str, Any], failed: Sequence[str]) -> dict[str, Any]:
    """Return ``values`` with each path in ``failed`` removed.

    A path inside a list — ``agents.subagents[0].name`` — drops the whole entry
    rather than the field, because a half-removed sub-agent is a sub-agent that
    fails validation for a second reason and salvages nothing.
    """
    pruned = deepcopy(dict(values))
    for path in failed:
        _drop(pruned, paths.split(path.replace("[", ".").replace("]", "")))
    return pruned


def _drop(cursor: Any, segments: Sequence[str]) -> None:
    """Remove the value ``segments`` names from ``cursor``, in place."""
    if not segments:
        return
    head, rest = segments[0], segments[1:]

    if isinstance(cursor, list):
        if not head.isdigit() or int(head) >= len(cursor):
            return
        if rest:
            # Anything wrong inside an entry condemns the entry: the fields that
            # remain would fail on their own.
            del cursor[int(head)]
        else:
            del cursor[int(head)]
        return

    if not isinstance(cursor, dict) or head not in cursor:
        return
    if rest:
        _drop(cursor[head], rest)
    else:
        del cursor[head]


__all__ = ["ROOT_SECTIONS", "RootConfig", "section_fields"]
