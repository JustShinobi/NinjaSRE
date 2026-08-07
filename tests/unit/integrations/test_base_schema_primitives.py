"""The credential shapes, and the two rules the helpers exist to keep.

A field says whether it is secret, and a validation pattern stays optional. Both
are cheap to get wrong by copying whichever vendor a contributor looked at
first, and both have a failure that only shows during an incident: a region
marked secret disappears from every diagnostic, and a pattern that is nearly
right rejects the operator's perfectly valid newer key.
"""

from __future__ import annotations

import pytest

from integrations._base.schema import (
    VaultMapping,
    api_key_schema,
    basic_auth_schema,
    bearer_token_schema,
    credential_schema,
    key_pair_schema,
    public,
    secret,
    undeclared_fields,
)
from platform.credentials.errors import CredentialSchemaViolation


def test_a_bearer_token_vendor_declares_one_required_secret() -> None:
    schema = bearer_token_schema("acme", description="Acme personal access token.")

    assert schema.required_names == ("token",)
    assert schema.secret_names == ("token",)


def test_configuration_beside_the_secret_is_public_and_optional() -> None:
    """A region a capability may read, and a key it may not, in one schema."""
    schema = api_key_schema(
        "acme",
        description="Acme API key.",
        extra=(public("region", "Which regional deployment this organisation is on."),),
    )

    assert schema.secret_names == ("api_key",)
    assert schema.required_names == ("api_key",)
    assert schema.get("region") is not None and not schema.get("region").is_secret


def test_basic_auth_treats_the_username_as_half_a_credential() -> None:
    """The pair travels together; a username in a trace is half of it in a log."""
    schema = basic_auth_schema(
        "acme", user_description="Service account.", password_description="Its password."
    )

    assert set(schema.secret_names) == {"username", "password"}


def test_a_key_pair_vendor_declares_the_identifier_and_the_secret() -> None:
    schema = key_pair_schema(
        "acme",
        key_id_description="Key identifier.",
        key_description="Key secret.",
        key_id_pattern=r"AK[0-9A-Z]{8}",
    )

    with pytest.raises(CredentialSchemaViolation):
        schema.validate({"key_id": "nope", "key_secret": "s3cret"})
    schema.validate({"key_id": "AK12345678", "key_secret": "s3cret"})


def test_a_pattern_is_only_applied_when_a_vendor_actually_fixes_the_format() -> None:
    """No helper invents one — a nearly-right pattern rejects a valid key."""
    schema = bearer_token_schema("acme", description="Token.")

    schema.validate({"token": "whatever-format-acme-issues-next-year"})


def test_a_copy_paste_artefact_is_rejected_while_the_operator_is_still_looking() -> None:
    schema = bearer_token_schema("acme", description="Token.")

    with pytest.raises(CredentialSchemaViolation, match="whitespace"):
        schema.validate({"token": "abcdef\n"})


def test_a_field_the_injection_reads_but_the_schema_does_not_declare_is_named() -> None:
    """The rename check, phrased so anything consuming a credential may ask it."""
    schema = credential_schema("acme", secret("token", "Token."))

    assert undeclared_fields(schema, ("token", "api_key")) == ("api_key",)
    assert undeclared_fields(schema, ("token",)) == ()


def test_the_vault_mapping_is_identity_until_a_field_is_renamed() -> None:
    schema = api_key_schema("acme", description="Acme API key.")
    mapping = VaultMapping.identity(schema)

    assert mapping.key_for("api_key") == "api_key"


def test_a_renamed_field_still_finds_the_credential_operators_already_stored() -> None:
    """The rename is one declaration rather than a migration nobody runs."""
    mapping = VaultMapping(integration="acme", keys={"api_key": "acme_key"})

    assert mapping.stored({"api_key": "value"}) == {"acme_key": "value"}
    assert mapping.declared({"acme_key": "value"}) == {"api_key": "value"}
