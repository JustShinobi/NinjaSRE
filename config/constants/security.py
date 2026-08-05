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

CREDENTIAL_PROXY_TIMEOUT_SECONDS: Final[float] = 30.0

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
    "CREDENTIAL_HANDLE_HEADER",
    "CREDENTIAL_PROXY_TIMEOUT_SECONDS",
    "DEFAULT_SIDE_EFFECT_LEVEL",
    "GUARDRAIL_ACTIONS",
    "GUARDRAIL_ACTION_AUDIT",
    "GUARDRAIL_ACTION_BLOCK",
    "GUARDRAIL_ACTION_REDACT",
    "MASKING_ENABLED_BY_DEFAULT",
    "MASK_TOKEN_PREFIX",
    "NINJASRE_CREDENTIAL_PROXY_TOKEN_ENV",
    "NINJASRE_CREDENTIAL_PROXY_URL_ENV",
    "NINJASRE_GUARDRAIL_RULES_PATH_ENV",
    "NINJASRE_MASKING_ENABLED_ENV",
    "NINJASRE_VAULT_KEY_FILE_ENV",
    "NINJASRE_VAULT_MASTER_KEY_ENV",
    "REDACTION_PLACEHOLDER",
    "SIDE_EFFECT_DESTRUCTIVE",
    "SIDE_EFFECT_LEVELS",
    "SIDE_EFFECT_READ",
    "SIDE_EFFECT_READ_SENSITIVE",
    "SIDE_EFFECT_WRITE_IRREVERSIBLE",
    "SIDE_EFFECT_WRITE_REVERSIBLE",
    "TEAM_CONTEXT_HEADER",
    "TENANT_CONTEXT_HEADER",
    "VAULT_KEY_VERSION_COLUMN",
]
