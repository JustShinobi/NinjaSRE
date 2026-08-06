"""The credential vault, and the proxy that is the only thing allowed to read it.

Constitution Article IV: no credential reaches the agent — not in an environment
variable, a prompt, a tool argument, the filesystem, or a trace. This package is
the mechanism, and it is split along the line that makes the claim checkable:

``vault``, ``schemas``, ``handles``, ``health``, ``verification``
    The operator's half. Storing, validating, versioning, rotating, and
    reporting on credentials. **None of it can read one.** ``Vault`` has no
    method that returns a value, and that absence is the guarantee — a reviewer
    asking "can this see credentials?" reads the class surface and is done.

``proxy/``
    The credential's half. One module in it calls
    ``CredentialStore.reveal``; the secret exists for the width of one request
    and is injected at the network edge.

``descriptor``
    What each vendor declares so the two halves can meet: the credential's
    shape, the hosts it may reach, how the secret enters the request, and how to
    check that it works.

``tools/check_direct_credentials.py`` holds the same line in CI, by failing the
build on a ``reveal`` call outside ``proxy/`` and on any module below tier 3
reaching for a credential-shaped environment variable.
"""

from __future__ import annotations

from platform.credentials.descriptor import (
    IntegrationDescriptor,
    IntegrationVerifier,
    SdkStrategy,
)
from platform.credentials.errors import (
    CredentialError,
    CredentialNotConfigured,
    CredentialSchemaViolation,
    CredentialVersionNotFound,
    MalformedHandle,
    UnknownIntegration,
    VaultKeyMismatch,
)
from platform.credentials.handles import CredentialHandle
from platform.credentials.health import (
    CredentialHealth,
    CredentialHealthReport,
    CredentialHealthState,
    IntegrationCredentialHealth,
    verify_startup,
)
from platform.credentials.schemas import (
    CredentialField,
    CredentialSchema,
    CredentialSchemaRegistry,
    FieldKind,
)
from platform.credentials.vault import CredentialVersion, Vault
from platform.credentials.verification import (
    CredentialVerification,
    VerificationProbe,
    VerificationResult,
)

__all__ = [
    "CredentialError",
    "CredentialField",
    "CredentialHandle",
    "CredentialHealth",
    "CredentialHealthReport",
    "CredentialHealthState",
    "CredentialNotConfigured",
    "CredentialSchema",
    "CredentialSchemaRegistry",
    "CredentialSchemaViolation",
    "CredentialVerification",
    "CredentialVersion",
    "CredentialVersionNotFound",
    "FieldKind",
    "IntegrationCredentialHealth",
    "IntegrationDescriptor",
    "IntegrationVerifier",
    "MalformedHandle",
    "SdkStrategy",
    "UnknownIntegration",
    "Vault",
    "VaultKeyMismatch",
    "VerificationProbe",
    "VerificationResult",
    "verify_startup",
]
