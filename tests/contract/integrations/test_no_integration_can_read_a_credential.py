"""SC-004, asserted over the whole tier rather than per client.

The per-integration half of this lives in the parity suite: after a real call,
no secret is reachable from the client instance. This file is the other half,
and it is the one that scales — it asserts the property of the *tier*, so an
eighty-fifth integration written by somebody who never read this file is covered
the day it lands.

Three statements, in ascending order of how much each holds:

**Nothing under ``integrations/`` reads the process environment.** Not only
credential-shaped names. A vendor client takes its configuration from the
hierarchy and its credential from the proxy, so any lookup here is one or the
other in the wrong place — which is what catches the key assembled by
concatenation that a name-based rule cannot see.

**The base client has no parameter that could accept a credential.** The point
is not that contributors are careful; it is that the wrong thing is unspellable.
A constructor with a ``token`` argument is a constructor somebody will pass a
token to.

**No client class declares a slot that could hold one.** ``__slots__`` is
exhaustive — a slotted class has no ``__dict__`` — so the set of things an
instance can hold is enumerable, and the assertion is over that set rather than
over one call path somebody remembered to test.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from integrations._base.client import IntegrationClient
from integrations._catalogue.discovery import catalogue
from tools.check_direct_credentials import find_violations

pytestmark = pytest.mark.contract

REPO_ROOT = Path(__file__).resolve().parents[3]
INTEGRATIONS_ROOT = REPO_ROOT / "integrations"

#: Words that name a secret rather than a setting. A parameter or slot called
#: one of these is one somebody will fill with the thing it is named after.
CREDENTIAL_WORDS: frozenset[str] = frozenset(
    {
        "api_key",
        "app_key",
        "application_key",
        "auth",
        "credential",
        "credentials",
        "key",
        "password",
        "secret",
        "secret_key",
        "session_token",
        "token",
    }
)


def test_no_module_under_integrations_reads_the_process_environment() -> None:
    violations = find_violations([INTEGRATIONS_ROOT])

    assert not violations, "\n".join(str(violation) for violation in violations)


def test_the_base_client_has_no_parameter_a_credential_could_arrive_through() -> None:
    parameters = set(inspect.signature(IntegrationClient.__init__).parameters)

    assert not parameters & CREDENTIAL_WORDS
    assert "transport" in parameters, "the proxy transport is how an authenticated call is made"


def test_the_base_client_declares_no_slot_a_credential_could_rest_in() -> None:
    assert not set(IntegrationClient.__slots__) & {f"_{word}" for word in CREDENTIAL_WORDS}


def test_no_catalogued_client_adds_a_credential_shaped_slot_or_parameter() -> None:
    """The property has to hold for every vendor, not only for the base class."""
    offences: list[str] = []

    for entry in catalogue():
        client = entry.descriptor.client_class
        slots = {
            slot.lstrip("_") for base in client.__mro__ for slot in getattr(base, "__slots__", ())
        }
        parameters = set(inspect.signature(client.__init__).parameters)
        for held in sorted((slots | parameters) & CREDENTIAL_WORDS):
            offences.append(f"{entry.name}: {client.__name__} carries {held!r}")

    assert not offences, "\n".join(offences)
