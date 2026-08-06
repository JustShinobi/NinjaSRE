"""What the vault raises, and the rule every message here obeys.

**No message names a value.** An exception string reaches places a log line does
not — a traceback in an operator's console, an error field in an API response,
a pytest failure captured in CI output — so scrubbing logs is not enough. Every
error here identifies a credential by handle and a field by name, and there is
no code path that puts plaintext into one.

That constraint shapes ``CredentialSchemaViolation`` in particular. It reports
which fields were missing, blank, or malformed; it never reports what was
supplied, because "expected 32 hex characters, got ``a3f1…``" is a leak wearing
the costume of a helpful error message.
"""

from __future__ import annotations

from collections.abc import Sequence


class CredentialError(Exception):
    """Base for every vault and proxy failure. Never carries a secret value."""


class UnknownIntegration(CredentialError, LookupError):
    """No schema or injection rule is declared for this integration.

    Names the integrations that *are* declared, because the realistic cause is a
    typo or a package that was never imported, and both are answered by the
    list.
    """

    def __init__(self, integration: str, *, known: Sequence[str] = ()) -> None:
        known_names = ", ".join(sorted(known)) if known else "none"
        super().__init__(
            f"No integration named {integration!r} is declared. Declared: {known_names}."
        )
        self.integration = integration
        self.known = tuple(known)


class CredentialSchemaViolation(CredentialError, ValueError):
    """A credential did not match its integration's schema (FR-005).

    Rejected on write rather than at the first call. A key with a stray newline
    stored happily and failed at 03:00 during the one incident that needed it;
    validating on the way in moves that failure to the moment somebody was
    already looking at the screen.
    """

    def __init__(self, *, integration: str, problems: Sequence[str]) -> None:
        listed = "; ".join(problems)
        super().__init__(f"The credential for {integration!r} is not valid: {listed}.")
        self.integration = integration
        self.problems = tuple(problems)


class CredentialNotConfigured(CredentialError, LookupError):
    """This tenant and team have no credential for this integration.

    The actionable half is the handle, because that is what an operator types
    into the command that fixes it.
    """

    def __init__(self, handle: str, *, integration: str) -> None:
        super().__init__(
            f"No credential is configured for {integration!r} under the handle {handle!r}."
        )
        self.handle = handle
        self.integration = integration


class CredentialVersionNotFound(CredentialError, LookupError):
    """A rollback named a version the vault does not hold."""

    def __init__(self, handle: str, version: int) -> None:
        super().__init__(f"The credential {handle!r} has no version {version}.")
        self.handle = handle
        self.version = version


class MalformedHandle(CredentialError, ValueError):
    """A handle that cannot be parsed, or that carries a reserved separator."""


class VaultKeyMismatch(CredentialError, RuntimeError):
    """Stored credentials cannot be decrypted with the configured key.

    Raised at startup, on purpose. A deployment that boots with the wrong key
    works perfectly until the first credential is needed, and the first
    credential is needed during an incident.
    """

    def __init__(self, handles: Sequence[str]) -> None:
        count = len(handles)
        listed = ", ".join(sorted(handles))
        super().__init__(
            f"{count} stored credential(s) cannot be decrypted with the configured "
            f"encryption key: {listed}. The key differs from the one that wrote them — "
            f"restore the original key rather than re-entering the credentials, or the "
            f"rows become unreadable for good."
        )
        self.handles = tuple(handles)


__all__ = [
    "CredentialError",
    "CredentialNotConfigured",
    "CredentialSchemaViolation",
    "CredentialVersionNotFound",
    "MalformedHandle",
    "UnknownIntegration",
    "VaultKeyMismatch",
]
