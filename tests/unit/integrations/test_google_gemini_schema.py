"""The provider key routed the way Article IV says every credential is routed.

A console can store a provider key today and nothing can read it. The vault
holds it, the vault's ``reveal`` is the credential proxy's to call and nobody
else's, and the proxy has no rule for any language-model provider — so the key
goes in and stops there. Meanwhile the model client reads an environment
variable, which is the one place Article IV says a credential must never be.

So the provider becomes an integration like every other: a declared credential
shape, a declared host, and a rule that puts the key in at the network edge. The
key then works because it is stored, rather than working because it was also
exported.

**The header, not the query string.** Gemini accepts both. A query string
reaches access logs, proxy logs and referrer headers, and a key that has been
written to a log is a key that has to be rotated.
"""

from __future__ import annotations

import pytest

from integrations.google_gemini.schema import HOSTS, INTEGRATION, RULE, SCHEMA

pytestmark = pytest.mark.unit


def test_the_provider_is_declared_under_the_name_the_vault_already_uses() -> None:
    """A credential is stored against an integration name. A rule under any
    other spelling would leave the stored key unreadable — which is the defect
    this closes, reintroduced by a typo."""
    assert INTEGRATION == "google_gemini"


def test_the_schema_asks_for_the_one_thing_the_provider_needs() -> None:
    names = {field.name for field in SCHEMA.fields}

    assert "api_key" in names


def test_the_api_key_is_declared_secret() -> None:
    """A field the schema calls public is one the console will show back."""
    from platform.credentials.schemas import FieldKind

    secret_fields = {field.name for field in SCHEMA.fields if field.kind is FieldKind.SECRET}

    assert "api_key" in secret_fields


def test_the_rule_reads_only_fields_the_schema_declares() -> None:
    """A rule reading a field nobody is asked for is a credential that half
    works: stored, accepted, and missing the part the vendor checks."""
    declared = {field.name for field in SCHEMA.fields}

    for injection in RULE.injections:
        assert set(injection.fields()) <= declared


def test_the_key_goes_in_a_header_rather_than_the_query_string() -> None:
    """A query string reaches access logs and referrer headers, and a key that
    has been logged has to be rotated."""
    from platform.credentials.proxy.injection import QueryParameterInjection

    assert not any(isinstance(one, QueryParameterInjection) for one in RULE.injections)
    assert any(getattr(one, "header", "") == "x-goog-api-key" for one in RULE.injections)


def test_the_egress_allowlist_names_the_provider_and_nothing_wider() -> None:
    """The allow-list is what stops a compromised prompt sending the key
    somewhere else, so it is exact names rather than a suffix match."""
    assert HOSTS == ("generativelanguage.googleapis.com",)
    assert not any("*" in host for host in HOSTS)


def test_the_rule_permits_exactly_the_declared_hosts() -> None:
    assert RULE.hosts == HOSTS
