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
field here, with a default, which the console then renders and validation then
enforces. That is the whole argument against free-form configuration: an untyped
second codebase that nothing validates and nobody can document.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from platform.config_service.errors import ConfigInvalid, FieldError
from platform.config_service.schema.agents import AgentsConfig, ModelsConfig
from platform.config_service.schema.capabilities import CapabilitiesConfig
from platform.config_service.schema.integrations import IntegrationsConfig
from platform.config_service.schema.policies import PoliciesConfig
from platform.config_service.schema.reader import Reader
from platform.config_service.schema.surfaces import SurfacesConfig

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


@dataclass(frozen=True, slots=True)
class RootConfig:
    """One node's effective configuration, typed."""

    agents: AgentsConfig = field(default_factory=AgentsConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)
    integrations: IntegrationsConfig = field(default_factory=IntegrationsConfig)
    policies: PoliciesConfig = field(default_factory=PoliciesConfig)
    surfaces: SurfacesConfig = field(default_factory=SurfacesConfig)

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
        secrets — and want to report all of it at once.
        """
        reader = Reader(values=values)
        reader.close(ROOT_SECTIONS)
        config = cls(
            agents=AgentsConfig.of(reader.section("agents")),
            models=ModelsConfig.of(reader.section("models")),
            capabilities=CapabilitiesConfig.of(reader.section("capabilities")),
            integrations=IntegrationsConfig.of(reader.section("integrations")),
            policies=PoliciesConfig.of(reader.section("policies")),
            surfaces=SurfacesConfig.of(reader.section("surfaces")),
        )
        return config, tuple(reader.errors)

    def capability_references(self) -> tuple[str, ...]:
        """Return every capability name this configuration mentions.

        Across all three places one can appear — the allow-list, the deny-list,
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
    tier 1 and this is tier 3, and a form that read the dataclasses directly
    would be a form that renders whatever a refactor left behind.
    """
    from platform.config_service.schema.agents import AGENTS_FIELDS, MODELS_FIELDS
    from platform.config_service.schema.capabilities import CAPABILITIES_FIELDS
    from platform.config_service.schema.integrations import INTEGRATIONS_FIELDS
    from platform.config_service.schema.policies import POLICIES_FIELDS
    from platform.config_service.schema.surfaces import SURFACES_FIELDS

    return {
        "agents": AGENTS_FIELDS,
        "models": MODELS_FIELDS,
        "capabilities": CAPABILITIES_FIELDS,
        "integrations": INTEGRATIONS_FIELDS,
        "policies": POLICIES_FIELDS,
        "surfaces": SURFACES_FIELDS,
    }


__all__ = ["ROOT_SECTIONS", "RootConfig", "section_fields"]
