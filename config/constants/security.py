"""Vault, credential proxy, guardrail, and masking configuration names.

Every name here is read by ``platform/`` on the trusted side of the boundary —
the vault bootstrap, the proxy, the guardrail engine. **None of them is read
from the agent's process.** The agent holds a
tenant-and-team-scoped handle; the proxy resolves the real secret at the network
edge (Constitution Article IV, clauses 1 and 2).

Naming a variable here therefore says where an operator configures something.
It never says the agent can see it.
"""

from __future__ import annotations

from typing import Final

# --- Credential vault --------------------------------------------------------

NINJASRE_VAULT_MASTER_KEY_ENV: Final = "NINJASRE_VAULT_MASTER_KEY"
NINJASRE_VAULT_KEY_FILE_ENV: Final = "NINJASRE_VAULT_KEY_FILE"

#: Rotating the master key re-encrypts every stored credential, so the vault
#: records which key version encrypted each row.
VAULT_KEY_VERSION_COLUMN: Final = "key_version"

#: A credential handle is ``<integration>/<team>``; a stored version appends
#: ``@v<n>``. Rotation writes a new version rather than overwriting the old one,
#: so rolling back is a pointer move and not a restore from somebody's notes.
CREDENTIAL_HANDLE_SEPARATOR: Final = "/"
CREDENTIAL_VERSION_SEPARATOR: Final = "@v"

#: The team component of a handle that belongs to the organisation rather than
#: to one team. A literal is needed because the empty string would make
#: ``datadog/`` and ``datadog`` two spellings of the same thing.
CREDENTIAL_ORG_WIDE_TEAM: Final = "-"

#: The first version the vault writes. Versions count up and are never reused,
#: so an audit line naming version 4 means the same row forever.
VAULT_INITIAL_CREDENTIAL_VERSION: Final[int] = 1

#: The label the vault puts on the pointer row's metadata to name the live
#: version. Metadata, so health checks, the console, and the operator CLI can
#: read which version is active without any code path touching a value.
VAULT_ACTIVE_VERSION_LABEL_PREFIX: Final = "active-version="

# --- Credential proxy --------------------------------------------------------

#: Mandatory in every deployment profile, including local development
#: (ADR 0005). There is no "direct" mode to fall back to.
NINJASRE_CREDENTIAL_PROXY_URL_ENV: Final = "NINJASRE_CREDENTIAL_PROXY_URL"
NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV: Final = "NINJASRE_CREDENTIAL_PROXY_TOKEN"

#: Header carrying the opaque credential handle from a tool call to the proxy.
#: The handle names a credential; it is not one.
CREDENTIAL_HANDLE_HEADER: Final = "X-NinjaSRE-Credential-Handle"
TENANT_CONTEXT_HEADER: Final = "X-NinjaSRE-Tenant"
TEAM_CONTEXT_HEADER: Final = "X-NinjaSRE-Team"

#: Names the capability whose call this is, so an audit line answers "which
#: tool used this credential" rather than only "something did".
CAPABILITY_CONTEXT_HEADER: Final = "X-NinjaSRE-Capability"

#: Names the integration whose injection rule applies. Separate from the handle
#: because the proxy resolves the rule before it resolves the credential — an
#: undeclared host is rejected without a vault read.
INTEGRATION_CONTEXT_HEADER: Final = "X-NinjaSRE-Integration"

#: Google wants the billing project in a header of its own rather than in the
#: token. It lives here rather than beside the signer because every
#: vendor-shaped literal that is not a secret belongs in this tier, and because
#: a ``GOOGLE_``-prefixed name written anywhere else fails ``check-constants``.
GOOGLE_QUOTA_PROJECT_HEADER: Final = "x-goog-user-project"

CREDENTIAL_PROXY_TIMEOUT_SECONDS: Final[float] = 30.0

#: The proxy's internal API. Two paths and nothing else: one that forwards a
#: request and one that reports health. There is deliberately no path that
#: returns a credential, because FR-010 says no configuration may enable one.
PROXY_FORWARD_PATH: Final = "/internal/forward"
PROXY_HEALTH_PATH: Final = "/internal/health"

#: Per-tenant ceiling, counted over a fixed window. A tenant that exceeds it is
#: refused rather than queued: a queue turns a runaway loop into latency
#: everybody else pays, and the refusal is what tells the operator it happened.
CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS: Final[float] = 60.0
CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT: Final[int] = 600

#: How long before expiry a short-lived credential (OAuth, STS) is refreshed.
#: Wide enough that a request starting just inside the margin still finishes
#: with a valid token, narrow enough that refreshes stay rare.
CREDENTIAL_REFRESH_MARGIN_SECONDS: Final[float] = 120.0

#: Exactly one (FR-013). A second retry on an expiry failure is a retry against
#: a credential that has already been refreshed once, so the failure is
#: something other than expiry and repeating it only spends the vendor's rate
#: limit.
CREDENTIAL_EXPIRY_RETRY_ATTEMPTS: Final[int] = 1

#: The p50 overhead the proxy hop is allowed to add, measured in
#: ``tests/benchmarks``. A capability's own network call dominates this by two
#: orders of magnitude; the budget exists so a regression that changes that is
#: a test failure rather than a slow week.
CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS: Final[float] = 0.005

#: What a resolution is called in the audit trail (FR-019).
CREDENTIAL_RESOLUTION_AUDIT_ACTION: Final = "credential.resolve"
CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND: Final = "integration"

# --- Guardrails --------------------------------------------------------------

NINJASRE_GUARDRAIL_RULES_PATH_ENV: Final = "NINJASRE_GUARDRAIL_RULES_PATH"

GUARDRAIL_ACTION_REDACT: Final = "redact"
GUARDRAIL_ACTION_BLOCK: Final = "block"
GUARDRAIL_ACTION_AUDIT: Final = "audit"

GUARDRAIL_ACTIONS: Final[tuple[str, ...]] = (
    GUARDRAIL_ACTION_REDACT,
    GUARDRAIL_ACTION_BLOCK,
    GUARDRAIL_ACTION_AUDIT,
)

#: What replaces a redacted span. Fixed width so a redaction cannot be sized to
#: infer the value behind it.
REDACTION_PLACEHOLDER: Final = "[REDACTED]"

# --- Identifier masking ------------------------------------------------------

NINJASRE_MASKING_ENABLED_ENV: Final = "NINJASRE_MASKING_ENABLED"

#: Masking is reversible and applied around every external LLM call, then undone
#: only when rendering to an authorised human (Article IV, clause 5).
MASK_TOKEN_PREFIX: Final = "NSRE_MASK_"

#: Disabling masking is an operator decision that has to be made explicitly.
MASKING_ENABLED_BY_DEFAULT: Final[bool] = True

# --- Side-effect classification ----------------------------------------------

#: ``SIDE_EFFECT_LEVELS`` is ordered least to most dangerous, and the order is
#: load-bearing: it is what "above ``read_sensitive``" means, and everything
#: above it needs per-action approval and a stored rollback plan.
#:
#: The scale separates two distinctions that a single "write" level hides. A
#: read that returns customer data is not the same risk as a read that returns
#: a pod count, and restarting a deployment is not the same risk as deleting a
#: snapshot — the first is undone by waiting, the second is not undone at all.
SIDE_EFFECT_READ: Final = "read"
SIDE_EFFECT_READ_SENSITIVE: Final = "read_sensitive"
SIDE_EFFECT_WRITE_REVERSIBLE: Final = "write_reversible"
SIDE_EFFECT_WRITE_IRREVERSIBLE: Final = "write_irreversible"
SIDE_EFFECT_DESTRUCTIVE: Final = "destructive"

SIDE_EFFECT_LEVELS: Final[tuple[str, ...]] = (
    SIDE_EFFECT_READ,
    SIDE_EFFECT_READ_SENSITIVE,
    SIDE_EFFECT_WRITE_REVERSIBLE,
    SIDE_EFFECT_WRITE_IRREVERSIBLE,
    SIDE_EFFECT_DESTRUCTIVE,
)

#: What a capability is assumed to do when it arrives carrying no declaration
#: at all — a bridged protocol tool, for instance, described by a remote server
#: that owes us nothing (Article III, clause 1). Absence is never permission.
#:
#: A first-party capability never reaches this. Omitting the level in the
#: repository fails the build instead, because a default that is *usually* right
#: is how an undeclared destructive tool eventually ships as a write.
DEFAULT_SIDE_EFFECT_LEVEL: Final = SIDE_EFFECT_WRITE_IRREVERSIBLE

#: An approval is per-action and per-session; it never generalises to a later
#: action (Article III, clause 4). This is how long one stays valid.
APPROVAL_EXPIRY_SECONDS: Final[int] = 300


__all__ = [
    "APPROVAL_EXPIRY_SECONDS",
    "CAPABILITY_CONTEXT_HEADER",
    "CREDENTIAL_EXPIRY_RETRY_ATTEMPTS",
    "CREDENTIAL_HANDLE_HEADER",
    "CREDENTIAL_HANDLE_SEPARATOR",
    "CREDENTIAL_ORG_WIDE_TEAM",
    "CREDENTIAL_PROXY_MAX_REQUESTS_PER_TENANT",
    "CREDENTIAL_PROXY_OVERHEAD_BUDGET_SECONDS",
    "CREDENTIAL_PROXY_RATE_LIMIT_WINDOW_SECONDS",
    "CREDENTIAL_PROXY_TIMEOUT_SECONDS",
    "CREDENTIAL_REFRESH_MARGIN_SECONDS",
    "CREDENTIAL_RESOLUTION_AUDIT_ACTION",
    "CREDENTIAL_RESOLUTION_AUDIT_RESOURCE_KIND",
    "CREDENTIAL_VERSION_SEPARATOR",
    "DEFAULT_SIDE_EFFECT_LEVEL",
    "GUARDRAIL_ACTIONS",
    "GUARDRAIL_ACTION_AUDIT",
    "GUARDRAIL_ACTION_BLOCK",
    "GOOGLE_QUOTA_PROJECT_HEADER",
    "GUARDRAIL_ACTION_REDACT",
    "INTEGRATION_CONTEXT_HEADER",
    "MASKING_ENABLED_BY_DEFAULT",
    "MASK_TOKEN_PREFIX",
    "NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV",
    "NINJASRE_CREDENTIAL_PROXY_URL_ENV",
    "NINJASRE_GUARDRAIL_RULES_PATH_ENV",
    "NINJASRE_MASKING_ENABLED_ENV",
    "NINJASRE_VAULT_KEY_FILE_ENV",
    "NINJASRE_VAULT_MASTER_KEY_ENV",
    "PROXY_FORWARD_PATH",
    "PROXY_HEALTH_PATH",
    "REDACTION_PLACEHOLDER",
    "SIDE_EFFECT_DESTRUCTIVE",
    "SIDE_EFFECT_LEVELS",
    "SIDE_EFFECT_READ",
    "SIDE_EFFECT_READ_SENSITIVE",
    "SIDE_EFFECT_WRITE_IRREVERSIBLE",
    "SIDE_EFFECT_WRITE_REVERSIBLE",
    "TEAM_CONTEXT_HEADER",
    "TENANT_CONTEXT_HEADER",
    "VAULT_ACTIVE_VERSION_LABEL_PREFIX",
    "VAULT_INITIAL_CREDENTIAL_VERSION",
    "VAULT_KEY_VERSION_COLUMN",
]
