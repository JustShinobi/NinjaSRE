"""One suite over the whole catalogue: adding an integration adds a row, not a file.

Every assertion below is a failure somebody has already had, phrased so that it
lands on the day the integration does rather than at 03:00 during the incident
that needed it:

``parity``
    The seven artefacts. An integration missing one is not "mostly done" — the
    missing one is precisely the part that would have saved the incident, and
    which one it is differs per omission. Named individually so the message says
    what to write.

``schema validity``
    A credential schema whose fields the injection rule does not read, or reads
    under another name, sends an unauthenticated request and gets a 401 nobody
    can explain.

``proxy routing``
    Article IV. The client makes its call and the credential is added at the
    network edge; a client that reached the vendor another way would pass every
    other check here.

``error mapping``
    A vendor's status arrives as one of seven categories the loop reasons about.
    An unclassified failure makes the loop do the same wrong thing on every
    incident.

``pagination``
    A vendor's declared style, per endpoint. A client that assumed one style for
    a whole API reads page one forever on the endpoints that use the other.

``capability metadata``
    ``side_effect_level`` has no default and nothing else may be blank either: a
    tool that declares nothing competes on nothing and is selected at random.

``skill binding``
    A skill directing a tool no package declares tells the model to call
    something that is not there, and the loop spends iterations discovering it.

``documentation``
    Setup being tribal knowledge is how an integration is configured wrongly by
    the third team to try.

``synthetic scenario``
    Without one the integration rots: nothing exercises it end to end, and the
    first person to notice is the investigation that needed it.
"""

from __future__ import annotations

import inspect

import pytest

from capabilities.registry.discovery import discover
from capabilities.registry.validation import DANGLING_DIRECTED_TOOL, failures
from integrations._base.client import IntegrationClient
from integrations._base.errors import ErrorCategory, IntegrationError, category_for
from integrations._base.pagination import PaginationStyle, supported_styles
from integrations._catalogue.entry import CatalogueEntry, IntegrationCategory, ParityStatus
from integrations._catalogue.validation import Artefact
from platform.credentials.proxy.injection import PathSegmentInjection
from platform.credentials.proxy.model import OutboundRequest
from tests.contract.integrations.conftest import (
    CATALOGUE,
    CONTEXT,
    CREDENTIALS,
    ENTRIES,
    PROFILES,
    integration_ids,
    stand_up,
)

pytestmark = pytest.mark.contract

IDS = integration_ids()

#: Vendor statuses every integration has to classify the same way. A 403 that
#: one client calls "permission" and another calls "transient" is a loop that
#: retries one vendor's authorisation failure for the whole retry budget.
CLASSIFIED_STATUSES: tuple[tuple[int, ErrorCategory], ...] = (
    (401, ErrorCategory.AUTH),
    (403, ErrorCategory.PERMISSION),
    (404, ErrorCategory.NOT_FOUND),
    (429, ErrorCategory.RATE_LIMITED),
    (400, ErrorCategory.INVALID_REQUEST),
    (500, ErrorCategory.TRANSIENT),
    (503, ErrorCategory.TRANSIENT),
)


def test_the_catalogue_is_not_empty() -> None:
    """A walk that found nothing would satisfy every parametrised test below."""
    assert CATALOGUE, "discovery found no integrations, so nothing below asserts anything"


# --- The seven artefacts (FR-001, FR-002) ------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_the_integration_ships_all_seven_artefacts(name: str) -> None:
    parity = ENTRIES[name].parity

    assert parity.status is ParityStatus.COMPLETE, parity.failure_message()
    assert set(parity.present) == set(Artefact)


@pytest.mark.parametrize("name", IDS)
def test_the_catalogue_entry_records_what_an_operator_has_to_supply(name: str) -> None:
    """FR-021, per row."""
    entry = ENTRIES[name]

    assert isinstance(entry.category, IntegrationCategory)
    assert entry.summary.strip()
    assert entry.required_credentials, "an integration that needs no credential needs no proxy"
    assert entry.capabilities, "an integration with no tool cannot be reached by the agent"
    record = entry.to_record()
    assert set(record) >= {
        "name",
        "category",
        "capabilities",
        "required_credentials",
        "required_permissions",
        "regions",
        "health",
        "parity",
    }


# --- Credential schema (T002) ------------------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_the_credential_schema_is_valid_and_the_rule_reads_only_what_it_declares(
    name: str,
) -> None:
    descriptor = ENTRIES[name].descriptor

    assert descriptor.schema.integration == name
    assert descriptor.schema.fields
    assert descriptor.undeclared_injection_fields() == ()
    assert descriptor.schema.required_names, (
        f"{name}: a schema with nothing required accepts an empty credential"
    )


@pytest.mark.parametrize("name", IDS)
def test_a_credential_the_schema_accepts_is_the_one_the_suite_uses(name: str) -> None:
    """Otherwise the routing test below proves the fixture, not the integration."""
    assert name in CREDENTIALS, f"{name}: the contract suite has no credential in its shape"
    ENTRIES[name].descriptor.schema.validate(CREDENTIALS[name])


# --- Proxy routing (T003) ----------------------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_the_client_sits_on_the_base_client_and_cannot_hold_a_credential(name: str) -> None:
    client_class = ENTRIES[name].descriptor.client_class

    assert issubclass(client_class, IntegrationClient)
    parameters = inspect.signature(client_class.__init__).parameters
    schema_fields = set(ENTRIES[name].descriptor.schema.secret_names)
    assert not schema_fields & set(parameters), (
        f"{name}: the client constructor accepts a secret field, so a caller can pass one in"
    )


@pytest.mark.parametrize("name", IDS)
async def test_every_call_reaches_the_vendor_through_the_proxy(name: str) -> None:
    entry = ENTRIES[name]
    transport, vendor = await stand_up([found.descriptor for found in CATALOGUE], seeded=(name,))
    client = entry.descriptor.client_class(transport=transport, context=CONTEXT)

    await client.ping()

    assert len(vendor.sent) == 1, f"{name}: ping made {len(vendor.sent)} calls, not one"
    sent = vendor.sent[0]
    assert entry.descriptor.rule.permits(sent.host), (
        f"{name}: reached {sent.host}, which its own allow-list does not permit"
    )
    assert _authenticated(entry, sent), f"{name}: the vendor received nothing the proxy injected"


@pytest.mark.parametrize("name", IDS)
async def test_no_credential_value_survives_anywhere_on_the_client(name: str) -> None:
    """SC-004, per integration, after a real call rather than at construction."""
    transport, _ = await stand_up([found.descriptor for found in CATALOGUE], seeded=(name,))
    client = ENTRIES[name].descriptor.client_class(transport=transport, context=CONTEXT)

    await client.ping()

    held = repr({slot: getattr(client, slot, None) for slot in _slots_of(type(client))})
    for field_name in ENTRIES[name].descriptor.schema.secret_names:
        secret = CREDENTIALS[name].get(field_name)
        if secret:
            assert secret not in held, f"{name}: {field_name} is reachable from the client"


# --- Error mapping (T004) ----------------------------------------------------


@pytest.mark.parametrize(("status", "expected"), CLASSIFIED_STATUSES)
def test_every_vendor_status_maps_onto_the_shared_taxonomy(
    status: int, expected: ErrorCategory
) -> None:
    """FR-006. One table, so two integrations cannot disagree about a 403."""
    assert category_for(status) is expected


@pytest.mark.parametrize("name", IDS)
async def test_a_refused_call_comes_back_classified_rather_than_raw(name: str) -> None:
    from platform.credentials.proxy.model import OutboundResponse

    transport, vendor = await stand_up([found.descriptor for found in CATALOGUE], seeded=(name,))
    vendor.responses.append(OutboundResponse(403, {}, b"forbidden"))
    client = ENTRIES[name].descriptor.client_class(transport=transport, context=CONTEXT)

    with pytest.raises(IntegrationError) as raised:
        await client.ping()

    assert raised.value.category is ErrorCategory.PERMISSION
    assert raised.value.integration == name


# --- Pagination (T005) -------------------------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_each_paginated_endpoint_declares_a_style_the_base_client_walks(name: str) -> None:
    """FR-005, including the vendor that paginates two endpoints two ways."""
    profile = PROFILES[name]
    client_class = ENTRIES[name].descriptor.client_class

    assert profile.pagination, (
        f"{name}: no endpoint declares a pagination style, so nothing states how a "
        f"second page is asked for"
    )
    for endpoint in profile.pagination:
        assert isinstance(endpoint.style, PaginationStyle)
        assert endpoint.style in supported_styles()
        assert endpoint.parameter.strip(), (
            f"{name}.{endpoint.endpoint}: a style with no parameter cannot ask for page two"
        )
        assert callable(getattr(client_class, endpoint.endpoint, None)), (
            f"{name}: declares pagination for {endpoint.endpoint!r}, which the client "
            f"does not expose"
        )


# --- Capability metadata (T006) ----------------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_every_capability_declares_what_selection_and_approval_need(name: str) -> None:
    tools = [found for found in discover().tools if found.metadata.evidence_source == name]

    assert tools, f"{name}: no tool declares this integration as its evidence source"
    for found in tools:
        metadata = found.metadata
        assert metadata.description.strip()
        assert metadata.use_cases, f"{found.name}: no use case, so nothing scores it"
        assert metadata.anti_examples, f"{found.name}: no anti-example, so nothing suppresses it"
        assert metadata.side_effect_level is not None
        assert name in metadata.requires.integrations, (
            f"{found.name}: does not require {name}, so a team without it still sees the tool"
        )
        if metadata.side_effect_level.needs_approval:
            assert metadata.requires_approval
            assert metadata.approval_reason.strip()
            assert metadata.rollback_plan or metadata.rollback_planner


# --- Skill-to-tool binding (T007) --------------------------------------------


@pytest.mark.parametrize("name", IDS)
def test_the_methodology_skill_directs_tools_that_exist(name: str) -> None:
    catalogue = discover()
    skills = [skill for skill in catalogue.skills if name in skill.metadata.requires.integrations]
    declared = {found.name for found in catalogue.tools}

    assert skills, f"{name}: no skill requires it, so its methodology reaches no investigation"
    for skill in skills:
        assert skill.metadata.directs_tools, (
            f"{skill.name}: directs no tools, so it is prose the model cannot act on"
        )
        dangling = sorted(set(skill.metadata.directs_tools) - declared)
        assert not dangling, f"{skill.name}: directs {dangling}, which no package declares"


def test_the_whole_catalogue_binds() -> None:
    """The same rule across every skill, not only the per-integration ones."""
    dangling = [
        failure
        for failure in failures(discover(), check_bodies=False)
        if failure.rule == DANGLING_DIRECTED_TOOL
    ]

    assert not dangling, "\n".join(str(failure) for failure in dangling)


# --- Documentation and scenarios (T008, T009) --------------------------------


@pytest.mark.parametrize("name", IDS)
def test_the_setup_documentation_says_what_an_operator_has_to_do(name: str) -> None:
    document = ENTRIES[name].parity.docs_path
    assert document is not None and document.exists()

    text = document.read_text(encoding="utf-8")
    for heading in ("Setup", "Permissions", "Limitations"):
        assert heading.lower() in text.lower(), (
            f"{name}: docs.md has no {heading} section, which is the part an operator reads"
        )
    for credential in ENTRIES[name].required_credentials:
        assert credential in text, f"{name}: docs.md never mentions the {credential} field"


@pytest.mark.parametrize("name", IDS)
def test_a_synthetic_scenario_exercises_the_integration(name: str) -> None:
    scenario = ENTRIES[name].parity.scenario_path
    assert scenario is not None and scenario.exists()

    text = scenario.read_text(encoding="utf-8")
    assert "SCENARIOS" in text, (
        f"{name}: the scenario module exposes no SCENARIOS, so the harness collects nothing"
    )


# --- Helpers -----------------------------------------------------------------


def _authenticated(entry: CatalogueEntry, sent: OutboundRequest) -> bool:
    """Return whether the proxy put anything into the request the client did not.

    Three shapes, and the third is the one a header check misses. A header or a
    query parameter is visible on the request; a *path* injection is visible
    only as an absence — the client sends ``/bot{token}/getMe`` and the vendor
    receives a path with the placeholder gone. Reading that as "nothing was
    injected" would let the one vendor whose credential travels in the URL pass
    this test for the wrong reason.
    """
    if sent.headers or "?" in sent.url:
        return True
    placeholders = [
        "{" + injection.placeholder + "}"
        for injection in entry.descriptor.rule.injections
        if isinstance(injection, PathSegmentInjection)
    ]
    return bool(placeholders) and not any(marker in sent.url for marker in placeholders)


def _slots_of(cls: type) -> tuple[str, ...]:
    """Return every slot the class and its bases declare.

    A slotted class has no ``__dict__`` — there is nowhere to stash a credential
    — so "what does this instance hold" has to be asked of the slots.
    """
    return tuple(slot for base in cls.__mro__ for slot in getattr(base, "__slots__", ()))
