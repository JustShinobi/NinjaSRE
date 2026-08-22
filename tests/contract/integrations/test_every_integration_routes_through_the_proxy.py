"""SC-002. Every integration in the catalogue, asserted rather than inspected.

The catalogue is three packages today and roughly eighty-five by the end of
wave 6. That growth is exactly why this is a walk over the package tree and not
a list somebody maintains: an integration added without a descriptor, without an
injection rule, or with a client that does not sit on the base class fails here
the day it lands, and nobody has to remember to add it.

What each assertion buys:

``declares a descriptor``
    There is one place per vendor that says what its credential looks like, what
    hosts it may reach, and how the secret enters the request. A vendor without
    one has no proxy path, so it has an in-process one.

``client on the base class``
    FR-015. ``IntegrationClient`` is the only sanctioned way to make an
    authenticated call, and a client that does not inherit it is making calls
    some other way.

``declares hosts``
    ``InjectionRule.hosts`` doubles as the egress allow-list (FR-009). An empty
    tuple would pass every other check here and permit nothing, which is a
    failure that would look like a working integration until the first call.
"""

from __future__ import annotations

import pytest

from integrations._base.client import IntegrationClient
from integrations.registry import descriptors, integration_names
from platform.credentials.descriptor import IntegrationDescriptor, SdkStrategy
from tests.contract.integrations.conftest import ENTRIES, integration_ids

pytestmark = pytest.mark.contract

CATALOGUE = descriptors()


def test_the_catalogue_is_not_empty() -> None:
    """A walk that found nothing would satisfy every parametrised test below."""
    assert integration_names()


@pytest.mark.parametrize("name", integration_names())
def test_the_integration_declares_a_descriptor(name: str) -> None:
    assert isinstance(CATALOGUE[name], IntegrationDescriptor)
    assert CATALOGUE[name].name == name


@pytest.mark.parametrize("name", integration_names())
def test_the_integration_declares_an_egress_allow_list(name: str) -> None:
    rule = CATALOGUE[name].rule

    assert rule.integration == name
    assert rule.hosts, "an integration that declares no host can reach nothing"
    assert all("/" not in host for host in rule.hosts), "hosts are host names, not URLs"


@pytest.mark.parametrize("name", integration_names())
def test_the_integration_declares_how_the_secret_enters_the_request(name: str) -> None:
    assert CATALOGUE[name].rule.injections, (
        "an integration with no injection sends unauthenticated requests"
    )


@pytest.mark.parametrize("name", integration_names())
def test_the_credential_schema_matches_the_injection_rule(name: str) -> None:
    """Every field an injection reads must be one the schema requires.

    The failure this catches is a rename: a schema field becomes ``token`` and
    the injection still asks for ``api_key``, which resolves to nothing and
    sends an unauthenticated request that the vendor answers with a 401 nobody
    can explain.
    """
    descriptor = CATALOGUE[name]
    declared = set(descriptor.schema.field_names)

    for injection in descriptor.rule.injections:
        missing = set(injection.fields()) - declared
        assert not missing, (
            f"{name}: {injection} reads fields the schema does not declare: {missing}"
        )


@pytest.mark.parametrize("name", integration_names())
def test_the_client_sits_on_the_base_client(name: str) -> None:
    client = CATALOGUE[name].client_class

    assert issubclass(client, IntegrationClient), (
        f"{name}: FR-015 makes IntegrationClient the only authenticated-call path"
    )


@pytest.mark.parametrize("name", integration_names())
def test_the_vendor_sdk_decision_is_recorded(name: str) -> None:
    """FR-018. Which row of the strategy table applies, and why, per vendor."""
    descriptor = CATALOGUE[name]

    assert isinstance(descriptor.sdk_strategy, SdkStrategy)
    assert descriptor.strategy_note.strip(), (
        f"{name}: a strategy with no rationale is a decision nobody can review"
    )


@pytest.mark.parametrize("name", integration_names())
def test_the_integration_declares_a_verifier(name: str) -> None:
    """FR-021 needs somewhere to send the end-to-end check."""
    assert CATALOGUE[name].verifier.integration == name


#: The host an integration ships when nobody packaging it could know the real
#: one. Recognised by suffix rather than by a list, because the list is the thing
#: that goes stale the first time a vendor is added.
PLACEHOLDER_SUFFIX = ".example.com"


@pytest.mark.parametrize("name", integration_ids())
def test_an_integration_nobody_can_place_asks_where_it_is(name: str) -> None:
    """A schema of secrets alone is a form an operator completes without connecting.

    Every self-hosted vendor ships a documentation host — ``loki.example.com``,
    ``proxmox.example.com`` — because the package cannot know where yours runs.
    An integration that ships one and asks for no address is one whose every
    call goes to the placeholder no matter what the operator entered, and whose
    verifier reports the credential stored while nothing works. That is the
    failure this pins, catalogue-wide, so the next self-hosted vendor cannot
    land without the field.
    """
    schema = ENTRIES[name].descriptor.schema
    placeholders = [
        host for host in ENTRIES[name].descriptor.rule.hosts if host.endswith(PLACEHOLDER_SUFFIX)
    ]
    if not placeholders:
        return
    assert schema.endpoint_names, (
        f"{name}: ships the placeholder host {placeholders} and declares no endpoint field, "
        f"so nothing an operator can enter will change where its calls go"
    )


@pytest.mark.parametrize("name", integration_ids())
def test_an_address_is_never_a_field_the_vault_holds(name: str) -> None:
    """It is configuration. The proxy reads it, and the proxy cannot read the vault."""
    schema = ENTRIES[name].descriptor.schema
    for address in schema.endpoint_names:
        assert address not in (schema.for_vault().field_names if schema.for_vault() else ())
        declared = schema.get(address)
        assert declared is not None and not declared.is_secret
