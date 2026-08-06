"""The control plane: one configuration tree, deep-merged, per team.

A platform team sets the organisation's defaults once. Each team below it
overrides only what differs, and what the runtime reads — prompts, models,
sub-agent topology, enabled capabilities, integration references, policy
switches — resolves from the merge of that chain.

Four things about this package are load-bearing.

**The merge interprets nothing.** Dicts recurse, everything else replaces, and
no key is a directive. A document behaves the way the person reviewing the pull
request read it.

**Every effective value names the node that supplied it.** "Why is this team
using that model" is asked constantly on a four-level tree, and answering it by
walking the tree by hand is how nobody ends up asking.

**Configuration is a closed schema, not key-value storage.** That is what makes
a reference to a capability that does not exist a validation error at write
time rather than a surprise at three in the morning — and what lets the console
render a form without hard-coding a vendor's fields.

**Configuration holds references, never secrets.** A secret-shaped value is
refused at write with a pointer to the vault, and the audit trail of the attempt
is filtered by the same guardrail engine, so a mistake is not preserved in
plaintext by the record of the mistake.
"""

from __future__ import annotations

from platform.config_service.bindings import RuntimeBindings
from platform.config_service.catalogue import (
    CapabilityCatalogueReader,
    CapabilityDescription,
    CatalogueView,
    CredentialField,
    IntegrationDirectory,
    IntegrationSchema,
    StaticCatalogue,
    StaticIntegrationDirectory,
)
from platform.config_service.document import NodeDocument
from platform.config_service.effective import (
    EffectiveConfig,
    EffectiveConfigCache,
    EffectiveConfigResolver,
)
from platform.config_service.errors import (
    ChangeRequiresApproval,
    ConfigInvalid,
    ConfigServiceError,
    ConfigTooDeep,
    FieldError,
    FieldLocked,
    HierarchyCycle,
    HierarchyTooDeep,
    LockConflict,
    NodeHasDescendants,
    SecretInConfiguration,
    UnknownNode,
    UnknownTemplate,
)
from platform.config_service.field_policy import FieldPolicy, PolicySet
from platform.config_service.hierarchy import Hierarchy
from platform.config_service.merge import Layer, MergeResult, deep_merge, merge_layers
from platform.config_service.schema import RootConfig
from platform.config_service.service import ConfigService
from platform.config_service.templates import ConfigTemplate, TemplateDiff, TemplateLibrary
from platform.config_service.validation import ConfigValidator, ValidationOutcome

__all__ = [
    "CapabilityCatalogueReader",
    "CapabilityDescription",
    "CatalogueView",
    "ChangeRequiresApproval",
    "ConfigInvalid",
    "ConfigService",
    "ConfigServiceError",
    "ConfigTemplate",
    "ConfigTooDeep",
    "ConfigValidator",
    "CredentialField",
    "EffectiveConfig",
    "EffectiveConfigCache",
    "EffectiveConfigResolver",
    "FieldError",
    "FieldLocked",
    "FieldPolicy",
    "Hierarchy",
    "HierarchyCycle",
    "HierarchyTooDeep",
    "IntegrationDirectory",
    "IntegrationSchema",
    "Layer",
    "LockConflict",
    "MergeResult",
    "NodeDocument",
    "NodeHasDescendants",
    "PolicySet",
    "RootConfig",
    "RuntimeBindings",
    "SecretInConfiguration",
    "StaticCatalogue",
    "StaticIntegrationDirectory",
    "TemplateDiff",
    "TemplateLibrary",
    "UnknownNode",
    "UnknownTemplate",
    "ValidationOutcome",
    "deep_merge",
    "merge_layers",
]
