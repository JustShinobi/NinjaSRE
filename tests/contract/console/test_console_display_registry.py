"""Every catalogue id the console can title has a name a person reads.

The rule is one sentence: the interface uses a display name in every title,
list and label, and the raw id — `azure_monitor`, `google_gemini` — is
reserved for a technical context. This holds the two ends of that promise
against each other: the profile every vendor package declares, and the
payload the gateway actually serves from it, so a vendor that forgot its own
name cannot ship silently and a route that stopped forwarding one cannot
either.
"""

from __future__ import annotations

import inspect

import pytest

from gateway.http.routes.integrations import IntegrationView, list_integrations
from integrations._catalogue.discovery import catalogue

pytestmark = pytest.mark.contract


def test_every_installed_integration_declares_a_display_name_and_a_category() -> None:
    """The profile itself, not the payload — the source the payload is read from."""
    entries = catalogue()
    assert entries, "no integration is installed to check"

    for entry in entries:
        assert entry.display_name.strip() != "", (
            f"{entry.name} has no display_name; its profile should have failed to "
            f"construct rather than reach here"
        )
        assert entry.category is not None


def test_the_integration_view_the_gateway_serves_carries_a_display_name() -> None:
    """The payload the console reads has the field, typed as a plain string."""
    fields = IntegrationView.model_fields
    assert "display_name" in fields, (
        "IntegrationView has no display_name field; the console has only the raw "
        "id to title a card with"
    )
    assert fields["display_name"].annotation is str


def test_the_route_forwards_the_profile_s_display_name_rather_than_the_raw_id() -> None:
    """The route reads `entry.display_name`, not `entry.name`, for this field.

    Source-level rather than a live call: the property under test is that the
    field the route *builds* is wired to the catalogue's own display name, and
    a call is a poorer way to prove that a specific keyword argument is wired
    to a specific attribute than reading the one place it is written.
    """
    source = inspect.getsource(list_integrations)
    assert "display_name=entry.display_name" in source, (
        "list_integrations does not forward entry.display_name into IntegrationView; "
        "the console would still be titling cards with the raw id"
    )
