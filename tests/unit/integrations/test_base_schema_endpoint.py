"""The field that says where a self-hosted vendor actually is.

A credential schema that declares only secrets is a form an operator can fill in
completely and still not connect anything: the client goes on addressing the
placeholder host its package was written with. The endpoint field is the missing
half, and it is deliberately not a secret — an address is configuration, it is
readable, and it belongs in the configuration tree the proxy already reads its
egress allow-list from.
"""

from __future__ import annotations

import pytest

from integrations._base.schema import credential_schema, endpoint, secret
from platform.credentials.errors import CredentialSchemaViolation
from platform.credentials.schemas import FieldKind


def test_an_endpoint_is_configuration_rather_than_a_secret() -> None:
    """It is rendered as text, logged, and reported — none of which a secret is."""
    declared = endpoint("endpoint", "Where your Alertmanager answers.")

    assert declared.kind is FieldKind.ENDPOINT
    assert not declared.is_secret
    assert declared.is_endpoint


def test_a_schema_reports_its_endpoint_field_by_name() -> None:
    schema = credential_schema(
        "acme",
        endpoint("endpoint", "Where your Acme answers."),
        secret("token", "Acme token.", min_length=8),
    )

    assert schema.endpoint_names == ("endpoint",)
    assert schema.secret_names == ("token",)


def test_an_address_with_a_scheme_and_a_host_is_accepted() -> None:
    schema = credential_schema("acme", endpoint("endpoint", "Where your Acme answers."))

    schema.validate({"endpoint": "http://10.20.20.36:9093"})
    schema.validate({"endpoint": "https://acme.example.com"})
    schema.validate({"endpoint": "https://acme.example.com/prefix"})


def test_an_address_with_no_scheme_is_refused_and_says_so() -> None:
    """`10.20.20.36:9093` is what an operator types first, and it is ambiguous."""
    schema = credential_schema("acme", endpoint("endpoint", "Where your Acme answers."))

    with pytest.raises(CredentialSchemaViolation) as refused:
        schema.validate({"endpoint": "10.20.20.36:9093"})

    assert "http://" in str(refused.value)


def test_a_scheme_that_is_not_http_is_refused() -> None:
    schema = credential_schema("acme", endpoint("endpoint", "Where your Acme answers."))

    with pytest.raises(CredentialSchemaViolation):
        schema.validate({"endpoint": "ftp://acme.example.com"})


def test_an_address_with_no_host_is_refused() -> None:
    schema = credential_schema("acme", endpoint("endpoint", "Where your Acme answers."))

    with pytest.raises(CredentialSchemaViolation):
        schema.validate({"endpoint": "https:///just-a-path"})


def test_a_refusal_never_quotes_the_address_back() -> None:
    """The rule the module holds for secrets, kept for everything it validates."""
    schema = credential_schema("acme", endpoint("endpoint", "Where your Acme answers."))

    with pytest.raises(CredentialSchemaViolation) as refused:
        schema.validate({"endpoint": "ftp://acme.internal"})

    assert "acme.internal" not in str(refused.value)


def test_a_schema_may_not_declare_two_endpoints() -> None:
    """An integration is in one place. Two would leave the client to pick."""
    with pytest.raises(ValueError, match="more than one endpoint"):
        credential_schema(
            "acme",
            endpoint("endpoint", "Where your Acme answers."),
            endpoint("other", "Somewhere else."),
        )


def test_an_endpoint_may_be_declared_optional() -> None:
    """A vendor with a real public API needs no address from anybody."""
    schema = credential_schema(
        "acme",
        endpoint("endpoint", "Only if you host your own.", required=False),
    )

    assert schema.required_names == ()
    schema.validate({})
