"""The credential shapes every vendor turns out to have four of.

Every integration declares what its credential is made of, and almost every one
of those declarations is one of the same handful: a bearer token, an API key in
a header, a username and password, or a key pair. Written out by hand, each is
six lines of ``CredentialField`` that a contributor copies from whichever vendor
they looked at first — which is how one integration ends up validating a
whitespace-padded token and the next one does not.

So the shapes are here, once. What a vendor writes is which shape it has and
what its documentation calls the fields.

**Two rules are enforced rather than suggested.**

A validation pattern is optional and stays optional. A pattern that is nearly
right rejects the deployment on the vendor's newer key format, and the operator
has no way to override it — so the helpers below take one and never invent one.

A field says whether it is secret. ``region``, ``site``, ``account_id``, and
``cluster`` are configuration an investigation may legitimately see, and marking
them public is what lets the catalogue report "configured for eu1" without
reporting a key.

## Vault mapping

The vault stores a credential as a mapping keyed by field name, and by default
that is the whole mapping: the field is called ``api_key`` and it is stored
under ``api_key``. ``VaultMapping`` exists for the case where it cannot be —
an integration renaming a field after operators have already stored credentials
under the old name. It records the storage key beside the declared name so the
rename is one declaration rather than a migration nobody runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from platform.credentials.schemas import CredentialField, CredentialSchema, FieldKind


def secret(
    name: str,
    description: str,
    *,
    pattern: str | None = None,
    required: bool = True,
    min_length: int = 1,
    alternatives: Iterable[str] = (),
    label: str = "",
    min_scope: str = "",
    guide_url: str = "",
) -> CredentialField:
    """Return a field holding material the agent must never see."""
    return CredentialField(
        name=name,
        description=description,
        required=required,
        kind=FieldKind.SECRET,
        min_length=min_length,
        pattern=pattern,
        alternatives=tuple(alternatives),
        label=label,
        min_scope=min_scope,
        guide_url=guide_url,
    )


def public(
    name: str,
    description: str,
    *,
    required: bool = False,
    pattern: str | None = None,
    label: str = "",
    min_scope: str = "",
    guide_url: str = "",
) -> CredentialField:
    """Return a configuration field a capability may legitimately read."""
    return CredentialField(
        name=name,
        description=description,
        required=required,
        kind=FieldKind.PUBLIC,
        pattern=pattern,
        label=label,
        min_scope=min_scope,
        guide_url=guide_url,
    )


def credential_schema(integration: str, *fields: CredentialField) -> CredentialSchema:
    """Return the schema for ``integration``, built from ``fields``."""
    return CredentialSchema(integration=integration, fields=tuple(fields))


# --- The four shapes ---------------------------------------------------------


def bearer_token_schema(
    integration: str,
    *,
    description: str,
    field_name: str = "token",
    pattern: str | None = None,
    extra: Iterable[CredentialField] = (),
) -> CredentialSchema:
    """Return the schema for a vendor authenticated by one bearer token."""
    return credential_schema(
        integration,
        secret(field_name, description, pattern=pattern),
        *extra,
    )


def api_key_schema(
    integration: str,
    *,
    description: str,
    field_name: str = "api_key",
    pattern: str | None = None,
    extra: Iterable[CredentialField] = (),
) -> CredentialSchema:
    """Return the schema for a vendor authenticated by an API key in a header."""
    return credential_schema(
        integration,
        secret(field_name, description, pattern=pattern),
        *extra,
    )


def basic_auth_schema(
    integration: str,
    *,
    user_description: str,
    password_description: str,
    extra: Iterable[CredentialField] = (),
) -> CredentialSchema:
    """Return the schema for a vendor authenticated by a username and password.

    The username is a secret here even though it usually is not. Basic auth
    sends the pair together, and a username that reaches a trace is half of a
    credential in a log somebody will grep.
    """
    return credential_schema(
        integration,
        secret("username", user_description),
        secret("password", password_description),
        *extra,
    )


def key_pair_schema(
    integration: str,
    *,
    key_id_description: str,
    key_description: str,
    key_id_pattern: str | None = None,
    extra: Iterable[CredentialField] = (),
) -> CredentialSchema:
    """Return the schema for a vendor authenticated by an identifier and a secret."""
    return credential_schema(
        integration,
        secret("key_id", key_id_description, pattern=key_id_pattern),
        secret("key_secret", key_description),
        *extra,
    )


# --- Vault mapping -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VaultMapping:
    """Which vault key each declared field is stored under.

    Identity for everything the mapping does not mention, which is almost
    everything. The exceptions exist so a field rename does not orphan the
    credentials operators have already stored: the schema gets the new name and
    this records where the value actually lives.
    """

    integration: str
    keys: Mapping[str, str]

    @classmethod
    def identity(cls, schema: CredentialSchema) -> VaultMapping:
        """Return the mapping that stores every field under its own name."""
        return cls(
            integration=schema.integration,
            keys={name: name for name in schema.field_names},
        )

    def key_for(self, field_name: str) -> str:
        """Return the vault key ``field_name`` is stored under."""
        return self.keys.get(field_name, field_name)

    def stored(self, values: Mapping[str, str]) -> dict[str, str]:
        """Return ``values`` keyed the way the vault holds them."""
        return {self.key_for(name): value for name, value in values.items()}

    def declared(self, stored: Mapping[str, str]) -> dict[str, str]:
        """Return vault-keyed ``stored`` values under their declared field names."""
        reverse = {vault_key: name for name, vault_key in self.keys.items()}
        return {reverse.get(key, key): value for key, value in stored.items()}


def undeclared_fields(schema: CredentialSchema, reads: Iterable[str]) -> tuple[str, ...]:
    """Return the names in ``reads`` the schema does not declare.

    The rename check, phrased so anything that consumes a credential — an
    injection rule, a signer, a verifier — can ask the same question. Empty is
    correct; anything else means the two sides have drifted and the symptom
    would be an unauthenticated request and a 401 nobody can explain.
    """
    return tuple(sorted(set(reads) - set(schema.field_names)))


__all__ = [
    "CredentialField",
    "CredentialSchema",
    "FieldKind",
    "VaultMapping",
    "api_key_schema",
    "basic_auth_schema",
    "bearer_token_schema",
    "credential_schema",
    "key_pair_schema",
    "public",
    "secret",
    "undeclared_fields",
]
