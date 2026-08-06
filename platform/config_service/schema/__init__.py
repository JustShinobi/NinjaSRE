"""The declared shape of configuration: six sections, every field typed.

``RootConfig`` is the whole surface. Build one from a merged mapping with
``RootConfig.of`` — which raises carrying every field-level problem — or with
``RootConfig.read``, which returns the errors instead so a caller can add its
own passes before deciding.

Defaults live in ``config/constants/`` and ``config/prompts/`` rather than in
the database. A fresh deployment therefore works with no configuration at all,
and improving a shipped prompt is a diff rather than a migration over every
team's stored copy.
"""

from __future__ import annotations

from platform.config_service.schema.agents import (
    AgentsConfig,
    ModelsConfig,
    ModelSelection,
    SubAgentConfig,
)
from platform.config_service.schema.capabilities import CapabilitiesConfig
from platform.config_service.schema.integrations import IntegrationsConfig, IntegrationSettings
from platform.config_service.schema.policies import (
    ApprovalPolicySettings,
    CustomMaskingPattern,
    GuardrailPolicySettings,
    KnowledgePolicySettings,
    MaskingPolicySettings,
    MemoryPolicySettings,
    PoliciesConfig,
    StrategyPolicySettings,
)
from platform.config_service.schema.reader import Reader
from platform.config_service.schema.root import ROOT_SECTIONS, RootConfig, section_fields
from platform.config_service.schema.surfaces import (
    ChannelSettings,
    DestinationSettings,
    SurfacesConfig,
)

__all__ = [
    "ROOT_SECTIONS",
    "AgentsConfig",
    "ApprovalPolicySettings",
    "CapabilitiesConfig",
    "ChannelSettings",
    "CustomMaskingPattern",
    "DestinationSettings",
    "GuardrailPolicySettings",
    "IntegrationSettings",
    "IntegrationsConfig",
    "KnowledgePolicySettings",
    "MaskingPolicySettings",
    "MemoryPolicySettings",
    "ModelSelection",
    "ModelsConfig",
    "PoliciesConfig",
    "Reader",
    "RootConfig",
    "StrategyPolicySettings",
    "SubAgentConfig",
    "SurfacesConfig",
    "section_fields",
]
