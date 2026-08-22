"""What the guided run asks for, which has to be everything the write needs.

The wizard renders ``credential_fields`` and posts them to the credential route
in one body. A field served under ``settings_fields`` is a field no screen
renders — the console reads that list nowhere — so a vendor's address landing
there would reproduce, one screen over, exactly the failure the address field
was added to fix: a form an operator completes without connecting anything.
"""

from __future__ import annotations

import pytest

from gateway.http.catalogue_readers import installed_integrations
from integrations.registry import discover

pytestmark = pytest.mark.unit


def _names(fields: object) -> set[str]:
    return {field.name for field in fields}  # type: ignore[attr-defined]


def test_the_form_asks_for_the_address_of_a_self_hosted_vendor() -> None:
    schema = installed_integrations().schema("alertmanager")

    assert schema is not None
    assert "endpoint" in _names(schema.credential_fields)


def test_the_address_is_not_hidden_in_a_list_nothing_renders() -> None:
    schema = installed_integrations().schema("alertmanager")

    assert schema is not None
    assert "endpoint" not in _names(schema.settings_fields)


def test_every_field_a_vendor_declares_is_asked_for_exactly_once() -> None:
    """Between the two lists, and never in both: a duplicate renders twice."""
    directory = installed_integrations()
    for name, descriptor in discover().items():
        schema = directory.schema(name)
        assert schema is not None, name
        asked = _names(schema.credential_fields)
        configured = _names(schema.settings_fields)
        assert not asked & configured, f"{name}: {sorted(asked & configured)} is in both lists"
        assert asked | configured == set(descriptor.schema.field_names), name


def test_the_address_is_still_not_a_secret_on_the_form() -> None:
    """It is rendered as text and it is readable. Only the secrecy flag decides."""
    schema = installed_integrations().schema("alertmanager")

    assert schema is not None
    address = next(f for f in schema.credential_fields if f.name == "endpoint")
    assert address.secret is False
