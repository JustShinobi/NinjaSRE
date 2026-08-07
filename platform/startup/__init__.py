"""Everything that has to be true before a deployment accepts its first alert.

The order in this package is the order at boot, and it is not arbitrary:

1. **Resolve the profile.** One setting decides the component set, the sandbox,
   where the credential proxy lives, and the concurrency ceiling.
2. **Validate the configuration.** Every problem at once, each naming its
   setting and what to do about it.
3. **Verify the key.** Stored credentials must open with the configured key —
   *before* migrations, so a key that did not survive a restore fails in seconds
   rather than after a schema change.
4. **Migrate.** Under an advisory lock, in order, with the resulting revision
   checked against what this release expects.
5. **Report readiness per dependency.** "Not ready" is not an answer; "the
   database is reachable and the schema is two revisions behind" is.

``sequence.run_startup`` is that list, executed. Everything else here is one of
its steps, usable on its own — an operator's preflight runs step 2 alone, and a
restore runs step 4's compatibility check without any of the rest.
"""

from __future__ import annotations

from platform.startup.backup import BackupManifest, RestoreAction, RestoreDecision, decide_restore
from platform.startup.egress import (
    EgressDestination,
    configured_destinations,
    external_destinations,
    unexpected,
)
from platform.startup.errors import (
    BackupIncompatible,
    ConfigurationInvalid,
    EgressNotPermitted,
    EncryptionKeyInvalid,
    EncryptionKeyMissing,
    MigrationLockUnavailable,
    SchemaIncompatible,
    StartupError,
    UnknownDeploymentProfile,
)
from platform.startup.keys import (
    configured_key,
    key_fingerprint,
    require_encryption_key,
)
from platform.startup.migrations import (
    MigrationOutcome,
    SchemaMigrator,
    apply_at_startup,
    check_compatibility,
)
from platform.startup.profiles import (
    DeploymentProfile,
    ProfileTopology,
    resolve_profile,
    resolve_topology,
    topology_for,
)
from platform.startup.readiness import (
    DependencyReadiness,
    DependencyState,
    ReadinessReport,
)
from platform.startup.rotation import KeyRotationReport, rotate_encryption_key
from platform.startup.sequence import StartupResult, run_startup
from platform.startup.settings import SETTINGS, Setting, render_env_example
from platform.startup.setup import SetupPlan, SetupStep, admin_token_announcement, first_run_plan
from platform.startup.validation import Finding, Severity, ValidationReport, validate

__all__ = [
    "SETTINGS",
    "BackupIncompatible",
    "BackupManifest",
    "ConfigurationInvalid",
    "DependencyReadiness",
    "DependencyState",
    "DeploymentProfile",
    "EgressDestination",
    "EgressNotPermitted",
    "EncryptionKeyInvalid",
    "EncryptionKeyMissing",
    "Finding",
    "KeyRotationReport",
    "MigrationLockUnavailable",
    "MigrationOutcome",
    "ProfileTopology",
    "ReadinessReport",
    "RestoreAction",
    "RestoreDecision",
    "SchemaIncompatible",
    "SchemaMigrator",
    "Setting",
    "SetupPlan",
    "SetupStep",
    "Severity",
    "StartupError",
    "StartupResult",
    "UnknownDeploymentProfile",
    "ValidationReport",
    "admin_token_announcement",
    "apply_at_startup",
    "check_compatibility",
    "configured_destinations",
    "configured_key",
    "decide_restore",
    "external_destinations",
    "first_run_plan",
    "key_fingerprint",
    "render_env_example",
    "require_encryption_key",
    "resolve_profile",
    "resolve_topology",
    "rotate_encryption_key",
    "run_startup",
    "topology_for",
    "unexpected",
    "validate",
]
